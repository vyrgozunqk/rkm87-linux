"""TFT Screen Image and GIF processor and uploader for RK M87."""

import fcntl
import math
import os
import struct
import time
from typing import Callable, Generator, List, Optional, Tuple
from PIL import Image, ImageSequence

from . import protocol
from .device import RKDevice, _HIDIOCSFEATURE


def rgb_to_rgb565_be(r: int, g: int, b: int) -> bytes:
    """Convert RGB 888 to 16-bit big-endian RGB565."""
    r5 = (r >> 3) & 0x1F
    g6 = (g >> 2) & 0x3F
    b5 = (b >> 3) & 0x1F
    val = (r5 << 11) | (g6 << 5) | b5
    return struct.pack(">H", val)


def process_image_frame(img: Image.Image, width: int = protocol.SCREEN_WIDTH, height: int = protocol.SCREEN_HEIGHT) -> bytes:
    """Resize, crop, and convert a PIL Image frame to raw RGB565 bytes (240x135)."""
    # Resize preserving aspect ratio and crop to center
    img = img.convert("RGB")
    src_w, src_h = img.size

    scale = max(width / src_w, height / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    left = (new_w - width) // 2
    top = (new_h - height) // 2
    img_cropped = img_resized.crop((left, top, left + width, top + height))

    raw_bytes = bytearray()
    pixels = img_cropped.load()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            raw_bytes.extend(rgb_to_rgb565_be(r, g, b))

    return bytes(raw_bytes)


def load_gif_or_image(file_path: str, max_frames: int = protocol.SCREEN_MAX_FRAMES) -> Tuple[List[bytes], int]:
    """Load an image or animated GIF file.
    Returns: (list_of_rgb565_frames, average_delay_ms)
    """
    img = Image.open(file_path)
    frames: List[bytes] = []
    delays: List[int] = []

    for frame in ImageSequence.Iterator(img):
        raw_frame = process_image_frame(frame)
        frames.append(raw_frame)
        d = frame.info.get("duration", 100)
        delays.append(d if d > 0 else 100)
        if len(frames) >= max_frames:
            break

    avg_delay = sum(delays) // len(delays) if delays else 100
    return frames, avg_delay


class ScreenUploader:
    def __init__(self, dev: RKDevice):
        self.dev = dev

    def abort(self):
        """Explicitly send abort signal (mode 2) to reset screen MCU state safely."""
        if not self.dev.fd or self.dev.is_dongle:
            return
        abort_payload = protocol.build_gif_param_payload(mode=2, frame_count=0, delay_ms=0)
        abort_buf = protocol.build_feature_report(protocol.CMD_WIRED_SET_GIF_PARAM, abort_payload)
        try:
            fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(abort_buf)), abort_buf)
        except OSError:
            pass

    def upload_gif(
        self,
        file_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """Upload a GIF or image to the keyboard screen over USB cable.
        progress_callback: fn(current_step, total_steps, status_text)
        cancel_check: optional fn() -> bool, if returns True transfer aborts cleanly
        """
        if self.dev.is_dongle:
            raise RuntimeError("Screen image/GIF uploads are only supported over USB Cable.")
        if self.dev.fd is None:
            raise RuntimeError("Device is not connected.")

        # Pre-flight frame loading & validation in memory BEFORE touching hardware
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        frames, delay_ms = load_gif_or_image(file_path)
        if not frames:
            raise ValueError("No valid image frames found in file.")
        if len(frames) > protocol.SCREEN_MAX_FRAMES:
            frames = frames[:protocol.SCREEN_MAX_FRAMES]

        frame_bytes_len = len(frames[0])
        chunks_per_frame = math.ceil(frame_bytes_len / protocol.SCREEN_CHUNK_SIZE)
        total_chunks = len(frames) * chunks_per_frame
        current_chunk = 0

        # Step 1: Start transfer (mode 1)
        start_payload = protocol.build_gif_param_payload(mode=1, frame_count=len(frames), delay_ms=delay_ms)
        start_buf = protocol.build_feature_report(protocol.CMD_WIRED_SET_GIF_PARAM, start_payload)
        fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(start_buf)), start_buf)
        time.sleep(0.05)

        try:
            # Step 2: Stream chunks
            for f_idx, frame_data in enumerate(frames):
                for c_idx in range(chunks_per_frame):
                    if cancel_check and cancel_check():
                        self.abort()
                        if progress_callback:
                            progress_callback(current_chunk, total_chunks, "Upload cancelled by user.")
                        return False

                    offset = c_idx * protocol.SCREEN_CHUNK_SIZE
                    chunk_slice = frame_data[offset:offset + protocol.SCREEN_CHUNK_SIZE]

                    page_payload = protocol.build_page_chunk_payload(f_idx, c_idx, chunk_slice)
                    page_buf = protocol.build_feature_report(protocol.CMD_WIRED_ACCESS_DATA_PAGE, page_payload)
                    fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(page_buf)), page_buf)

                    current_chunk += 1
                    if progress_callback:
                        progress_callback(
                            current_chunk,
                            total_chunks,
                            f"Uploading frame {f_idx + 1}/{len(frames)} (page {c_idx + 1}/{chunks_per_frame})"
                        )

                    time.sleep(0.005)  # Safe throttle for hardware MCU

            # Step 3: Finish transfer (mode 0)
            finish_payload = protocol.build_gif_param_payload(mode=0, frame_count=len(frames), delay_ms=delay_ms)
            finish_buf = protocol.build_feature_report(protocol.CMD_WIRED_SET_GIF_PARAM, finish_payload)
            fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(finish_buf)), finish_buf)
            time.sleep(0.05)

            if progress_callback:
                progress_callback(total_chunks, total_chunks, "Upload completed successfully!")
            return True

        except Exception as e:
            self.abort()
            raise e
