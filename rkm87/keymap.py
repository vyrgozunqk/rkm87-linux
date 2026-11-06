"""Key Remapping and Macro Manager for Royal Kludge M87."""

import json
import os
import struct
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from . import protocol
from .device import RKDevice, _HIDIOCSFEATURE

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# Media / Consumer key usage codes (USB HID Usage Page 0x0C)
MEDIA_KEYS = {
    "Play / Pause": 0x00B7,
    "Next Track": 0x00B5,
    "Previous Track": 0x00B6,
    "Stop Track": 0x00B7,
    "Volume Up": 0x00E9,
    "Volume Down": 0x00EA,
    "Mute": 0x00E2,
    "Calculator": 0x0192,
    "File Explorer (My PC)": 0x0194,
    "Default Mail": 0x018A,
    "Web Browser Home": 0x0223,
    "Web Search": 0x0221,
    "Web Refresh": 0x0227,
}

# Mouse buttons
MOUSE_BUTTONS = {
    "Mouse Left Click": 0x01,
    "Mouse Right Click": 0x02,
    "Mouse Middle Click": 0x04,
}

# Common HID key codes
HID_KEYS = {
    "A": 0x04, "B": 0x05, "C": 0x06, "D": 0x07, "E": 0x08, "F": 0x09,
    "G": 0x0A, "H": 0x0B, "I": 0x0C, "J": 0x0D, "K": 0x0E, "L": 0x0F,
    "M": 0x10, "N": 0x11, "O": 0x12, "P": 0x13, "Q": 0x14, "R": 0x15,
    "S": 0x16, "T": 0x17, "U": 0x18, "V": 0x19, "W": 0x1A, "X": 0x1B,
    "Y": 0x1C, "Z": 0x1D,
    "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21, "5": 0x22,
    "6": 0x23, "7": 0x24, "8": 0x25, "9": 0x26, "0": 0x27,
    "Enter": 0x28, "Escape": 0x29, "Backspace": 0x2A, "Tab": 0x2B, "Space": 0x2C,
    "Minus": 0x2D, "Equal": 0x2E, "Left Bracket": 0x2F, "Right Bracket": 0x30,
    "Backslash": 0x31, "Semicolon": 0x33, "Quote": 0x34, "Grave": 0x35,
    "Comma": 0x36, "Period": 0x37, "Slash": 0x38, "Caps Lock": 0x39,
    "F1": 0x3A, "F2": 0x3B, "F3": 0x3C, "F4": 0x3D, "F5": 0x3E, "F6": 0x3F,
    "F7": 0x40, "F8": 0x41, "F9": 0x42, "F10": 0x43, "F11": 0x44, "F12": 0x45,
    "Print Screen": 0x46, "Scroll Lock": 0x47, "Pause": 0x48, "Insert": 0x49,
    "Home": 0x4A, "Page Up": 0x4B, "Delete": 0x4C, "End": 0x4D, "Page Down": 0x4E,
    "Right Arrow": 0x4F, "Left Arrow": 0x50, "Down Arrow": 0x51, "Up Arrow": 0x52,
    "Left Ctrl": 0xE0, "Left Shift": 0xE1, "Left Alt": 0xE2, "Left GUI": 0xE3,
    "Right Ctrl": 0xE4, "Right Shift": 0xE5, "Right Alt": 0xE6, "Right GUI": 0xE7,
}


@dataclass
class KeyBinding:
    action_type: str = "default"  # default, hid_key, media, mouse, macro, disabled
    target: str = ""              # Key name, media name, or macro name
    code: int = 0
    macro_id: int = 0


@dataclass
class MacroEvent:
    hid_code: int
    is_down: bool
    delay_ms: int = 50


@dataclass
class Macro:
    name: str
    id: int
    repeat: int = 1
    events: List[MacroEvent] = field(default_factory=list)


class KeyMappingManager:
    def __init__(self, dev: RKDevice):
        self.dev = dev
        self.layout_keys: List[Dict] = []
        self.bindings: Dict[str, KeyBinding] = {}  # key_id -> KeyBinding
        self.macros: Dict[int, Macro] = {}
        self._load_layout()

    def _load_layout(self):
        layout_path = os.path.join(DATA_DIR, "layout.json")
        if os.path.exists(layout_path):
            with open(layout_path, "r", encoding="utf-8") as f:
                self.layout_keys = json.load(f)
        for k in self.layout_keys:
            self.bindings[k["id"]] = KeyBinding(action_type="default", target=k["name"])

    def remap_key(self, key_id: str, action_type: str, target: str, code: int = 0, macro_id: int = 0):
        self.bindings[key_id] = KeyBinding(
            action_type=action_type,
            target=target,
            code=code,
            macro_id=macro_id
        )

    def reset_key(self, key_id: str):
        for k in self.layout_keys:
            if k["id"] == key_id:
                self.bindings[key_id] = KeyBinding(action_type="default", target=k["name"])
                break

    def reset_all(self):
        for k in self.layout_keys:
            self.bindings[k["id"]] = KeyBinding(action_type="default", target=k["name"])

    def encode_key_dword(self, k_info: Dict, binding: KeyBinding) -> int:
        """Encode a key assignment into the 4-byte matrix entry."""
        if binding.action_type == "disabled":
            return 0x00000000

        if binding.action_type == "media":
            code = binding.code or MEDIA_KEYS.get(binding.target, 0)
            return ((code & 0xFF) << 24) | (((code >> 8) & 0xFF) << 16) | 0x0002

        if binding.action_type == "mouse":
            btn = binding.code or MOUSE_BUTTONS.get(binding.target, 0x01)
            return (0x01 << 16) | (btn << 8) | 0x01

        if binding.action_type == "macro":
            return ((binding.macro_id & 0xFF) << 8) | 0x04

        if binding.action_type == "hid_key":
            code = binding.code or HID_KEYS.get(binding.target, 0)
            # Modifier keys in SinoWealth matrix use (mask << 8):
            # LCtrl=0x100, LShift=0x200, LAlt=0x400, LWin=0x800,
            # RCtrl=0x1000, RShift=0x2000, RAlt=0x4000
            MODIFIERS = {
                0xE0: 0x0100, 0xE1: 0x0200, 0xE2: 0x0400, 0xE3: 0x0800,
                0xE4: 0x1000, 0xE5: 0x2000, 0xE6: 0x4000,
            }
            if code in MODIFIERS:
                return MODIFIERS[code]
            return (code << 24)

        # Default: default key binding from layout.json / golden matrix
        if "default_dword" in k_info and k_info["default_dword"] is not None:
            return k_info["default_dword"]

        name = k_info.get("name", "")
        hid_code = HID_KEYS.get(name, 0)
        return (hid_code << 24)

    def build_matrix_buffer(self, layer: int = 0) -> bytes:
        """Build the 504-byte (126-dword) matrix buffer for the specified layer."""
        golden_path = os.path.join(DATA_DIR, "default_matrix_layers.json")
        payload = bytearray(504)
        if os.path.exists(golden_path):
            try:
                with open(golden_path, "r", encoding="utf-8") as f:
                    layers = json.load(f)
                    if str(layer) in layers:
                        payload[:504] = bytes(layers[str(layer)])[:504]
            except Exception:
                pass

        # If custom keybindings exist, apply them onto Layer 0
        if layer == 0:
            for k in self.layout_keys:
                slot = k.get("matrix_idx", 0)
                if 0 <= slot < 126:
                    binding = self.bindings.get(k["id"])
                    if binding and binding.action_type != "default":
                        dw = self.encode_key_dword(k, binding)
                        struct.pack_into("<I", payload, slot * 4, dw)

        return bytes(payload)

    def send_raw_matrix_layer(self, layer: int, payload: bytes) -> bool:
        """Send a single 504-byte matrix layer to the keyboard hardware."""
        if not self.dev.fd:
            return False

        if len(payload) != 504:
            buf = bytearray(504)
            buf[:len(payload)] = payload[:504]
            payload = bytes(buf)

        if self.dev.is_dongle:
            # 504 bytes divided into 14-byte chunks (36 packages)
            total_bytes = len(payload)
            num_packages = (total_bytes + 13) // 14
            for pkg_idx in range(num_packages):
                start = pkg_idx * 14
                chunk = payload[start:start + 14]
                pkt = protocol.build_output_report(
                    protocol.CMD_DONGLE_SET_MATRIX,
                    payload=chunk,
                    num_packages=num_packages,
                    package_index=pkg_idx,
                    board=layer
                )
                try:
                    os.write(self.dev.fd, pkt)
                    time.sleep(0.003)
                except OSError:
                    return False
            return True
        else:
            # Wired mode: 1 feature report with num_packages=1, pkg_idx=0, data_len=504
            buf = protocol.build_feature_report(
                protocol.CMD_WIRED_SET_MATRIX,
                payload=payload,
                num_packages=1,
                package_index=0,
                board=layer
            )
            try:
                import fcntl
                fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(buf)), buf)
                return True
            except OSError:
                return False

    def apply_matrix(self) -> bool:
        """Send the active Layer 0 matrix to the keyboard."""
        payload = self.build_matrix_buffer(layer=0)
        return self.send_raw_matrix_layer(0, payload)

    def reset_to_defaults(self) -> bool:
        """Restore all 4 hardware matrix layers directly from the verified golden factory matrix dump."""
        golden_path = os.path.join(DATA_DIR, "default_matrix_layers.json")
        if not os.path.exists(golden_path):
            return False

        with open(golden_path, "r", encoding="utf-8") as f:
            layers = json.load(f)

        self.bindings.clear()
        self._load_layout()

        all_ok = True
        for layer_str, data in layers.items():
            layer_idx = int(layer_str)
            payload = bytes(data)
            ok = self.send_raw_matrix_layer(layer_idx, payload)
            if not ok:
                all_ok = False
            time.sleep(0.03)

        return all_ok

    def build_macro_payload(self, macro: Macro) -> bytes:
        """Encode macro events into SinoWealth binary format."""
        buf = bytearray()
        buf.append(macro.repeat & 0xFF)
        buf.append(len(macro.events) & 0xFF)

        for ev in macro.events[:64]:
            code = ev.hid_code & 0x7F
            state = 0x80 if ev.is_down else 0x00
            delay_10ms = min(127, ev.delay_ms // 10)
            buf.append(code | state)
            buf.append(delay_10ms)

        # Pad to at least 128 bytes
        while len(buf) < 128:
            buf.append(0)
        return bytes(buf[:128])

    def apply_macro(self, macro: Macro) -> bool:
        """Upload a recorded macro to the keyboard."""
        if not self.dev.fd:
            return False

        payload = self.build_macro_payload(macro)
        if self.dev.is_dongle:
            total_bytes = len(payload)
            num_packages = (total_bytes + 13) // 14
            for pkg_idx in range(num_packages):
                start = pkg_idx * 14
                chunk = payload[start:start + 14]
                pkt = protocol.build_output_report(
                    protocol.CMD_DONGLE_SET_MACRO,
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
            buf = protocol.build_feature_report(protocol.CMD_WIRED_SET_MACRO, payload)
            try:
                import fcntl
                fcntl.ioctl(self.dev.fd, _HIDIOCSFEATURE(len(buf)), buf)
                return True
            except OSError:
                return False


# Convenient alias
KeymapManager = KeyMappingManager

