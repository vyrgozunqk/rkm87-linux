"""Background service daemon for RK M87:
- Synchronizes local time to keyboard RTC
- Synchronizes OS audio volume to keyboard LCD bar
- Optionally streams live sound/music spectrum to RGB LEDs
"""

import signal
import sys
import time
from datetime import datetime
from typing import Optional

from .audio import AudioSpectrumStreamer, get_current_volume
from .device import RKDevice
from .lighting import LightingManager


class RKDaemon:
    def __init__(self, enable_music_sync: bool = False):
        self.enable_music_sync = enable_music_sync
        self.dev = RKDevice()
        self.lighting_mgr = LightingManager(self.dev)
        self.audio_streamer: Optional[AudioSpectrumStreamer] = None
        self._running = False

    def on_spectrum_update(self, bands):
        """Called when audio spectrum data arrives (11 frequency bands)."""
        if not self.dev.fd or not self.enable_music_sync or self.dev.is_dongle:
            return
        # Convert 11 bands into real-time RGB frame payload (cmdId 0x88)
        # 11 columns, each can light up from 1 to 6 steps
        frame = bytearray(14)
        for i, val in enumerate(bands[:11]):
            level = min(5, int(val * 6))
            frame[i] = level
        self.dev.send_real_data(bytes(frame))

    def run(self):
        self._running = True

        def _sig_handler(signum, frame):
            print("\nShutting down RK M87 daemon...")
            self._running = False

        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)

        print("Starting RK M87 Background Daemon...")

        if self.enable_music_sync:
            self.audio_streamer = AudioSpectrumStreamer(self.on_spectrum_update)
            self.audio_streamer.start()
            print("Music RGB visualizer stream started.")

        last_time_sync = 0.0
        time_sync_interval = 30 * 60  # 30 minutes
        last_volume = -1
        vol_dirty = False
        vol_change_time = 0.0
        vol_debounce = 0.5  # 500ms quiet period to keep encoder responsive
        old_dongle = None

        while self._running:
            # Poll for hotplug or reconnect (handles switching between cable and dongle)
            has_dev = self.dev.poll_hotplug()
            if not has_dev or not self.dev.fd:
                time.sleep(2)
                continue

            if old_dongle != self.dev.is_dongle:
                old_dongle = self.dev.is_dongle
                mode_str = "2.4GHz Dongle" if self.dev.is_dongle else "USB Cable"
                print(f"Connected to RK M87 on {self.dev.dev_path} ({mode_str})")
                last_time_sync = 0.0  # Force immediate sync on connect

            now_mono = time.monotonic()

            # Check volume
            curr_vol = get_current_volume()
            if curr_vol != last_volume:
                last_volume = curr_vol
                vol_dirty = True
                vol_change_time = now_mono

            # Determine whether to send SysParam
            time_due = (now_mono - last_time_sync) >= time_sync_interval
            debounce_ready = vol_dirty and ((now_mono - vol_change_time) >= vol_debounce)

            if debounce_ready or time_due:
                if self.dev.is_awake():
                    vol_to_send = last_volume if last_volume >= 0 else 50
                    now_dt = datetime.now()
                    ok = self.dev.sync_time_and_volume(vol_to_send, now_dt)
                    if ok:
                        if time_due:
                            print(f"[{now_dt.strftime('%H:%M:%S')}] Time synchronized to keyboard LCD.")
                            last_time_sync = now_mono
                        if debounce_ready:
                            print(f"Volume synchronized: {vol_to_send}%")
                            vol_dirty = False
                else:
                    # Keyboard is asleep, wait a bit before checking again
                    pass

            time.sleep(0.1)

        if self.audio_streamer:
            self.audio_streamer.stop()
        self.dev.close()
        print("Daemon stopped.")


def start_daemon(music: bool = False):
    daemon = RKDaemon(enable_music_sync=music)
    daemon.run()


if __name__ == "__main__":
    music_flag = "--music" in sys.argv
    start_daemon(music=music_flag)
