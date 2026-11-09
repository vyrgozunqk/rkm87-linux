"""Lighting configuration manager for RK M87."""

import json
import os
from dataclasses import dataclass
from typing import Optional, List, Dict, Any, Tuple

from . import protocol
from .device import RKDevice

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def load_modes_data() -> Dict[str, Any]:
    modes_path = os.path.join(DATA_DIR, "modes.json")
    if os.path.exists(modes_path):
        with open(modes_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"modes": [], "palette": [], "brightness_levels": [0, 4, 8, 12, 16, 20], "speed_levels": [0, 1, 2, 3, 4]}


@dataclass
class LightingConfig:
    effect: int = 1         # 1 = Neon_Stream, 17 = Steady, 18 = Breathing, etc.
    brightness: int = 20    # 0, 4, 8, 12, 16, 20
    speed: int = 2         # 0..4
    palette_index: int = 7  # 0=Red, 1=Green, 2=Blue, 3=Yellow, 4=Pink, 5=Cyan, 6=White, 7=Rainbow
    debounce: Optional[int] = None       # 1 = Gaming Mode (1ms), 4 = Office Mode (4ms)
    sleep_minutes: Optional[int] = None # 10, 20, 40, 60, 0 (Never)


DEFAULT_PALETTE_RGB = [
    (255, 0, 0),      # 0: Red
    (0, 255, 0),      # 1: Green
    (0, 0, 255),      # 2: Blue
    (255, 255, 0),    # 3: Yellow
    (255, 50, 130),   # 4: Pink
    (0, 255, 255),    # 5: Cyan
    (255, 255, 255),  # 6: White
]


class LightingManager:
    def __init__(self, dev: RKDevice):
        self.dev = dev
        self.data = load_modes_data()
        self.modes = self.data.get("modes", [])
        self.palette = self.data.get("palette", [])
        self._cached_color_table: Optional[bytearray] = None
        self.last_debounce: int = 4
        self.last_sleep_minutes: int = 10
        self.last_preset_config: Optional[LightingConfig] = None
        self.last_custom_key_colors: Dict[str, Tuple[int, int, int]] = {}
        self.last_custom_brightness: int = 20
        self.last_mode_type: str = "preset"
        layout_path = os.path.join(DATA_DIR, "layout.json")
        self.layout_keys: List[Dict[str, Any]] = []
        if os.path.exists(layout_path):
            with open(layout_path, "r", encoding="utf-8") as f:
                self.layout_keys = json.load(f)

    def get_mode_name(self, effect_id: int) -> str:
        for m in self.modes:
            if m["id"] == effect_id:
                return m["name"]
        return f"Mode {effect_id}"

    def build_profile_payload(self, config: LightingConfig) -> bytes:
        """Construct the 128-byte profile payload for SetLED (cmdId 0x04)."""
        deb = config.debounce if (config.debounce is not None and config.debounce in (1, 4)) else self.last_debounce
        sleep_m = config.sleep_minutes if (config.sleep_minutes is not None and config.sleep_minutes in (0, 10, 20, 40, 60)) else self.last_sleep_minutes

        buf = bytearray(128)
        buf[2] = deb
        buf[3] = deb
        buf[5] = 0x00
        is_off = (config.effect == 0 or config.brightness == 0)
        eff_brightness = 0 if is_off else (config.brightness & 0xFF)
        eff_id = 0 if is_off else (config.effect & 0xFF)

        buf[6] = eff_brightness
        buf[7] = config.speed & 0xFF
        buf[8] = config.palette_index & 0xFF
        buf[9] = 0x01 if eff_id in (18, 19) else 0x00  # 1 for Gaoshou custom mode, 0 for built-in
        buf[10] = eff_id
        if eff_id in (18, 19):
            buf[11] = 0x20
            buf[0x38] = 0xFF
            buf[0x39] = 0xFF

        buf[24] = sleep_m

        # Populate all slots with reasonable defaults so Fn key combos on keyboard never go dark
        for eff in range(1, 21):
            s_off = 56 + eff * 2
            if s_off + 1 < 128:
                buf[s_off] = 20 if not is_off else 0
                buf[s_off + 1] = (2 << 4) | 7

        # Effect parameter slot: offset = 56 + effect * 2
        eff_slot = config.effect if config.effect > 0 else 1
        offset = 56 + eff_slot * 2
        if offset + 1 < 128:
            buf[offset] = eff_brightness
            buf[offset + 1] = ((config.speed & 0x0F) << 4) | (config.palette_index & 0x0F)

        return bytes(buf)

    def get_color_table(self) -> Optional[bytearray]:
        """Read 420-byte color table from keyboard flash memory."""
        if not self.dev.fd:
            return None

        if self.dev.is_dongle:
            if not self.dev.is_awake():
                return None
            import select
            pkt = protocol.build_output_report(protocol.CMD_DONGLE_GET_LED_RGB_TAB)
            try:
                os.write(self.dev.fd, pkt)
                chunks = {}
                for _ in range(35):
                    ready, _, _ = select.select([self.dev.fd], [], [], 0.1)
                    if not ready:
                        break
                    p = os.read(self.dev.fd, 20)
                    if len(p) >= 20 and p[1] == protocol.CMD_DONGLE_GET_LED_RGB_TAB:
                        pkg_idx = p[3]
                        dlen = p[4] & 0x0F
                        chunks[pkg_idx] = p[5:5 + dlen]
                if chunks:
                    full_buf = bytearray()
                    for i in range(len(chunks)):
                        if i in chunks:
                            full_buf.extend(chunks[i])
                    if len(full_buf) >= 420:
                        self._cached_color_table = bytearray(full_buf[:420])
                        return self._cached_color_table
            except OSError:
                pass
        else:
            import fcntl
            from .device import _HIDIOCSFEATURE, _HIDIOCGFEATURE
            req = bytearray(protocol.REPORT_SIZE_WIRED)
            req[0] = protocol.REPORT_ID_WIRED
            req[1] = protocol.CMD_WIRED_GET_LED_RGB_TAB
            req[4] = 0x01
            req[6] = 420 & 0xFF
            req[7] = (420 >> 8) & 0xFF
            try:
                fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(req)), req)
                resp = bytearray(protocol.REPORT_SIZE_WIRED)
                resp[0] = protocol.REPORT_ID_WIRED
                fcntl.ioctl(self.dev.fd, _HIDIOCGFEATURE(len(resp)), resp)
                self._cached_color_table = bytearray(resp[8:8 + 420])
                return self._cached_color_table
            except OSError:
                pass

        return self._cached_color_table

    def set_color_table(self, tab: bytes | bytearray) -> bool:
        """Write 420-byte color table back to keyboard flash memory."""
        if not self.dev.fd or len(tab) < 420:
            return False

        payload = bytes(tab[:420])
        self._cached_color_table = bytearray(payload)

        if self.dev.is_dongle:
            total_bytes = len(payload)
            num_packages = (total_bytes + 13) // 14
            for pkg_idx in range(num_packages):
                start = pkg_idx * 14
                chunk = payload[start:start + 14]
                pkt = protocol.build_output_report(
                    protocol.CMD_DONGLE_SET_LED_RGB_TAB,
                    payload=chunk,
                    num_packages=num_packages,
                    package_index=pkg_idx
                )
                try:
                    os.write(self.dev.fd, pkt)
                except OSError:
                    return False
            return True
        else:
            import fcntl
            from .device import _HIDIOCSFEATURE
            buf = protocol.build_feature_report(protocol.CMD_WIRED_SET_LED_RGB_TAB, payload)
            buf[6] = 420 & 0xFF
            buf[7] = (420 >> 8) & 0xFF
            try:
                fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(buf)), buf)
                return True
            except OSError:
                return False

    def _commit_led_payload(self, payload: bytes | bytearray) -> bool:
        """Helper to send 128-byte profile payload to keyboard."""
        if not self.dev.fd:
            return False
        if self.dev.is_dongle:
            total_bytes = len(payload)
            num_packages = (total_bytes + 13) // 14
            for pkg_idx in range(num_packages):
                start = pkg_idx * 14
                chunk = payload[start:start + 14]
                pkt = protocol.build_output_report(
                    protocol.CMD_DONGLE_SET_LED,
                    payload=chunk,
                    num_packages=num_packages,
                    package_index=pkg_idx
                )
                try:
                    os.write(self.dev.fd, pkt)
                except OSError:
                    return False
            return True
        else:
            buf = protocol.build_feature_report(protocol.CMD_WIRED_SET_LED, payload)
            try:
                import fcntl
                from .device import _HIDIOCSFEATURE
                fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(buf)), buf)
                return True
            except OSError:
                return False

    def set_lighting(self, config: LightingConfig, custom_rgb: Optional[tuple[int, int, int]] = None) -> bool:
        """Apply lighting configuration to the keyboard, automatically updating the 420-byte flash table."""
        if 1 <= config.effect <= 17 and config.brightness > 0:
            self.last_preset_config = config
            self.last_mode_type = "preset"

        # Check if turning off
        if config.effect == 0 or config.brightness == 0:
            config.brightness = 0
            config.effect = 0
            payload = self.build_profile_payload(config)
            return self._commit_led_payload(payload)

        # 1. Update color table if not pure rainbow mode (palette_index != 7) or if custom_rgb provided
        if custom_rgb is not None or config.palette_index < 7:
            tab = self.get_color_table()
            if tab is None or len(tab) < 420:
                # Initialize default 420-byte table if read failed
                tab = bytearray(420)
                for eff in range(20):
                    for slot_idx, rgb in enumerate(DEFAULT_PALETTE_RGB):
                        base = eff * 21 + slot_idx * 3
                        tab[base] = rgb[0]
                        tab[base + 1] = rgb[1]
                        tab[base + 2] = rgb[2]

            table_dirty = False

            # Ensure all effects have default colors if they were uninitialized (zeroes)
            for eff in range(1, 18):
                base = eff * 21
                if all(b == 0 for b in tab[base:base + 21]):
                    for slot_idx, rgb in enumerate(DEFAULT_PALETTE_RGB):
                        s_offset = base + slot_idx * 3
                        tab[s_offset] = rgb[0]
                        tab[s_offset + 1] = rgb[1]
                        tab[s_offset + 2] = rgb[2]
                    table_dirty = True

            # Determine target slot and target RGB
            target_slot = config.palette_index if config.palette_index < 7 else 0
            if custom_rgb is not None:
                target_rgb = (
                    max(0, min(255, int(custom_rgb[0]))),
                    max(0, min(255, int(custom_rgb[1]))),
                    max(0, min(255, int(custom_rgb[2]))),
                )
                config.palette_index = target_slot
            else:
                target_rgb = DEFAULT_PALETTE_RGB[target_slot]
                for p in self.palette:
                    if p["id"] == target_slot and p.get("rgb"):
                        target_rgb = tuple(p["rgb"])
                        break

            slot_offset = config.effect * 21 + target_slot * 3
            if slot_offset + 2 < len(tab):
                current_rgb = (tab[slot_offset], tab[slot_offset + 1], tab[slot_offset + 2])
                if current_rgb != target_rgb:
                    tab[slot_offset] = target_rgb[0]
                    tab[slot_offset + 1] = target_rgb[1]
                    tab[slot_offset + 2] = target_rgb[2]
                    table_dirty = True

            if table_dirty:
                self.set_color_table(tab)

        # 2. Commit SetLED profile
        payload = self.build_profile_payload(config)
        return self._commit_led_payload(payload)

    def _build_key_matrix_map(self):
        """Build a comprehensive lookup map from key identifiers/aliases to matrix_idx."""
        key_map = {}
        for k in self.layout_keys:
            midx = k.get("matrix_idx")
            if midx is not None:
                kid = k.get("id", "")
                kname = k.get("name", "")
                if kid:
                    key_map[kid.upper()] = midx
                    key_map[kid.lower()] = midx
                if kname:
                    key_map[kname.upper()] = midx
                    key_map[kname.lower()] = midx

        aliases = {
            "ctrl": "LCtrl", "lctrl": "LCtrl", "rctrl": "RCtrl",
            "shift": "LShift", "lshift": "LShift", "rshift": "RShift",
            "win": "LWin", "lwin": "LWin", "cmd": "LWin", "super": "LWin",
            "alt": "LAlt", "lalt": "LAlt", "ralt": "RAlt",
            "caps": "CapsLock", "capslock": "CapsLock",
            "tab": "Tab", "esc": "Esc", "space": "Space", "spacebar": "Space",
            "back": "Backspace", "backspace": "Backspace", "bksp": "Backspace",
            "enter": "Enter", "return": "Enter",
            "cal": "Calc", "calc": "Calc",
            "print": "PrtSc", "prtsc": "PrtSc", "printscreen": "PrtSc",
            "scroll": "SrcLock", "srclock": "SrcLock", "scrolllock": "SrcLock",
            "pause": "Pause", "break": "Pause",
            "ins": "Insert", "insert": "Insert",
            "del": "Delete", "delete": "Delete",
            "home": "Home", "end": "End",
            "pgup": "PgUp", "pageup": "PgUp",
            "pgdn": "PgDn", "pagedown": "PgDn",
            "up": "Up", "down": "Down", "left": "Left", "right": "Right",
            "~": "`", "?": "/", "<": ",", ">": ".", "|": "\\",
            "app": "App", "menu": "App", "fn": "FN"
        }
        for alias, target in aliases.items():
            if target.upper() in key_map:
                midx = key_map[target.upper()]
                key_map[alias.lower()] = midx
                key_map[alias.upper()] = midx
        return key_map

    def resolve_key_matrix_index(self, key_ident):
        """Resolve a key string ID, name, alias, or index to hardware matrix_idx (0..101)."""
        if not hasattr(self, "_key_matrix_cache"):
            self._key_matrix_cache = self._build_key_matrix_map()

        if isinstance(key_ident, int):
            if 0 <= key_ident <= 125:
                return key_ident

        clean = str(key_ident).strip()
        if clean.isdigit():
            val = int(clean)
            if 0 <= val <= 125:
                return val

        if clean.upper() in self._key_matrix_cache:
            return self._key_matrix_cache[clean.upper()]
        if clean.lower() in self._key_matrix_cache:
            return self._key_matrix_cache[clean.lower()]

        return None

    @staticmethod
    def rgb_to_palette_id(r: int, g: int, b: int) -> int:
        """Map RGB tuple to SinoWealth 3-bit hardware palette color ID (1..7, or 0 if off).
        1 = Red, 2 = Green, 3 = Blue, 4 = Yellow, 5 = Pink, 6 = Cyan, 7 = White, 0 = Off
        """
        if r < 35 and g < 35 and b < 35:
            return 0  # Off
        palette_map = {
            1: (255, 0, 0),       # Red
            2: (0, 255, 0),       # Green
            3: (0, 0, 255),       # Blue
            4: (255, 255, 0),     # Yellow
            5: (255, 30, 220),    # Pink / Magenta
            6: (0, 255, 255),     # Cyan
            7: (255, 255, 255),   # White
        }
        best_id = 1
        best_dist = float("inf")
        for pid, (pr, pg, pb) in palette_map.items():
            dist = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
            if dist < best_dist:
                best_dist = dist
                best_id = pid
        return best_id

    def send_realtime_matrix_lighting(self, key_colors: Dict[str, Tuple[int, int, int]]) -> bool:
        """Stream real-time per-key LED colors via CMD_SET_GAME (0x06 wired / 0x02 dongle).
        
        Payload format: 378 bytes Planar RGB (0x17A)
        - Plane 0 (bytes 0..125): Red values (0..255)
        - Plane 1 (bytes 126..251): Green values (0..255)
        - Plane 2 (bytes 252..377): Blue values (0..255)
        """
        if not self.dev.fd:
            return False

        buf = bytearray(378)
        for key_ident, rgb in key_colors.items():
            midx = self.resolve_key_matrix_index(key_ident)
            if midx is not None and 0 <= midx < 126:
                r = max(0, min(255, int(rgb[0])))
                g = max(0, min(255, int(rgb[1])))
                b = max(0, min(255, int(rgb[2])))
                buf[midx] = r          # Red plane (0..125)
                buf[126 + midx] = g    # Green plane (126..251)
                buf[252 + midx] = b    # Blue plane (252..377)

        if not self.dev.is_dongle:
            import fcntl
            from .device import _HIDIOCSFEATURE
            game_req = protocol.build_feature_report(protocol.CMD_WIRED_SET_GAME, buf, board=1)
            game_req[6] = len(buf) & 0xFF
            game_req[7] = (len(buf) >> 8) & 0xFF
            try:
                fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(game_req)), game_req)
                return True
            except OSError:
                return False
        else:
            total_bytes = len(buf)
            num_packages = (total_bytes + 13) // 14
            for pkg_idx in range(num_packages):
                start = pkg_idx * 14
                chunk = buf[start:start + 14]
                pkt = protocol.build_output_report(
                    protocol.CMD_DONGLE_SET_GAME,
                    payload=chunk,
                    num_packages=num_packages,
                    package_index=pkg_idx,
                    board=1
                )
                try:
                    os.write(self.dev.fd, pkt)
                    import time
                    time.sleep(0.001)
                except OSError:
                    return False
            return True

    def enter_custom_matrix_mode(self, brightness: int = 20) -> bool:
        """Puts the keyboard into Self-define (Gaoshou) mode slot 18 with the specified brightness.
        Preserves debounce, sleep timeouts, language, and other hardware settings.
        """
        if not self.dev.fd:
            return False

        import time

        # 1. Read existing hardware profile to preserve debounce, sleep timeouts, language, and registers
        raw = self.get_raw_profile()
        if raw is not None and len(raw) >= 128 and not all(b == 0 for b in raw):
            prof = bytearray(raw)
        else:
            prof = bytearray(self.build_profile_payload(LightingConfig(effect=18, brightness=brightness, speed=2, palette_index=7)))

        # Preserve / enforce valid debounce and sleep registers
        deb = prof[2] if prof[2] in (1, 4) else (prof[3] if prof[3] in (1, 4) else self.last_debounce)
        sleep_m = prof[24] if prof[24] in (0, 10, 20, 40, 60) else self.last_sleep_minutes
        prof[2] = deb
        prof[3] = deb
        prof[24] = sleep_m

        # Set Self-define ("Gaoshou") parameters (Effect 18 per KB.ini GaoshouIndex=17)
        prof[6] = brightness & 0xFF
        prof[7] = 2
        prof[8] = 7
        prof[9] = 1    # Gaoshou custom light mode flag
        prof[10] = 18  # Effect 18: Self-define hardware slot
        prof[11] = 0x20 # Group 0 (0x20 + group)
        prof[0x38] = 0xFF
        prof[0x39] = 0xFF

        # Configure slot 18 parameter entry (offset = 56 + 18 * 2 = 92)
        offset = 56 + 18 * 2
        if offset + 1 < 128:
            prof[offset] = brightness & 0xFF
            prof[offset + 1] = (2 << 4) | 7
        # Also configure byte 94 (0x5E) as observed in official software
        if offset + 3 < 128:
            prof[offset + 2] = brightness & 0xFF
            prof[offset + 3] = (2 << 4) | 7

        ok = self._commit_led_payload(prof)

        # 2. Wait 150ms for microcontroller to settle into Self-define mode (matching 0x96 ms in official driver)
        time.sleep(0.15)
        return ok

    def set_custom_matrix_lighting(self, key_colors: Dict[str, Tuple[int, int, int]], brightness: int = 20) -> bool:
        """Apply custom per-key RGB colors to the keyboard ("Gaoshou" mode).
        
        Args:
            key_colors: Mapping of key ID ('K1'..'K94') or name ('W', 'Esc', 'Space') to (R, G, B).
            brightness: Master brightness level (0..20).
        """
        if not self.dev.fd:
            return False

        self.last_custom_key_colors = dict(key_colors)
        self.last_custom_brightness = brightness
        self.last_mode_type = "custom"

        if not self.enter_custom_matrix_mode(brightness):
            return False

        # Stream 378-byte planar RGB buffer to CMD_SET_GAME
        return self.send_realtime_matrix_lighting(key_colors)

    def get_custom_profiles_dir(self) -> str:
        d = os.path.join(DATA_DIR, "custom_profiles")
        os.makedirs(d, exist_ok=True)
        return d

    def list_custom_profiles(self) -> List[str]:
        d = self.get_custom_profiles_dir()
        profiles = []
        for f in sorted(os.listdir(d)):
            if f.endswith(".json"):
                profiles.append(f[:-5])
        return profiles

    def load_custom_profile(self, name: str) -> Optional[Dict[str, Any]]:
        d = self.get_custom_profiles_dir()
        filename = f"{name}.json" if not name.endswith(".json") else name
        path = os.path.join(d, filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def save_custom_profile(self, name: str, key_colors: Dict[str, Tuple[int, int, int]]) -> bool:
        d = self.get_custom_profiles_dir()
        safe_name = name.strip().replace("/", "_").replace("\\", "_")
        filename = f"{safe_name}.json" if not safe_name.endswith(".json") else safe_name
        path = os.path.join(d, filename)
        data = {
            "name": name.replace("_", " ").title(),
            "keys": {k: [int(v[0]), int(v[1]), int(v[2])] for k, v in key_colors.items()}
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception:
            return False

    def delete_custom_profile(self, name: str) -> bool:
        d = self.get_custom_profiles_dir()
        filename = f"{name}.json" if not name.endswith(".json") else name
        path = os.path.join(d, filename)
        if os.path.exists(path):
            try:
                os.remove(path)
                return True
            except OSError:
                pass
        return False

    def get_raw_profile(self) -> Optional[bytearray]:
        """Read the raw 128-byte hardware profile payload directly from the keyboard.
        
        Returns bytearray(128) or None if read failed, keyboard is asleep, or data is all zeroes.
        """
        if not self.dev.fd:
            return None

        if self.dev.is_dongle:
            if not self.dev.is_awake():
                return None
            import select
            pkt = protocol.build_output_report(protocol.CMD_DONGLE_GET_LED)
            try:
                os.write(self.dev.fd, pkt)
                chunks = {}
                for _ in range(16):
                    ready, _, _ = select.select([self.dev.fd], [], [], 0.15)
                    if not ready:
                        break
                    p = os.read(self.dev.fd, 20)
                    if len(p) >= 20 and p[1] == protocol.CMD_DONGLE_GET_LED:
                        pkg_idx = p[3]
                        dlen = p[4] & 0x0F
                        chunks[pkg_idx] = p[5:5 + dlen]

                if not chunks:
                    return None
                full_buf = bytearray()
                for i in range(len(chunks)):
                    if i in chunks:
                        full_buf.extend(chunks[i])
                if len(full_buf) < 128 or all(b == 0 for b in full_buf[:128]):
                    return None
                return bytearray(full_buf[:128])
            except OSError:
                return None
        else:
            # Wired mode: feature report 0x84
            import fcntl
            from .device import _HIDIOCSFEATURE, _HIDIOCGFEATURE
            req_buf = bytearray(protocol.REPORT_SIZE_WIRED)
            req_buf[0] = protocol.REPORT_ID_WIRED
            req_buf[1] = protocol.CMD_WIRED_GET_LED
            req_buf[4] = 0x01
            req_buf[6] = 128
            try:
                fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(req_buf)), req_buf)
                read_buf = bytearray(protocol.REPORT_SIZE_WIRED)
                read_buf[0] = protocol.REPORT_ID_WIRED
                fcntl.ioctl(self.dev.fd, _HIDIOCGFEATURE(len(read_buf)), read_buf)
                if read_buf[1] != protocol.CMD_WIRED_GET_LED:
                    return None
                prof = bytearray(read_buf[8:8 + 128])
                if all(b == 0 for b in prof):
                    return None
                return prof
            except OSError:
                return None

    def get_current_lighting(self) -> Optional[LightingConfig]:
        """Read the active hardware lighting state directly from the keyboard.

        Returns LightingConfig or None if reading failed or keyboard is asleep.
        """
        profile = self.get_raw_profile()
        if not profile:
            return None

        if profile[3] in (1, 4):
            debounce = profile[3]
        elif profile[2] in (1, 4):
            debounce = profile[2]
        else:
            debounce = self.last_debounce

        if profile[24] in (0, 10, 20, 40, 60):
            sleep_minutes = profile[24]
        else:
            sleep_minutes = self.last_sleep_minutes

        self.last_debounce = debounce
        self.last_sleep_minutes = sleep_minutes

        # Check if lighting is turned off
        if profile[6] == 0 or profile[10] == 0:
            return LightingConfig(
                effect=0,
                brightness=0,
                speed=profile[7] if profile[7] <= 4 else 2,
                palette_index=profile[8] if profile[8] <= 7 else 7,
                debounce=debounce,
                sleep_minutes=sleep_minutes,
            )

        # Parse profile: byte 10 is active effect ID
        effect_id = profile[10]
        offset = 56 + effect_id * 2
        if offset + 1 < len(profile) and profile[offset] > 0:
            brightness = profile[offset]
            speed = (profile[offset + 1] >> 4) & 0x0F
            palette_idx = profile[offset + 1] & 0x0F
        elif profile[6] > 0:
            brightness = profile[6]
            speed = profile[7]
            palette_idx = profile[8]
        else:
            brightness, speed, palette_idx = 0, 2, 7

        cfg = LightingConfig(
            effect=effect_id,
            brightness=brightness,
            speed=speed,
            palette_index=palette_idx,
            debounce=debounce,
            sleep_minutes=sleep_minutes,
        )
        if 1 <= effect_id <= 17 and brightness > 0:
            if self.last_preset_config is None or self.last_mode_type == "preset":
                self.last_preset_config = cfg
        elif effect_id in (18, 19) or profile[9] == 1:
            self.last_mode_type = "custom"

        return cfg

    def restore_lighting(self) -> bool:
        """Restore active lighting (preset or custom per-key) previously set or read from hardware."""
        if self.last_mode_type == "custom" and self.last_custom_key_colors:
            return self.set_custom_matrix_lighting(self.last_custom_key_colors, self.last_custom_brightness)
        elif self.last_preset_config is not None:
            return self.set_lighting(self.last_preset_config)
        else:
            return self.set_lighting(LightingConfig(effect=1, brightness=20, speed=2, palette_index=7))

    def restore_preset_lighting(self) -> bool:
        """Restore persistent hardware preset effect (modes 1..17)."""
        cfg = self.last_preset_config or LightingConfig(effect=1, brightness=20, speed=2, palette_index=7)
        return self.set_lighting(cfg)

    def set_hardware_options(self, debounce: int, sleep_minutes: int) -> bool:
        """Update debounce filter (1ms Gaming vs 4ms Office) and wireless sleep timeout in hardware.
        
        Preserves the user's current lighting state (even if LEDs are completely off).
        """
        target_debounce = debounce if debounce in (1, 4) else 4
        target_sleep = sleep_minutes if sleep_minutes in (0, 10, 20, 40, 60) else 10
        self.last_debounce = target_debounce
        self.last_sleep_minutes = target_sleep

        # 1. Modify the hardware's existing profile in-place to avoid altering user's lighting state
        raw = self.get_raw_profile()
        if raw is not None:
            raw[2] = target_debounce
            raw[3] = target_debounce
            raw[24] = target_sleep
            return self._commit_led_payload(raw)

        # 2. Fallback only if hardware read completely failed
        cfg = self.get_current_lighting()
        if not cfg:
            cfg = LightingConfig(effect=1, brightness=20, speed=2, palette_index=7)
        cfg.debounce = target_debounce
        cfg.sleep_minutes = target_sleep
        return self.set_lighting(cfg)

    def reset_keyboard_data(self, keymap_mgr=None) -> bool:
        """Safely restore on-device key mapping scancodes, lighting profiles, and color tables to factory defaults."""
        import time

        ok_matrix = True
        # 1. Reset all 4 key matrix layers to verified golden factory defaults
        if keymap_mgr:
            ok_matrix = keymap_mgr.reset_to_defaults()
            time.sleep(0.04)

        # 2. Reset 420-byte color table to clean factory defaults
        tab = bytearray(420)
        for eff in range(20):
            for slot_idx, rgb in enumerate(DEFAULT_PALETTE_RGB):
                base = eff * 21 + slot_idx * 3
                tab[base] = rgb[0]
                tab[base + 1] = rgb[1]
                tab[base + 2] = rgb[2]
        self.set_color_table(tab)
        time.sleep(0.04)

        # 3. Reset lighting config to default Rainbow, full brightness 20, Office mode debounce (4ms), 10m sleep
        default_cfg = LightingConfig(effect=1, brightness=20, speed=2, palette_index=7, debounce=4, sleep_minutes=10)
        ok_light = self.set_lighting(default_cfg)

        return ok_matrix and ok_light


