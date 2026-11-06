"""Interactive 2D Keyboard Canvas for RK M87."""

import json
import math
import os
import time
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


class KeyboardCanvas(QWidget):
    ORIGINAL_W = 762
    ORIGINAL_H = 332
    key_clicked = Signal(str)  # emits key_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(700, 305)

        # Load layout
        self.keys = []
        layout_path = os.path.join(DATA_DIR, "layout.json")
        if os.path.exists(layout_path):
            with open(layout_path, "r", encoding="utf-8") as f:
                self.keys = json.load(f)

        # Load backdrop
        bg_path = os.path.join(DATA_DIR, "kbled.png")
        self.pixmap_bg = QPixmap(bg_path) if os.path.exists(bg_path) else None

        # Build canonical alias lookup map
        self._key_ident_map: Dict[str, str] = {}
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
        for k in self.keys:
            kid = k.get("id", "")
            kname = k.get("name", "")
            if kid:
                self._key_ident_map[kid.upper()] = kid
                self._key_ident_map[kid.lower()] = kid
            if kname:
                self._key_ident_map[kname.upper()] = kid
                self._key_ident_map[kname.lower()] = kid
        for alias, target in aliases.items():
            if target.upper() in self._key_ident_map:
                cid = self._key_ident_map[target.upper()]
                self._key_ident_map[alias.lower()] = cid
                self._key_ident_map[alias.upper()] = cid

        # Per-key colors and effect state
        self.key_colors: Dict[str, QColor] = {}
        self.active_mode = 1
        self.active_palette_color = QColor(0, 255, 230)
        self.is_rainbow = True
        self.is_custom_mode = False
        self.is_music_mode = False
        self.selection_enabled = False
        self.selected_keys = set()
        self.animation_phase = 0.0

        # Animation timer (30 FPS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate_tick)
        self.timer.start(33)

    def _animate_tick(self):
        self.animation_phase += 0.05
        if self.animation_phase > 2 * math.pi:
            self.animation_phase -= 2 * math.pi
        self.update()

    def set_lighting_state(self, effect_id: int, color: Optional[Tuple[int, int, int]], is_rainbow: bool):
        self.active_mode = effect_id
        self.is_rainbow = is_rainbow
        self.is_custom_mode = False
        self.is_music_mode = False
        if color:
            self.active_palette_color = QColor(*color)
        self.update()

    def set_custom_colors(self, colors: Dict[str, Tuple[int, int, int]]):
        """Set per-key colors for custom or music mode."""
        self.key_colors.clear()
        for k, rgb in colors.items():
            clean = str(k).strip()
            cid = self._key_ident_map.get(clean.upper()) or self._key_ident_map.get(clean.lower()) or clean
            self.key_colors[cid] = QColor(rgb[0], rgb[1], rgb[2])
        self.update()

    def set_custom_mode(self, enabled: bool):
        self.is_custom_mode = enabled
        self.update()

    def set_music_mode(self, enabled: bool):
        self.is_music_mode = enabled
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Calculate scale and centered offset
        scale_x = self.width() / self.ORIGINAL_W
        scale_y = self.height() / self.ORIGINAL_H
        scale = min(scale_x, scale_y)

        draw_w = self.ORIGINAL_W * scale
        draw_h = self.ORIGINAL_H * scale
        offset_x = (self.width() - draw_w) / 2
        offset_y = (self.height() - draw_h) / 2

        # Draw dark canvas background
        painter.fillRect(self.rect(), QColor("#121214"))

        # Draw keyboard backdrop
        if self.pixmap_bg and not self.pixmap_bg.isNull():
            target_rect = QRectF(offset_x, offset_y, draw_w, draw_h)
            painter.drawPixmap(target_rect, self.pixmap_bg, QRectF(0, 0, self.ORIGINAL_W, self.ORIGINAL_H))

        # Font for key labels
        font = QFont("Sans-serif", max(6, int(8 * scale)), QFont.Bold)
        painter.setFont(font)

        # Draw all keys with lighting effects
        for k in self.keys:
            r = k["rect"]
            x = offset_x + r[0] * scale
            y = offset_y + r[1] * scale
            w = (r[2] - r[0]) * scale
            h = (r[3] - r[1]) * scale
            key_rect = QRectF(x, y, w, h)

            # Compute key lighting color based on effect
            glow_color = self._compute_key_color(k, r[0], r[1])
            is_selected = k["id"] in self.selected_keys and self.selection_enabled

            # Draw key background
            if is_selected:
                painter.setPen(QPen(QColor("#38bdf8"), 2.2 * scale))
                key_bg = QColor(25, 45, 65, 230)
            else:
                border_col = glow_color.lighter(130) if self.active_mode != 0 else QColor(50, 50, 55)
                painter.setPen(QPen(border_col, 1.2))
                key_bg = QColor(30, 32, 38, 200)

            painter.setBrush(QBrush(key_bg))
            painter.drawRoundedRect(key_rect, 3 * scale, 3 * scale)

            # Draw inner key glow if lit
            if self.active_mode != 0 or self.is_custom_mode or self.is_music_mode:
                if glow_color.red() > 20 or glow_color.green() > 20 or glow_color.blue() > 20:
                    glow_fill = QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 60)
                    painter.fillRect(key_rect.adjusted(1, 1, -1, -1), glow_fill)

            # Draw key label
            if self.active_mode == 0 and not (self.is_custom_mode or self.is_music_mode):
                painter.setPen(QPen(QColor(100, 100, 110)))
            elif is_selected:
                painter.setPen(QPen(QColor("#ffffff")))
            else:
                painter.setPen(QPen(glow_color.lighter(170)))

            text = k.get("name", "")
            # Shorten labels if needed
            if len(text) > 5 and not text.startswith("F"):
                text = text[:4] + "."
            painter.drawText(key_rect, Qt.AlignCenter, text)

    def _compute_key_color(self, key_info, px, py) -> QColor:
        """Compute visual color of key based on active animation and position."""
        # Custom Per-Key or Music visualizer mode
        if self.is_custom_mode or self.is_music_mode:
            kid = key_info.get("id")
            if kid in self.key_colors:
                return self.key_colors[kid]
            return QColor(30, 32, 38)

        # Off mode
        if self.active_mode == 0:
            return QColor(35, 35, 40)

        if self.is_rainbow:
            # Traveling rainbow wave across X coordinate
            hue = int((px / self.ORIGINAL_W * 360 + self.animation_phase * 60) % 360)
            return QColor.fromHsv(hue, 220, 255)
        else:
            # Monochrome / palette effect
            if self.active_mode == 18 or self.active_mode == 2:  # Breathing
                factor = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(self.animation_phase * 2))
                return QColor(
                    int(self.active_palette_color.red() * factor),
                    int(self.active_palette_color.green() * factor),
                    int(self.active_palette_color.blue() * factor),
                )
            return self.active_palette_color

    def mousePressEvent(self, event):
        scale_x = self.width() / self.ORIGINAL_W
        scale_y = self.height() / self.ORIGINAL_H
        scale = min(scale_x, scale_y)

        draw_w = self.ORIGINAL_W * scale
        draw_h = self.ORIGINAL_H * scale
        offset_x = (self.width() - draw_w) / 2
        offset_y = (self.height() - draw_h) / 2

        pos = event.position()
        mx = (pos.x() - offset_x) / scale
        my = (pos.y() - offset_y) / scale

        for k in self.keys:
            r = k["rect"]
            if r[0] <= mx <= r[2] and r[1] <= my <= r[3]:
                kid = k["id"]
                if self.selection_enabled:
                    if kid in self.selected_keys:
                        self.selected_keys.remove(kid)
                    else:
                        self.selected_keys.add(kid)
                    self.update()
                self.key_clicked.emit(kid)
                break
        super().mousePressEvent(event)
