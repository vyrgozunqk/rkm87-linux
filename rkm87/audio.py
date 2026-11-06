"""Audio monitor, volume detection, and FFT spectrum visualizer for RK M87."""

import math
import os
import subprocess
import threading
from typing import Callable, List, Optional, Dict, Tuple
import numpy as np

# Load audiobar column definition from data/modes.json
from .lighting import load_modes_data, LightingManager, LightingConfig

MODES_DATA = load_modes_data()
EQUALIZER_BANDS = MODES_DATA.get("equalizer_bands", [])


def get_current_volume() -> int:
    """Get current master volume (0-100) via pulsectl, wpctl, or pactl."""
    try:
        import pulsectl
        with pulsectl.Pulse("rkm87-vol-query") as pulse:
            info = pulse.server_info()
            sink = pulse.get_sink_by_name(info.default_sink_name)
            if sink.mute:
                return 0
            return min(100, round(pulse.volume_get_all_chans(sink) * 100))
    except Exception:
        pass

    # Try wpctl (PipeWire)
    try:
        out = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], capture_output=True, text=True, timeout=1)
        if out.returncode == 0:
            parts = out.stdout.strip().split()
            vol = float(parts[1])
            muted = "[MUTED]" in out.stdout
            return 0 if muted else min(100, round(vol * 100))
    except Exception:
        pass

    # Fallback pactl
    try:
        out = subprocess.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"], capture_output=True, text=True, timeout=1)
        if out.returncode == 0:
            for part in out.stdout.split("/"):
                part = part.strip()
                if part.endswith("%"):
                    return min(100, int(part[:-1]))
    except Exception:
        pass

    return 50


MUSIC_STYLES = {
    1: {"name": "Classic Frequency EQ", "desc": "11 vertical columns with green, yellow, and red peak bars"},
    2: {"name": "Center-Out Expansion", "desc": "Equalizer bars expanding horizontally from keyboard center"},
    3: {"name": "Rainbow Frequency", "desc": "Bass (Red) to Treble (Violet) traveling spectrum"},
    4: {"name": "Bass Kick Pulse", "desc": "Low-frequency thumping pulse with dancing mids/highs"},
    5: {"name": "Waveform Ripple", "desc": "Dynamic audio waves propagating across keyboard rows"},
    6: {"name": "Waterfall Drop", "desc": "Audio spikes falling down from Function row like rain"},
    7: {"name": "Monochrome Reactive", "desc": "Solid custom color bouncing dynamically to volume"},
    8: {"name": "Stereo Split EQ", "desc": "Bass/Rhythm on left hand, Highs/Melody on right hand"},
    9: {"name": "Fire Spectrum", "desc": "Leaping flames from dark crimson to scorching yellow-white"},
    10: {"name": "Cyberpunk Neon", "desc": "Electric Neon Cyan and Hot Pink dual-tone visualizer"},
}


class AudioSpectrumStreamer:
    """Captures default desktop audio monitor and computes 11-band FFT spectrum with Winamp physics."""

    def __init__(self, callback: Callable[[List[float]], None], rate: int = 22050, chunk_size: int = 1470, use_mic: bool = False):
        self.callback = callback
        self.rate = rate
        self.chunk_size = chunk_size  # ~15 fps (66.7ms per frame), perfect for keyboard MCU USB throughput
        self.gain = 1.2
        self.use_mic = use_mic
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen] = None

        # Winamp-style peak and decay physics
        self.num_bands = 11
        self.smooth_levels = [0.0] * self.num_bands
        self.peak_levels = [0.0] * self.num_bands
        self.peak_decay = 0.02
        self.falloff = 0.05

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass
            self._process = None
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _run(self):
        import shutil
        cmd = None
        if shutil.which("pw-record"):
            if self.use_mic:
                # Capture standard default recording source (Microphone)
                cmd = ["pw-record", "--format", "s16", f"--rate={self.rate}", "--channels=2", "-"]
            else:
                # Capture desktop audio sink monitor ("What you hear")
                cmd = ["pw-record", "-P", "{ stream.capture.sink = true }", "--format", "s16", f"--rate={self.rate}", "--channels=2", "-"]
        elif shutil.which("parec"):
            if self.use_mic:
                cmd = ["parec", "--format=s16le", f"--rate={self.rate}", "--channels=2"]
            else:
                cmd = ["parec", "-d", "@DEFAULT_SINK@.monitor", "--format=s16le", f"--rate={self.rate}", "--channels=2"]

        if not cmd:
            print("Audio recording tool (pw-record / parec) not found.")
            return

        try:
            self._process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception as e:
            print(f"Failed to launch audio recorder: {e}")
            return

        bytes_per_sample = 2 * 2  # stereo 16-bit
        chunk_bytes = self.chunk_size * bytes_per_sample
        freq_bins = np.logspace(np.log10(45), np.log10(self.rate / 2), self.num_bands + 1)

        while self._running and self._process and self._process.poll() is None:
            try:
                raw_data = self._process.stdout.read(chunk_bytes)
            except Exception:
                break

            if not raw_data or len(raw_data) < chunk_bytes:
                continue

            stereo = np.frombuffer(raw_data, dtype=np.int16).reshape(-1, 2)
            # Downmix stereo desktop output to mono for FFT analysis
            samples = stereo.mean(axis=1).astype(np.float32) / 32768.0

            # Compute FFT
            fft_data = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
            freqs = np.fft.rfftfreq(len(samples), 1.0 / self.rate)

            current_bands = []
            for i in range(self.num_bands):
                low_f = freq_bins[i]
                high_f = freq_bins[i + 1]
                idx = np.where((freqs >= low_f) & (freqs < high_f))[0]
                if len(idx) > 0:
                    val = float(np.mean(fft_data[idx]))
                    # Logarithmic decibel scale: [-48 dB, 0 dB] -> [0.0, 1.0] with sensitivity multiplier
                    db = 20.0 * math.log10(max(val, 1e-6))
                    sensitivity = max(0.2, self.gain)
                    norm = max(0.0, min(1.0, (db + 45.0) / 40.0 * (sensitivity / 1.0)))
                else:
                    norm = 0.0

                # Winamp decay physics: instant rise, smooth decay
                if norm > self.smooth_levels[i]:
                    self.smooth_levels[i] = norm
                else:
                    self.smooth_levels[i] = max(0.0, self.smooth_levels[i] - self.falloff)

                # Peak hold with gravity
                if norm > self.peak_levels[i]:
                    self.peak_levels[i] = norm
                else:
                    self.peak_levels[i] = max(0.0, self.peak_levels[i] - self.peak_decay)

                current_bands.append(self.smooth_levels[i])

            try:
                self.callback(current_bands)
            except Exception:
                pass


class MusicVisualizerController:
    """Orchestrates audio FFT streaming, visualizer style shaders, and hardware transmission."""

    def __init__(self, dev, gui_callback: Optional[Callable[[Dict[str, tuple]], None]] = None):
        self.dev = dev
        self.lighting = LightingManager(dev) if dev else None
        self.gui_callback = gui_callback
        self.style_id = 1
        self.custom_color = (0, 255, 230)
        self.streamer: Optional[AudioSpectrumStreamer] = None
        self.use_mic = False
        self._running = False
        self._lock = threading.Lock()
        self.animation_phase = 0.0
        self._saved_lighting: Optional[LightingConfig] = None
        self._last_hw_send = 0.0

        # Precompute all keys defined in EQUALIZER_BANDS
        self._all_eq_keys = set()
        for col in EQUALIZER_BANDS:
            for step in col:
                for k in step:
                    self._all_eq_keys.add(k)
        self._previous_lit_keys = set()

    def set_audio_source(self, use_mic: bool):
        """Switch audio input source between Desktop Audio and Microphone."""
        if self.use_mic == use_mic:
            return
        self.use_mic = use_mic
        if self._running and self.streamer:
            current_gain = self.streamer.gain
            self.streamer.stop()
            self.streamer = AudioSpectrumStreamer(self._on_audio_bands, use_mic=self.use_mic)
            self.streamer.gain = current_gain
            self.streamer.start()

    def start(self, style_id: int = 1, gain: float = 1.2, use_mic: bool = False):
        self.style_id = style_id
        self.use_mic = use_mic
        if self._running:
            if self.streamer:
                self.streamer.gain = gain
            return

        # Real-time physical keyboard LED visualization is disabled over 2.4GHz wireless dongle (firmware limitation)
        if self.dev and self.dev.is_dongle:
            return

        if self.lighting:
            try:
                self._saved_lighting = self.lighting.get_current_lighting()
                import time
                # Put keyboard into Gaoshou mode 19 at full brightness 20
                prof = bytearray(128)
                prof[6] = 20
                prof[7] = 2
                prof[8] = 7
                prof[9] = 1    # Gaoshou flag
                prof[10] = 19  # Mode 19 (Gaoshou)
                prof[11] = 0x20 # Group 0
                prof[0x38] = 0xFF
                prof[0x39] = 0xFF
                for eff in range(1, 21):
                    off = 56 + eff * 2
                    if off + 1 < 128:
                        prof[off] = 20
                        prof[off + 1] = (2 << 4) | 7
                self.lighting._commit_led_payload(prof)
                time.sleep(0.04)
            except Exception:
                self._saved_lighting = None

        self._running = True
        self.streamer = AudioSpectrumStreamer(self._on_audio_bands, use_mic=self.use_mic)
        self.streamer.gain = gain
        self.streamer.start()

    def stop(self):
        self._running = False
        if self.streamer:
            self.streamer.stop()
            self.streamer = None

        if self.lighting and self.dev and self.dev.fd and not self.dev.is_dongle:
            try:
                # Clear all visualizer keys
                clear_colors = {k: (0, 0, 0) for k in self._all_eq_keys}
                self.lighting.send_realtime_matrix_lighting(clear_colors)
            except Exception:
                pass

            # Restore original lighting if it was a built-in studio effect (1..17); otherwise default to Rainbow
            if self._saved_lighting and 1 <= self._saved_lighting.effect <= 17 and self._saved_lighting.brightness > 0:
                try:
                    self.lighting.set_lighting(self._saved_lighting)
                except Exception:
                    pass
            else:
                self.lighting.set_lighting(LightingConfig(effect=1, brightness=20, speed=2, palette_index=7))

        self._previous_lit_keys.clear()

    def _on_audio_bands(self, bands: List[float]):
        """Render keyboard colors based on active style and stream frame to hardware."""
        if not self._running:
            return

        self.animation_phase = (self.animation_phase + 0.1) % (2 * math.pi)
        key_colors: Dict[str, tuple] = {}

        # Render active style
        style = self.style_id
        if style == 1:
            key_colors = self._render_winamp_classic(bands)
        elif style == 2:
            key_colors = self._render_center_out(bands)
        elif style == 3:
            key_colors = self._render_rainbow_freq(bands)
        elif style == 4:
            key_colors = self._render_bass_pulse(bands)
        elif style == 5:
            key_colors = self._render_waveform_ripple(bands)
        elif style == 6:
            key_colors = self._render_waterfall(bands)
        elif style == 7:
            key_colors = self._render_monochrome(bands)
        elif style == 8:
            key_colors = self._render_stereo_split(bands)
        elif style == 9:
            key_colors = self._render_fire_spectrum(bands)
        elif style == 10:
            key_colors = self._render_cyberpunk_neon(bands)
        else:
            key_colors = self._render_winamp_classic(bands)

        # Notify GUI canvas
        if self.gui_callback:
            try:
                self.gui_callback(key_colors)
            except Exception:
                pass

        # Send to hardware via real-time matrix command (CMD_SET_GAME)
        # Real-time LED matrix streaming is disabled over 2.4GHz wireless dongle (firmware limitation)
        if self.dev and self.dev.is_dongle:
            return

        import time
        now = time.monotonic()
        # On USB wired cable: 16 FPS (60ms) delivers maximum silky smooth animation.
        min_hw_interval = 0.060
        if (now - self._last_hw_send) >= min_hw_interval:
            if self.lighting and self.dev and self.dev.fd and not self.dev.is_dongle and self._lock.acquire(blocking=False):
                try:
                    self._last_hw_send = now
                    self.lighting.send_realtime_matrix_lighting(key_colors)
                except Exception:
                    pass
                finally:
                    self._lock.release()

    # --- Visualizer Style Shaders ---

    def _render_winamp_classic(self, bands: List[float]) -> Dict[str, tuple]:
        """Classic Winamp EQ bars: Green bottom, Yellow mid, Red top."""
        keys = {}
        eq_colors = [
            (0, 255, 0),      # Step 0: Green
            (60, 255, 0),     # Step 1: Lime
            (180, 255, 0),    # Step 2: Yellow-Green
            (255, 220, 0),    # Step 3: Yellow
            (255, 120, 0),    # Step 4: Orange
            (255, 0, 0),      # Step 5: Red
        ]
        for col_idx, steps in enumerate(EQUALIZER_BANDS[:len(bands)]):
            level = bands[col_idx]
            max_step = int(level * len(steps))
            for s_idx, key_list in enumerate(steps):
                if s_idx <= max_step and max_step > 0:
                    color = eq_colors[min(len(eq_colors) - 1, s_idx)]
                    for kname in key_list:
                        keys[kname] = color
        return keys

    def _render_center_out(self, bands: List[float]) -> Dict[str, tuple]:
        """Bars expand outward from middle columns (columns 5 -> 0 and 5 -> 10)."""
        keys = {}
        for col_idx, steps in enumerate(EQUALIZER_BANDS[:len(bands)]):
            dist = abs(col_idx - 5)
            band_val = bands[col_idx]
            max_step = int(band_val * len(steps))
            r = int(min(255, dist * 50))
            g = int(max(0, 255 - dist * 40))
            b = 255 if dist > 3 else 50
            for s_idx, key_list in enumerate(steps):
                if s_idx <= max_step and max_step > 0:
                    for kname in key_list:
                        keys[kname] = (r, g, b)
        return keys

    def _render_rainbow_freq(self, bands: List[float]) -> Dict[str, tuple]:
        """Frequency drives hue (Bass=Red, Mids=Green/Yellow, Treble=Violet)."""
        keys = {}
        for col_idx, steps in enumerate(EQUALIZER_BANDS[:len(bands)]):
            level = bands[col_idx]
            max_step = int(level * len(steps))
            hue = (col_idx / 11.0) * 300.0  # 0 (red) to 300 (magenta)
            rgb = self._hsv_to_rgb(hue, 1.0, min(1.0, 0.4 + level * 0.6))
            for s_idx, key_list in enumerate(steps):
                if s_idx <= max_step and max_step > 0:
                    for kname in key_list:
                        keys[kname] = rgb
        return keys

    def _render_bass_pulse(self, bands: List[float]) -> Dict[str, tuple]:
        """Sub-bass kick pulses entire backdrop while highs animate."""
        keys = {}
        bass_energy = float(np.mean(bands[:3])) if len(bands) >= 3 else 0.0
        pulse_rgb = (int(bass_energy * 200), int(bass_energy * 30), int(bass_energy * 255))
        for col_idx, steps in enumerate(EQUALIZER_BANDS[:len(bands)]):
            level = bands[col_idx]
            max_step = int(level * len(steps))
            for s_idx, key_list in enumerate(steps):
                color = (255, 255, 255) if (s_idx <= max_step and max_step > 0) else pulse_rgb
                for kname in key_list:
                    keys[kname] = color
        return keys

    def _render_waveform_ripple(self, bands: List[float]) -> Dict[str, tuple]:
        """Traveling sinusoidal waves modulated by sound volume."""
        keys = {}
        avg_vol = float(np.mean(bands))
        for col_idx, steps in enumerate(EQUALIZER_BANDS[:len(bands)]):
            level = bands[col_idx]
            wave = 0.5 + 0.5 * math.sin(self.animation_phase * 2 + col_idx * 0.6)
            effective_level = (level * 0.7 + wave * 0.3 * avg_vol)
            max_step = int(effective_level * len(steps))
            for s_idx, key_list in enumerate(steps):
                if s_idx <= max_step and max_step > 0:
                    for kname in key_list:
                        keys[kname] = (0, int(150 + 105 * wave), 255)
        return keys

    def _render_waterfall(self, bands: List[float]) -> Dict[str, tuple]:
        """Raindrops falling downwards when volume peaks."""
        keys = {}
        for col_idx, steps in enumerate(EQUALIZER_BANDS[:len(bands)]):
            level = bands[col_idx]
            num_steps = len(steps)
            drop_pos = int((1.0 - level) * num_steps)
            for s_idx, key_list in enumerate(steps):
                if s_idx == drop_pos and level > 0.15:
                    for kname in key_list:
                        keys[kname] = (0, 240, 255)
                elif s_idx > drop_pos and level > 0.3:
                    trail_bright = int(180 * (1.0 - (s_idx - drop_pos) / num_steps))
                    for kname in key_list:
                        keys[kname] = (0, trail_bright, 200)
        return keys

    def _render_monochrome(self, bands: List[float]) -> Dict[str, tuple]:
        """Monochrome single-color EQ bars."""
        keys = {}
        cr, cg, cb = self.custom_color
        for col_idx, steps in enumerate(EQUALIZER_BANDS[:len(bands)]):
            level = bands[col_idx]
            max_step = int(level * len(steps))
            for s_idx, key_list in enumerate(steps):
                if s_idx <= max_step and max_step > 0:
                    factor = 0.5 + 0.5 * (s_idx / len(steps))
                    color = (int(cr * factor), int(cg * factor), int(cb * factor))
                    for kname in key_list:
                        keys[kname] = color
        return keys

    def _render_stereo_split(self, bands: List[float]) -> Dict[str, tuple]:
        """Left side = Deep Blue bass; Right side = Electric Pink highs."""
        keys = {}
        for col_idx, steps in enumerate(EQUALIZER_BANDS[:len(bands)]):
            level = bands[col_idx]
            max_step = int(level * len(steps))
            is_left = col_idx < 6
            color = (0, 150, 255) if is_left else (255, 20, 140)
            for s_idx, key_list in enumerate(steps):
                if s_idx <= max_step and max_step > 0:
                    for kname in key_list:
                        keys[kname] = color
        return keys

    def _render_fire_spectrum(self, bands: List[float]) -> Dict[str, tuple]:
        """Fiery spectrum: Crimson bottom -> Orange -> Hot Yellow peaks."""
        keys = {}
        for col_idx, steps in enumerate(EQUALIZER_BANDS[:len(bands)]):
            level = bands[col_idx]
            max_step = int(level * len(steps))
            for s_idx, key_list in enumerate(steps):
                if s_idx <= max_step and max_step > 0:
                    ratio = s_idx / max(1, len(steps) - 1)
                    r = 255
                    g = int(ratio * 220)
                    b = int(ratio * ratio * 150)
                    for kname in key_list:
                        keys[kname] = (r, g, b)
        return keys

    def _render_cyberpunk_neon(self, bands: List[float]) -> Dict[str, tuple]:
        """Alternating Neon Cyan and Hot Pink columns with bright white accents."""
        keys = {}
        for col_idx, steps in enumerate(EQUALIZER_BANDS[:len(bands)]):
            level = bands[col_idx]
            max_step = int(level * len(steps))
            is_cyan = (col_idx % 2 == 0)
            base_color = (0, 255, 230) if is_cyan else (255, 0, 130)
            for s_idx, key_list in enumerate(steps):
                if s_idx == max_step and max_step > 0:
                    color = (255, 255, 255)  # Peak tip
                elif s_idx < max_step:
                    color = base_color
                else:
                    continue
                for kname in key_list:
                    keys[kname] = color
        return keys

    @staticmethod
    def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
        c = v * s
        x = c * (1 - abs((h / 60.0) % 2 - 1))
        m = v - c
        if 0 <= h < 60:
            rp, gp, bp = c, x, 0
        elif 60 <= h < 120:
            rp, gp, bp = x, c, 0
        elif 120 <= h < 180:
            rp, gp, bp = 0, c, x
        elif 180 <= h < 240:
            rp, gp, bp = 0, x, c
        elif 240 <= h < 300:
            rp, gp, bp = x, 0, c
        else:
            rp, gp, bp = c, 0, x
        return (int((rp + m) * 255), int((gp + m) * 255), int((bp + m) * 255))
