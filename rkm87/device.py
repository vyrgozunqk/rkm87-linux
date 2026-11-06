"""Hardware device connection and transport management for RK M87."""

import fcntl
import os
import select
import sys
from datetime import datetime
from typing import Optional

from . import protocol

_IOC_WRITE = 1
_IOC_READ = 2


def _HIDIOCSFEATURE(size: int) -> int:
    return ((_IOC_WRITE | _IOC_READ) << 30) | (size << 16) | (ord("H") << 8) | 0x06


def _HIDIOCGFEATURE(size: int) -> int:
    return ((_IOC_WRITE | _IOC_READ) << 30) | (size << 16) | (ord("H") << 8) | 0x07


class RKDevice:
    def __init__(self, dev_path: Optional[str] = None):
        self.dev_path = dev_path
        self.pid: Optional[int] = None
        self.is_dongle: bool = False
        self.fd: Optional[int] = None

    def discover(self) -> bool:
        """Scan /sys/class/hidraw for RK M87 vendor config interface (input1)."""
        sysfs = "/sys/class/hidraw"
        if not os.path.isdir(sysfs):
            return False

        wired_path = None
        dongle_path = None

        for entry in sorted(os.listdir(sysfs)):
            uevent_path = os.path.join(sysfs, entry, "device", "uevent")
            try:
                with open(uevent_path) as f:
                    uevent = f.read().upper()
            except OSError:
                continue

            if "0000258A" not in uevent:
                continue

            # Check for input1 (vendor configuration interface)
            is_input1 = False
            for line in uevent.splitlines():
                if line.startswith("HID_PHYS=") and line.endswith("/INPUT1"):
                    is_input1 = True
                    break

            if not is_input1:
                continue

            if "0000258A:000001A2" in uevent:
                wired_path = f"/dev/{entry}"
            elif "0000258A:00000150" in uevent:
                dongle_path = f"/dev/{entry}"

        # Prioritize Wired mode over Dongle mode
        if wired_path:
            self.pid = protocol.PID_WIRED
            self.is_dongle = False
            self.dev_path = wired_path
            return True
        elif dongle_path:
            self.pid = protocol.PID_DONGLE
            self.is_dongle = True
            self.dev_path = dongle_path
            return True

        return False

    def poll_hotplug(self) -> bool:
        """Check for hotplug changes: prioritize Wired (0x01A2) over Dongle (0x0150).
        Automatically switches if cable is connected or disconnected.
        """
        sysfs = "/sys/class/hidraw"
        if not os.path.isdir(sysfs):
            return self.fd is not None

        wired_path = None
        dongle_path = None

        for entry in sorted(os.listdir(sysfs)):
            uevent_path = os.path.join(sysfs, entry, "device", "uevent")
            try:
                with open(uevent_path) as f:
                    uevent = f.read().upper()
            except OSError:
                continue

            if "0000258A" not in uevent:
                continue

            is_input1 = False
            for line in uevent.splitlines():
                if line.startswith("HID_PHYS=") and line.endswith("/INPUT1"):
                    is_input1 = True
                    break

            if not is_input1:
                continue

            if "0000258A:000001A2" in uevent:
                wired_path = f"/dev/{entry}"
            elif "0000258A:00000150" in uevent:
                dongle_path = f"/dev/{entry}"

        best_path = wired_path or dongle_path
        best_pid = protocol.PID_WIRED if wired_path else (protocol.PID_DONGLE if dongle_path else None)
        best_dongle = (wired_path is None and dongle_path is not None)

        if best_path and (best_path != self.dev_path or self.fd is None):
            self.close()
            self.dev_path = best_path
            self.pid = best_pid
            self.is_dongle = best_dongle
            return self.open()

        return self.fd is not None

    def open(self) -> bool:
        """Open hidraw device."""
        if not self.dev_path:
            if not self.discover():
                return False

        try:
            self.fd = os.open(self.dev_path, os.O_RDWR | os.O_NONBLOCK)
            return True
        except (PermissionError, OSError) as e:
            print(f"Error opening {self.dev_path}: {e}", file=sys.stderr)
            return False

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def is_awake(self) -> bool:
        """Check if keyboard is awake and responding to wireless commands."""
        if self.fd is None:
            return False
        if not self.is_dongle:
            return True

        # Send GetDongleStatus (0x07)
        pkt = protocol.build_output_report(protocol.CMD_DONGLE_GET_STATUS)
        try:
            os.write(self.fd, pkt)
            ready, _, _ = select.select([self.fd], [], [], 0.3)
            if not ready:
                return False
            resp = os.read(self.fd, 20)
            if len(resp) >= 6 and resp[1] == protocol.CMD_DONGLE_GET_STATUS:
                return resp[5] == 1  # 1 = awake, 0 = asleep
            return False
        except OSError:
            return False

    def sync_time_and_volume(self, volume: int, dt: Optional[datetime] = None) -> bool:
        """Send SysParam (0x0B) to update screen clock and volume."""
        if self.fd is None:
            return False

        payload = protocol.build_sysparam_payload(volume, dt)
        if self.is_dongle:
            pkt = protocol.build_output_report(protocol.CMD_DONGLE_SET_SCREEN_PARAM, payload)
            try:
                os.write(self.fd, pkt)
                ready, _, _ = select.select([self.fd], [], [], 0.3)
                if ready:
                    resp = os.read(self.fd, 20)
                    return len(resp) >= 2 and (resp[1] & 0x7F) == protocol.CMD_DONGLE_SET_SCREEN_PARAM
                return True
            except OSError:
                return False
        else:
            buf = protocol.build_feature_report(protocol.CMD_WIRED_SET_SCREEN_PARAM, payload)
            try:
                fcntl.ioctl(self.fd, _HIDIOCSFEATURE(len(buf)), buf)
                return True
            except OSError:
                return False

    def send_real_data(self, data: bytes) -> bool:
        """Stream real-time LED data for live audio/music visualization (cmdId 0x88)."""
        if self.fd is None:
            return False

        if self.is_dongle:
            pkt = protocol.build_output_report(protocol.CMD_DONGLE_SET_REAL_DATA, data)
            try:
                os.write(self.fd, pkt)
                return True
            except OSError:
                return False
        else:
            buf = protocol.build_feature_report(protocol.CMD_WIRED_SET_REAL_DATA, data)
            try:
                fcntl.ioctl(self.fd, _HIDIOCSFEATURE(len(buf)), buf)
                return True
            except OSError:
                return False
