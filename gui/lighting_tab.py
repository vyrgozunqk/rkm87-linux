"""RGB Lighting configuration tab."""

from typing import Optional, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from rkm87.lighting import LightingConfig, LightingManager


class LightingTab(QWidget):
    lighting_changed = Signal(object, object)  # emits (LightingConfig, Optional[Tuple[int, int, int]])

    def __init__(self, lighting_mgr: LightingManager, parent=None):
        super().__init__(parent)
        self.mgr = lighting_mgr
        self._block_signals = False
        self.custom_rgb: Optional[Tuple[int, int, int]] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Mode Selection
        mode_box = QGroupBox("Lighting Mode Preset")
        mode_box.setStyleSheet("QGroupBox { font-weight: bold; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 6px; margin-top: 10px; padding: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        mode_layout = QHBoxLayout(mode_box)

        mode_label = QLabel("Active Mode:")
        mode_label.setStyleSheet("color: #a1a1aa; font-size: 13px;")
        self.combo_mode = QComboBox()
        self.combo_mode.setStyleSheet("QComboBox { background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; padding: 6px 12px; font-size: 13px; } QComboBox::drop-down { border: none; }")
        for m in self.mgr.modes:
            self.combo_mode.addItem(f"[{m['id']:2d}] {m['name']}", m["id"])

        self.combo_mode.currentIndexChanged.connect(self._on_mode_change)
        mode_layout.addWidget(mode_label)
        mode_layout.addWidget(self.combo_mode, stretch=1)
        layout.addWidget(mode_box)

        # Brightness & Speed Sliders
        sliders_box = QGroupBox("Adjustments")
        sliders_box.setStyleSheet("QGroupBox { font-weight: bold; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 6px; margin-top: 10px; padding: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        sliders_layout = QGridLayout(sliders_box)
        sliders_layout.setVerticalSpacing(12)

        # Brightness
        b_label = QLabel("Brightness:")
        b_label.setStyleSheet("color: #a1a1aa; font-size: 13px;")
        self.slider_bright = QSlider(Qt.Horizontal)
        self.slider_bright.setRange(0, 5)  # 0, 4, 8, 12, 16, 20
        self.slider_bright.setValue(5)
        self.slider_bright.setStyleSheet("QSlider::groove:horizontal { height: 6px; background: #27272a; border-radius: 3px; } QSlider::sub-page:horizontal { background: #10b981; border-radius: 3px; } QSlider::handle:horizontal { background: #f4f4f5; width: 14px; margin-top: -4px; margin-bottom: -4px; border-radius: 7px; }")
        self.val_bright = QLabel("20 / 20")
        self.val_bright.setStyleSheet("color: #10b981; font-weight: bold; min-width: 50px;")
        self.slider_bright.valueChanged.connect(self._on_brightness_change)

        sliders_layout.addWidget(b_label, 0, 0)
        sliders_layout.addWidget(self.slider_bright, 0, 1)
        sliders_layout.addWidget(self.val_bright, 0, 2)

        # Speed
        s_label = QLabel("Speed:")
        s_label.setStyleSheet("color: #a1a1aa; font-size: 13px;")
        self.slider_speed = QSlider(Qt.Horizontal)
        self.slider_speed.setRange(0, 4)
        self.slider_speed.setValue(2)
        self.slider_speed.setStyleSheet("QSlider::groove:horizontal { height: 6px; background: #27272a; border-radius: 3px; } QSlider::sub-page:horizontal { background: #38bdf8; border-radius: 3px; } QSlider::handle:horizontal { background: #f4f4f5; width: 14px; margin-top: -4px; margin-bottom: -4px; border-radius: 7px; }")
        self.val_speed = QLabel("2 / 4")
        self.val_speed.setStyleSheet("color: #38bdf8; font-weight: bold; min-width: 50px;")
        self.slider_speed.valueChanged.connect(self._on_speed_change)

        sliders_layout.addWidget(s_label, 1, 0)
        sliders_layout.addWidget(self.slider_speed, 1, 1)
        sliders_layout.addWidget(self.val_speed, 1, 2)
        layout.addWidget(sliders_box)

        # Color Palette
        color_box = QGroupBox("Color Palette")
        color_box.setStyleSheet("QGroupBox { font-weight: bold; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 6px; margin-top: 10px; padding: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        color_layout = QHBoxLayout(color_box)
        color_layout.setSpacing(10)

        self.color_buttons = []
        self.active_palette_id = 7  # rainbow

        for p in self.mgr.palette:
            btn = QPushButton(p["name"])
            btn.setCheckable(True)
            rgb = p.get("rgb")
            bg_color = f"rgb({rgb[0]},{rgb[1]},{rgb[2]})" if rgb else "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 red, stop:0.3 green, stop:0.7 blue, stop:1 purple)"
            text_color = "#000000" if (rgb and sum(rgb) > 400) else "#ffffff"

            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {bg_color};
                    color: {text_color};
                    font-weight: bold;
                    border: 2px solid #27272a;
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 12px;
                }}
                QPushButton:checked {{
                    border: 2px solid #ffffff;
                }}
            """)
            btn.clicked.connect(lambda checked, pid=p["id"]: self._on_color_click(pid))
            self.color_buttons.append((p["id"], btn))
            color_layout.addWidget(btn)

        # Custom RGB Color Picker Button
        self.btn_custom = QPushButton("🎨 Custom...")
        self.btn_custom.setCheckable(True)
        self.btn_custom.setStyleSheet("""
            QPushButton {
                background: #3f3f46;
                color: #f4f4f5;
                font-weight: bold;
                border: 2px solid #27272a;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }
            QPushButton:checked {
                border: 2px solid #38bdf8;
                color: #38bdf8;
            }
        """)
        self.btn_custom.clicked.connect(self._on_custom_color_click)
        color_layout.addWidget(self.btn_custom)

        self._update_color_button_states()
        layout.addWidget(color_box)
        layout.addStretch(1)

    def _on_brightness_change(self, val):
        steps = [0, 4, 8, 12, 16, 20]
        actual_val = steps[val]
        self.val_bright.setText(f"{actual_val} / 20")
        if actual_val == 0:
            off_idx = self.combo_mode.findData(0)
            if off_idx >= 0 and self.combo_mode.currentIndex() != off_idx:
                self.combo_mode.setCurrentIndex(off_idx)
                return
        self._on_user_change()

    def _on_mode_change(self, index):
        effect = self.combo_mode.currentData()
        if effect == 0:
            self.slider_bright.setValue(0)
            self.slider_bright.setEnabled(False)
        else:
            self.slider_bright.setEnabled(True)
            if self.slider_bright.value() == 0:
                self.slider_bright.setValue(5)
        self._on_user_change()

    def _on_speed_change(self, val):
        self.val_speed.setText(f"{val} / 4")
        self._on_user_change()

    def _on_color_click(self, palette_id: int):
        self.custom_rgb = None
        self.active_palette_id = palette_id
        self._update_color_button_states()
        self._on_user_change()

    def _on_custom_color_click(self):
        initial = QColor(self.custom_rgb[0], self.custom_rgb[1], self.custom_rgb[2]) if self.custom_rgb else QColor(255, 50, 130)
        chosen = QColorDialog.getColor(initial, self, "Pick Custom Keyboard Color")
        if chosen.isValid():
            self.custom_rgb = (chosen.red(), chosen.green(), chosen.blue())
            self.active_palette_id = 0
            hex_str = chosen.name().upper()
            self.btn_custom.setText(f"🎨 {hex_str}")
            self.btn_custom.setStyleSheet(f"""
                QPushButton {{
                    background: {chosen.name()};
                    color: {"#000000" if (chosen.red() + chosen.green() + chosen.blue() > 400) else "#ffffff"};
                    font-weight: bold;
                    border: 2px solid #ffffff;
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 12px;
                }}
            """)
            self._update_color_button_states()
            self._on_user_change()
        else:
            self._update_color_button_states()

    def _update_color_button_states(self):
        is_custom = self.custom_rgb is not None
        self.btn_custom.setChecked(is_custom)
        if not is_custom:
            self.btn_custom.setText("🎨 Custom...")
            self.btn_custom.setStyleSheet("""
                QPushButton {
                    background: #3f3f46;
                    color: #f4f4f5;
                    font-weight: bold;
                    border: 2px solid #27272a;
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 12px;
                }
            """)
        for pid, btn in self.color_buttons:
            btn.setChecked(not is_custom and pid == self.active_palette_id)

    def _on_user_change(self):
        if self._block_signals:
            return
        cfg = self.get_config()
        self.lighting_changed.emit(cfg, self.custom_rgb)

    def get_config(self) -> LightingConfig:
        steps = [0, 4, 8, 12, 16, 20]
        effect = self.combo_mode.currentData()
        if effect is None:
            effect = 1
        bright = 0 if effect == 0 else steps[self.slider_bright.value()]
        speed = self.slider_speed.value()
        return LightingConfig(
            effect=effect,
            brightness=bright,
            speed=speed,
            palette_index=self.active_palette_id
        )

    def update_from_hardware(self, cfg: LightingConfig):
        """Silently update UI controls when hardware state changes."""
        self._block_signals = True
        try:
            # Mode
            idx = self.combo_mode.findData(cfg.effect)
            if idx >= 0:
                self.combo_mode.setCurrentIndex(idx)
            self.slider_bright.setEnabled(cfg.effect != 0)

            # Brightness
            steps = [0, 4, 8, 12, 16, 20]
            slider_idx = 0 if cfg.effect == 0 else 5
            for i, s in enumerate(steps):
                if s == cfg.brightness:
                    slider_idx = i
                    break
            self.slider_bright.setValue(slider_idx)
            self.val_bright.setText(f"{cfg.brightness} / 20")

            # Speed
            self.slider_speed.setValue(max(0, min(4, cfg.speed)))
            self.val_speed.setText(f"{cfg.speed} / 4")

            # Color
            self.active_palette_id = cfg.palette_index
            self._update_color_button_states()
        finally:
            self._block_signals = False
