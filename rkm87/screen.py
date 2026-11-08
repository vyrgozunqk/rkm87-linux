"""TFT Screen Image and GIF processor and uploader for RK M87."""

import fcntl
import math
import os
import select
import struct
import time
from typing import Callable, List, Optional, Tuple
from PIL import Image, ImageSequence

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

from . import protocol
from .device import RKDevice, _HIDIOCSFEATURE


def rgb_to_rgb565_be(r: int, g: int, b: int) -> bytes:
    """Convert RGB 888 to 16-bit big-endian RGB565."""
    r5 = (r >> 3) & 0x1F
    g6 = (g >> 2) & 0x3F
    b5 = (b >> 3) & 0x1F
    val = (r5 << 11) | (g6 << 5) | b5
    return struct.pack(">H", val)


def process_image_frame(
    img: Image.Image,
    width: int = protocol.SCREEN_WIDTH,
    height: int = protocol.SCREEN_HEIGHT,
    scale_mode: str = "fill",
) -> bytes:
    """Process and convert an Image frame to raw RGB565 bytes (240x135).
    scale_mode:
      - 'fill': Scale preserving aspect ratio to completely fill the 240x135 screen (center-cropped, matching official software).
      - 'fit': Scale preserving aspect ratio to fit inside 240x135 with black letterbox borders.
      - 'stretch': Directly stretch to 240x135 without preserving aspect ratio.
    """
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        bg.alpha_composite(rgba)
        img = bg.convert("RGB")
    else:
        img = img.convert("RGB")

    src_w, src_h = img.size

    if scale_mode == "stretch":
        final_img = img.resize((width, height), Image.Resampling.LANCZOS)
    elif scale_mode == "fit":
        scale = min(width / src_w, height / src_h)
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))
        img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        final_img = Image.new("RGB", (width, height), (0, 0, 0))
        left = (width - new_w) // 2
        top = (height - new_h) // 2
        final_img.paste(img_resized, (left, top))
    else:  # default "fill"
        scale = max(width / src_w, height / src_h)
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))
        img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - width) // 2
        top = (new_h - height) // 2
        final_img = img_resized.crop((left, top, left + width, top + height))

    if HAS_NUMPY:
        arr = np.asarray(final_img, dtype=np.uint16)
        r = (arr[:, :, 0] >> 3) & 0x1F
        g = (arr[:, :, 1] >> 2) & 0x3F
        b = (arr[:, :, 2] >> 3) & 0x1F
        rgb565 = (r << 11) | (g << 5) | b
        return rgb565.byteswap().tobytes()

    raw_bytes = bytearray()
    pixels = final_img.load()
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[x, y]
            raw_bytes.extend(rgb_to_rgb565_be(r, g, b))
    return bytes(raw_bytes)


def load_gif_or_image(
    file_path: str,
    max_frames: int = protocol.SCREEN_MAX_FRAMES,
    scale_mode: str = "fill",
) -> Tuple[List[bytes], int]:
    """Load an image or animated GIF file.
    Returns: (list_of_rgb565_frames, average_delay_ms)
    """
    img = Image.open(file_path)
    frames: List[bytes] = []
    delays: List[int] = []

    for frame in ImageSequence.Iterator(img):
        raw_frame = process_image_frame(frame, scale_mode=scale_mode)
        frames.append(raw_frame)
        d = frame.info.get("duration", 100)
        delays.append(d if d > 0 else 100)
        if len(frames) >= max_frames:
            break

    avg_delay = sum(delays) // len(delays) if delays else 100
    return frames, avg_delay


def _drain_input(fd: int):
    """Drain any pending unread packets from the hidraw descriptor."""
    while True:
        r, _, _ = select.select([fd], [], [], 0.0)
        if not r:
            break
        try:
            os.read(fd, 64)
        except OSError:
            break


def _wait_ack(fd: int, timeout: float = 2.0) -> bytes:
    """Wait for the 8-byte acknowledgment packet from the screen microcontroller.
    Response starts with [0x09, 0x0A, 0x06, 0x01, ...]
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        rem = max(0.01, deadline - time.time())
        r, _, _ = select.select([fd], [], [], rem)
        if not r:
            raise TimeoutError("Timeout waiting for keyboard screen ACK.")
        try:
            data = os.read(fd, 64)
        except OSError as e:
            raise RuntimeError(f"Error reading from device: {e}")
        if len(data) >= 4 and data[0] == 0x09 and data[1] == 0x0A:
            return data
    raise TimeoutError("Timeout waiting for keyboard screen ACK.")


class ScreenUploader:
    def __init__(self, dev: RKDevice):
        self.dev = dev

    def abort(self):
        """Explicitly send abort signal (mode 2) to reset screen MCU state safely."""
        if not self.dev.fd or self.dev.is_dongle:
            return
        try:
            _drain_input(self.dev.fd)
            abort_payload = protocol.build_gif_param_payload(mode=2, frame_count=0, delay_ms=100)
            abort_buf = protocol.build_feature_report(protocol.CMD_WIRED_SET_GIF_PARAM, abort_payload)
            fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(abort_buf)), abort_buf)
            try:
                _wait_ack(self.dev.fd, timeout=1.0)
            except TimeoutError:
                pass
            time.sleep(0.05)
            try:
                self.dev.sync_time_and_volume(50)
            except Exception:
                pass
        except OSError:
            pass

    def upload_gif(
        self,
        file_path: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        scale_mode: str = "fill",
    ) -> bool:
        """Upload a GIF or image to the keyboard screen over USB cable.
        Flow control waits for hardware MCU flash-write ACKs on every 512-byte chunk.
        progress_callback: fn(current_step, total_steps, status_text)
        cancel_check: optional fn() -> bool, if returns True transfer aborts cleanly
        scale_mode: 'fill' (crop to fill screen), 'fit' (letterbox), or 'stretch'
        """
        if self.dev.is_dongle:
            raise RuntimeError("Screen image/GIF uploads are only supported over USB Cable.")
        if self.dev.fd is None:
            raise RuntimeError("Device is not connected.")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        frames, delay_ms = load_gif_or_image(file_path, scale_mode=scale_mode)
        if not frames:
            raise ValueError("No valid image frames found in file.")
        if len(frames) > protocol.SCREEN_MAX_FRAMES:
            frames = frames[:protocol.SCREEN_MAX_FRAMES]

        frame_bytes_len = len(frames[0])
        chunks_per_frame = math.ceil(frame_bytes_len / protocol.SCREEN_CHUNK_SIZE)
        total_chunks = len(frames) * chunks_per_frame
        current_chunk = 0

        _drain_input(self.dev.fd)

        # Step 1: Start transfer (mode 1)
        start_payload = protocol.build_gif_param_payload(mode=1, frame_count=len(frames), delay_ms=delay_ms)
        start_buf = protocol.build_feature_report(protocol.CMD_WIRED_SET_GIF_PARAM, start_payload)
        fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(start_buf)), start_buf)
        _wait_ack(self.dev.fd, timeout=3.0)

        try:
            # Step 2: Stream chunks with hardware flash ACK handshake
            for f_idx, frame_data in enumerate(frames):
                for c_idx in range(chunks_per_frame):
                    if cancel_check and cancel_check():
                        self.abort()
                        if progress_callback:
                            progress_callback(current_chunk, total_chunks, "Upload cancelled by user.")
                        return False

                    offset = c_idx * protocol.SCREEN_CHUNK_SIZE
                    chunk_slice = frame_data[offset:offset + protocol.SCREEN_CHUNK_SIZE]

                    page_buf = protocol.build_screen_page_chunk(f_idx, c_idx, chunk_slice)

                    ack_ok = False
                    for _ in range(3):
                        fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(page_buf)), page_buf)
                        try:
                            ack = _wait_ack(self.dev.fd, timeout=2.0)
                            if len(ack) >= 4 and ack[3] == 0x01:
                                ack_ok = True
                                break
                        except TimeoutError:
                            pass

                    if not ack_ok:
                        raise RuntimeError(f"Microcontroller failed to ACK page chunk {c_idx} of frame {f_idx + 1}.")

                    current_chunk += 1
                    if progress_callback:
                        progress_callback(
                            current_chunk,
                            total_chunks,
                            f"Uploading frame {f_idx + 1}/{len(frames)}"
                        )

            # Step 3: Finish transfer (mode 0)
            finish_payload = protocol.build_gif_param_payload(mode=0, frame_count=len(frames), delay_ms=delay_ms)
            finish_buf = protocol.build_feature_report(protocol.CMD_WIRED_SET_GIF_PARAM, finish_payload)
            fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(finish_buf)), finish_buf)
            try:
                _wait_ack(self.dev.fd, timeout=3.0)
            except TimeoutError:
                pass

            if progress_callback:
                progress_callback(total_chunks, total_chunks, "Upload completed successfully!")
            return True

        except Exception as e:
            self.abort()
            raise e
