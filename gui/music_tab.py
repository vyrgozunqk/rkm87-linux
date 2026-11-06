"""Music Reactive Audio Spectrum Tab ("Winamp" Equalizer Visualizer)."""

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from rkm87.audio import MUSIC_STYLES, MusicVisualizerController
from .canvas import KeyboardCanvas


class EqualizerPreviewWidget(QWidget):
    """Real-time 11-column mini equalizer widget drawn with QPainter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(140)
        self.bands = [0.0] * 11
        self.setStyleSheet("background-color: #18181b; border: 1px solid #3f3f46; border-radius: 6px;")

    def update_bands(self, bands: List[float]):
        self.bands = bands[:11]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        painter.fillRect(0, 0, w, h, QColor("#18181b"))

        num_cols = 11
        col_w = (w - (num_cols + 1) * 8) / num_cols
        max_h = h - 20

        colors = [
            QColor("#22c55e"),  # Green (low)
            QColor("#eab308"),  # Yellow (mid)
            QColor("#ef4444"),  # Red (peak)
        ]

        for i, val in enumerate(self.bands):
            cx = 8 + i * (col_w + 8)
            bar_h = max(4, int(val * max_h))
            cy = h - 10 - bar_h

            # Segmented Winamp bar effect
            num_segments = max(1, int(bar_h / 6))
            for seg in range(num_segments):
                seg_y = h - 10 - (seg + 1) * 6
                ratio = seg / max(1, int(max_h / 6))
                if ratio < 0.6:
                    col = colors[0]
                elif ratio < 0.85:
                    col = colors[1]
                else:
                    col = colors[2]

                painter.fillRect(int(cx), int(seg_y), int(col_w), 4, col)


class MusicTab(QWidget):
    visualizer_toggled = Signal(bool)
    frame_received = Signal(dict, list)

    def __init__(self, dev, canvas: KeyboardCanvas, parent=None):
        super().__init__(parent)
        self.dev = dev
        self.canvas = canvas
        self.controller = MusicVisualizerController(self.dev, gui_callback=self._on_gui_frame)
        self.is_active = False
        self.frame_received.connect(self._handle_frame_gui)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        grid = QGridLayout(content)
        grid.setContentsMargins(15, 12, 15, 12)
        grid.setHorizontalSpacing(15)
        grid.setVerticalSpacing(12)

        box_style = (
            "QGroupBox { font-weight: bold; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 8px; margin-top: 10px; padding: 14px; background-color: #18181b; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #38bdf8; }"
        )

        # 1. Left Column: Master Toggle & Style Box
        ctrl_box = QGroupBox("🎛️ Real-Time Music Colors Control")
        ctrl_box.setStyleSheet(box_style)
        ctrl_layout = QVBoxLayout(ctrl_box)
        ctrl_layout.setSpacing(10)

        # Toggle Button
        self.btn_toggle = QPushButton("▶️  Start Music Light Show")
        self.btn_toggle.setCheckable(True)
        self.btn_toggle.setStyleSheet("""
            QPushButton {
                background: #27272a;
                color: #10b981;
                font-weight: bold;
                font-size: 14px;
                border: 2px solid #10b981;
                border-radius: 6px;
                padding: 10px 20px;
                min-height: 26px;
            }
            QPushButton:hover {
                background: #10b981;
                color: #ffffff;
            }
            QPushButton:checked {
                background: #ef4444;
                color: #ffffff;
                border-color: #ef4444;
            }
            QPushButton:disabled {
                background: #18181b;
                color: #71717a;
                border-color: #3f3f46;
            }
        """)
        self.btn_toggle.clicked.connect(self._toggle_visualizer)
        ctrl_layout.addWidget(self.btn_toggle)

        # Style Dropdown Row
        style_row = QHBoxLayout()
        style_label = QLabel("Light Show Effect:")
        style_label.setStyleSheet("color: #a1a1aa; font-size: 13px; font-weight: bold; min-height: 24px;")
        style_label.setFixedWidth(130)
        self.combo_style = QComboBox()
        self.combo_style.setStyleSheet("QComboBox { background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; padding: 6px 12px; font-size: 13px; min-height: 26px; }")
        for sid, sdata in MUSIC_STYLES.items():
            self.combo_style.addItem(f"[{sid:2d}] {sdata['name']}", sid)
        self.combo_style.currentIndexChanged.connect(self._on_style_changed)
        style_row.addWidget(style_label)
        style_row.addWidget(self.combo_style, stretch=1)
        ctrl_layout.addLayout(style_row)

        # Style Description
        self.lbl_desc = QLabel(MUSIC_STYLES[1]["desc"])
        self.lbl_desc.setStyleSheet("color: #38bdf8; font-style: italic; font-size: 12px; margin-left: 2px;")
        self.lbl_desc.setWordWrap(True)
        ctrl_layout.addWidget(self.lbl_desc)

        # Sensitivity / Gain Slider Row
        gain_row = QHBoxLayout()
        gain_label = QLabel("Sound / Mic Gain:")
        gain_label.setStyleSheet("color: #a1a1aa; font-size: 13px; font-weight: bold; min-height: 24px;")
        gain_label.setFixedWidth(130)
        self.slider_gain = QSlider(Qt.Horizontal)
        self.slider_gain.setRange(2, 30)  # 0.2x to 3.0x
        self.slider_gain.setValue(12)     # 1.2x
        self.slider_gain.setStyleSheet("QSlider::groove:horizontal { height: 6px; background: #27272a; border-radius: 3px; } QSlider::sub-page:horizontal { background: #38bdf8; border-radius: 3px; } QSlider::handle:horizontal { background: #f4f4f5; width: 14px; margin-top: -4px; margin-bottom: -4px; border-radius: 7px; }")
        self.val_gain = QLabel("1.2x")
        self.val_gain.setStyleSheet("color: #38bdf8; font-weight: bold; min-width: 45px;")
        self.slider_gain.valueChanged.connect(self._on_gain_changed)
        gain_row.addWidget(gain_label)
        gain_row.addWidget(self.slider_gain, stretch=1)
        gain_row.addWidget(self.val_gain)
        ctrl_layout.addLayout(gain_row)

        # Audio Input Source Selection Checkbox
        self.chk_mic = QCheckBox("🎤 Use Microphone (default is Desktop Audio / What You Hear)")
        self.chk_mic.setStyleSheet("QCheckBox { color: #f4f4f5; font-size: 13px; spacing: 8px; min-height: 24px; } QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #3f3f46; border-radius: 4px; background: #27272a; } QCheckBox::indicator:checked { background: #38bdf8; border-color: #38bdf8; }")
        self.chk_mic.setChecked(False)
        self.chk_mic.toggled.connect(self._on_mic_toggled)
        ctrl_layout.addWidget(self.chk_mic)

        # Notice Banner inside left column
        self.lbl_notice = QLabel("💡 Note: Real-time keyboard LED audio visualization requires the USB Cable connection.")
        self.lbl_notice.setStyleSheet("color: #eab308; background: #27272a; padding: 10px; border-radius: 6px; font-size: 12px;")
        self.lbl_notice.setWordWrap(True)
        ctrl_layout.addWidget(self.lbl_notice)
        ctrl_layout.addStretch(1)

        grid.addWidget(ctrl_box, 0, 0)

        # 2. Right Column: Live Audio Spectrum Bars Widget
        self.preview_box = QGroupBox("📊 Desktop Audio FFT Monitor (11 Bands)")
        self.preview_box.setStyleSheet(box_style)
        prev_layout = QVBoxLayout(self.preview_box)
        prev_layout.setSpacing(10)

        prev_desc = QLabel("Real-time frequency spectrum analysis computed via PipeWire / PulseAudio FFT.")
        prev_desc.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        prev_desc.setWordWrap(True)
        prev_layout.addWidget(prev_desc)

        self.eq_widget = EqualizerPreviewWidget()
        self.eq_widget.setMinimumHeight(140)
        prev_layout.addWidget(self.eq_widget, stretch=1)

        grid.addWidget(self.preview_box, 0, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        # Initialize connection mode status
        if self.dev:
            self.update_connection_mode(self.dev.is_dongle)

    def update_connection_mode(self, is_dongle: bool):
        """Update UI based on whether keyboard is wired or wireless."""
        if is_dongle:
            self.lbl_notice.setText("⚠️ Currently in 2.4GHz Dongle mode: Real-time keyboard LED audio visualizer is disabled (firmware limitation). Connect the USB cable to enable physical keyboard LED visualization.")
            self.lbl_notice.setStyleSheet("color: #f87171; background: #27272a; padding: 10px; border-radius: 6px; font-size: 12px;")
            if self.is_active:
                self.btn_toggle.setChecked(False)
                self._toggle_visualizer(False)
            self.btn_toggle.setEnabled(False)
        else:
            self.lbl_notice.setText("✓ USB Cable Connected: Real-time keyboard LED audio visualization is available.")
            self.lbl_notice.setStyleSheet("color: #34d399; background: #27272a; padding: 10px; border-radius: 6px; font-size: 12px;")
            self.btn_toggle.setEnabled(True)

    def _on_mic_toggled(self, use_mic: bool):
        title = "📊 Microphone FFT Monitor (11 Bands)" if use_mic else "📊 Desktop Audio FFT Monitor (11 Bands)"
        self.preview_box.setTitle(title)
        self.controller.set_audio_source(use_mic)

    def _toggle_visualizer(self, checked: bool):
        if checked and self.dev and self.dev.is_dongle:
            self.btn_toggle.setChecked(False)
            return

        self.is_active = checked
        if checked:
            self.btn_toggle.setText("⏹️  Stop Music Light Show")
            style_id = self.combo_style.currentData() or 1
            gain = self.slider_gain.value() / 10.0
            use_mic = self.chk_mic.isChecked()
            self.canvas.set_music_mode(True)
            self.controller.start(style_id=style_id, gain=gain, use_mic=use_mic)
        else:
            self.btn_toggle.setText("▶️  Start Music Light Show")
            self.controller.stop()
            self.canvas.set_music_mode(False)
            self.eq_widget.update_bands([0.0] * 11)
        self.visualizer_toggled.emit(checked)

    def _on_style_changed(self, idx):
        style_id = self.combo_style.currentData() or 1
        if style_id in MUSIC_STYLES:
            self.lbl_desc.setText(MUSIC_STYLES[style_id]["desc"])
        self.controller.style_id = style_id

    def _on_gain_changed(self, val):
        gain = val / 10.0
        self.val_gain.setText(f"{gain:.1f}x")
        if self.controller.streamer:
            self.controller.streamer.gain = gain

    def _on_gui_frame(self, key_colors: Dict[str, tuple]):
        """Runs on streamer background thread; dispatches safely via Qt Signal."""
        if self.is_active:
            levels = list(self.controller.streamer.smooth_levels) if (self.controller and self.controller.streamer) else []
            self.frame_received.emit(key_colors, levels)

    def _handle_frame_gui(self, key_colors: Dict[str, tuple], levels: list):
        """Runs safely on the Qt Main Event Loop."""
        if self.is_active:
            self.canvas.set_custom_colors(key_colors)
            if levels:
                self.eq_widget.update_bands(levels)

    def closeEvent(self, event):
        self.controller.stop()
        super().closeEvent(event)
