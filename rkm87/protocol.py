"""Protocol definitions for Royal Kludge M87 (SinoWealth).

Reverse engineered from DeviceDriver.exe and live Linux hardware probing.
Supports both:
- 2.4 GHz Dongle (PID 0x0150): CDev3632 protocol, 20-byte Output Reports (Report ID 0x13)
- USB Cable (PID 0x01A2): CDevG5KB protocol, 520-byte Feature Reports (Report ID 0x09)
"""

import struct
from datetime import datetime

VID = 0x258A
PID_DONGLE = 0x0150
PID_WIRED = 0x01A2

REPORT_ID_DONGLE = 0x13
REPORT_SIZE_DONGLE = 20

REPORT_ID_WIRED = 0x09
REPORT_SIZE_WIRED = 520

# Command IDs for Dongle mode (CDev3632)
CMD_DONGLE_SET_MATRIX = 0x01
CMD_DONGLE_SET_GAME = 0x02
CMD_DONGLE_SET_MACRO = 0x03
CMD_DONGLE_SET_LED = 0x04
CMD_DONGLE_GET_STATUS = 0x07
CMD_DONGLE_SET_LED_RGB_TAB = 0x09
CMD_DONGLE_SET_SCREEN_PARAM = 0x0B
CMD_DONGLE_GET_MATRIX = 0x41
CMD_DONGLE_GET_LED = 0x44
CMD_DONGLE_GET_LED_RGB_TAB = 0x49
CMD_DONGLE_GET_VERSION = 0x4A
CMD_DONGLE_SET_REAL_DATA = 0x88

# Command IDs for Wired mode (CDevG5KB)
CMD_WIRED_SET_MATRIX = 0x03
CMD_WIRED_SET_LED = 0x04
CMD_WIRED_SET_MACRO = 0x05
CMD_WIRED_SET_GAME = 0x06
CMD_WIRED_SET_LED_RGB_TAB = 0x0A
CMD_WIRED_SET_SCREEN_PARAM = 0x0B
CMD_WIRED_ACCESS_DATA_PAGE = 0x0C
CMD_WIRED_SET_GIF_PARAM = 0x0D
CMD_WIRED_GET_PASSWORD = 0x82
CMD_WIRED_GET_MATRIX = 0x83
CMD_WIRED_GET_LED = 0x84
CMD_WIRED_SET_REAL_DATA = 0x88
CMD_WIRED_GET_LED_RGB_TAB = 0x8A

# Screen specs for M87
SCREEN_WIDTH = 240
SCREEN_HEIGHT = 135
SCREEN_MAX_FRAMES = 100
SCREEN_CHUNK_SIZE = 512

# Standard palette
PALETTE = {
    0: ("Red", (255, 0, 0)),
    1: ("Green", (0, 255, 0)),
    2: ("Blue", (0, 0, 255)),
    3: ("Yellow", (255, 255, 0)),
    4: ("Pink", (255, 50, 130)),
    5: ("Cyan", (0, 255, 255)),
    6: ("White", (255, 255, 255)),
    7: ("Multicolor / Rainbow", None),
}


def crc8(packet: bytes | bytearray) -> int:
    """Calculate 8-bit additive checksum for 20-byte dongle packet."""
    return sum(packet[:19]) & 0xFF


def build_output_report(cmd_id: int, payload: bytes = b"", num_packages: int = 1, package_index: int = 0, board: int = 0) -> bytes:
    """Build a 20-byte CDev3632 output report for 2.4GHz dongle (Report ID 0x13)."""
    pkt = bytearray(REPORT_SIZE_DONGLE)
    pkt[0] = REPORT_ID_DONGLE
    pkt[1] = cmd_id
    pkt[2] = num_packages & 0xFF
    pkt[3] = package_index & 0xFF
    data_len = min(14, len(payload))
    pkt[4] = ((board & 0x0F) << 4) | (data_len & 0x0F)
    if data_len > 0:
        pkt[5:5 + data_len] = payload[:data_len]
    pkt[19] = crc8(pkt)
    return bytes(pkt)


def build_feature_report(cmd_id: int, payload: bytes = b"", num_packages: int = 1, package_index: int = 0, board: int = 0) -> bytearray:
    """Build a 520-byte CDevG5KB feature report for USB cable (Report ID 0x09)."""
    buf = bytearray(REPORT_SIZE_WIRED)
    buf[0] = REPORT_ID_WIRED
    buf[1] = cmd_id
    buf[2] = board & 0xFF
    buf[3] = 0x00  # reserved
    buf[4] = num_packages & 0xFF
    buf[5] = package_index & 0xFF
    data_len = len(payload)
    buf[6] = data_len & 0xFF
    buf[7] = (data_len >> 8) & 0xFF
    if data_len > 0:
        buf[8:8 + data_len] = payload[:512]
    return buf


def build_sysparam_payload(volume: int, dt: datetime | None = None) -> bytes:
    """Build the 14-byte SysParam payload for screen time & volume synchronization."""
    if dt is None:
        dt = datetime.now()
    volume = max(0, min(100, int(volume)))
    year = dt.year
    dow = (dt.weekday() + 1) % 7  # Python Mon=0..Sun=6 -> Windows Sun=0..Sat=6

    payload = bytearray(14)
    payload[0] = volume
    payload[1] = 0x00  # CPU (ignored by M87)
    payload[2] = 0x00  # RAM (ignored by M87)
    payload[3] = year & 0xFF
    payload[4] = (year >> 8) & 0xFF
    payload[5] = dt.month
    payload[6] = dt.day
    payload[7] = dt.hour
    payload[8] = dt.minute
    payload[9] = dt.second
    payload[10] = dow
    return bytes(payload)


def build_gif_param_payload(mode: int, frame_count: int, delay_ms: int) -> bytes:
    """Build the 5-byte SetGIFParam payload (cmdId 0x0D).
    mode: 0=finish, 1=start, 2=abort
    """
    payload = bytearray(5)
    payload[0] = (mode & 0x03) << 6
    payload[1] = frame_count & 0xFF
    payload[2] = (frame_count >> 8) & 0xFF
    payload[3] = delay_ms & 0xFF
    payload[4] = (delay_ms >> 8) & 0xFF
    return bytes(payload)


def build_page_chunk_payload(frame_index: int, page_index: int, chunk_data: bytes) -> bytes:
    """Build the header + payload for AccessData_Page (cmdId 0x0C).
    Format:
    [0] board=0
    [1] frameIdx
    [2] pageIdx
    [3] CRC: (-1 - sum(chunk_data)) & 0xFF
    [4..5] dataLen LE
    [6..] chunk_data
    """
    crc_val = (-1 - sum(chunk_data)) & 0xFF
    hdr = struct.pack("<BBBBH", 0, frame_index, page_index, crc_val, len(chunk_data))
    return hdr + chunk_data
