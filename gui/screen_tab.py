"""TFT Screen & GIF animation manager tab."""

import os
from typing import List, Optional
from PIL import Image, ImageSequence

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from rkm87.device import RKDevice
from rkm87.screen import ScreenUploader


class UploadWorker(QThread):
    progress = Signal(int, int, str)
    finished = Signal(bool, str)

    def __init__(self, dev: RKDevice, file_path: str, scale_mode: str = "fill"):
        super().__init__()
        self.dev = dev
        self.file_path = file_path
        self.scale_mode = scale_mode
        self._is_cancelled = False
        self.uploader = ScreenUploader(self.dev)

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            ok = self.uploader.upload_gif(
                self.file_path,
                progress_callback=lambda cur, tot, txt: self.progress.emit(cur, tot, txt),
                cancel_check=lambda: self._is_cancelled,
                scale_mode=self.scale_mode,
            )
            if self._is_cancelled:
                self.finished.emit(False, "Upload cancelled by user (hardware display state reset).")
            elif ok:
                self.finished.emit(True, "Upload completed successfully!")
            else:
                self.finished.emit(False, "Upload failed.")
        except Exception as e:
            self.finished.emit(False, str(e))


class ScreenTab(QWidget):
    upload_started = Signal()
    upload_finished = Signal(bool, str)

    def __init__(self, dev: RKDevice, parent=None):
        super().__init__(parent)
        self.dev = dev
        self.current_file: Optional[str] = None
        self.preview_frames: List[QPixmap] = []
        self.preview_frame_idx = 0
        self.frame_delay_ms = 100
        self.worker: Optional[UploadWorker] = None

        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._next_preview_frame)

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Upload & Preview Box
        preview_box = QGroupBox("Screen Display (240 × 135 pixels)")
        preview_box.setStyleSheet("QGroupBox { font-weight: bold; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 6px; margin-top: 10px; padding: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")

        # Horizontal side-by-side content: Left = Screen Preview, Right = Controls
        content_layout = QHBoxLayout()
        content_layout.setSpacing(28)
        content_layout.setContentsMargins(10, 10, 10, 10)

        # Left Column: Preview Screen & Info
        left_col = QVBoxLayout()
        left_col.setSpacing(6)
        left_col.setAlignment(Qt.AlignCenter)

        self.lbl_screen = QLabel()
        self.lbl_screen.setFixedSize(320, 180)  # Clean 16:9 preview matching 240x135
        self.lbl_screen.setStyleSheet("background-color: #000000; border: 2px solid #3f3f46; border-radius: 8px; color: #71717a; font-size: 13px;")
        self.lbl_screen.setAlignment(Qt.AlignCenter)
        self.lbl_screen.setText("No Image or GIF Selected\nClick 'Choose Image / GIF' on the right")
        left_col.addWidget(self.lbl_screen)

        self.lbl_info = QLabel("Resolution: 240×135 | Frames: 0")
        self.lbl_info.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        self.lbl_info.setAlignment(Qt.AlignCenter)
        left_col.addWidget(self.lbl_info)
        content_layout.addLayout(left_col)

        # Right Column: Controls, Scale Mode, Upload, Progress & Status
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        right_col.setAlignment(Qt.AlignVCenter)

        # File browse button
        self.btn_browse = QPushButton("📁  Choose Image / Animated GIF...")
        self.btn_browse.setStyleSheet("""
            QPushButton {
                background-color: #2563eb;
                color: #ffffff;
                font-weight: bold;
                padding: 10px 18px;
                border-radius: 6px;
                font-size: 13px;
                border: 1px solid #3b82f6;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
        """)
        self.btn_browse.clicked.connect(self._on_browse)
        right_col.addWidget(self.btn_browse)

        # Scaling Mode row
        scale_box = QVBoxLayout()
        scale_box.setSpacing(4)
        lbl_scale = QLabel("DISPLAY SCALING:")
        lbl_scale.setStyleSheet("color: #a1a1aa; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        self.combo_scale = QComboBox()
        self.combo_scale.addItem("Fill Screen (Crop to Fit — Recommended)", "fill")
        self.combo_scale.addItem("Fit Entire Image (Black letterbox borders)", "fit")
        self.combo_scale.addItem("Stretch to Fill (Distort to 240×135)", "stretch")
        self.combo_scale.setStyleSheet("""
            QComboBox {
                background-color: #27272a;
                color: #ffffff;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }
            QComboBox:hover {
                border-color: #3b82f6;
            }
            QComboBox QAbstractItemView {
                background-color: #18181b;
                color: #ffffff;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
                border: 1px solid #3f3f46;
            }
        """)
        self.combo_scale.currentIndexChanged.connect(self._on_scale_mode_changed)
        scale_box.addWidget(lbl_scale)
        scale_box.addWidget(self.combo_scale)
        right_col.addLayout(scale_box)

        # Action Buttons (Upload / Cancel)
        self.btn_upload = QPushButton("🚀  Upload to Keyboard Screen")
        self.btn_upload.setEnabled(False)
        self.btn_upload.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: #ffffff;
                font-weight: bold;
                padding: 10px 18px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:disabled {
                background-color: #27272a;
                color: #52525b;
                border: 1px solid #3f3f46;
            }
        """)
        self.btn_upload.clicked.connect(self._on_upload)

        self.btn_cancel = QPushButton("⏹️  Cancel Upload")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: #ffffff;
                font-weight: bold;
                padding: 10px 18px;
                border-radius: 6px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #dc2626;
            }
        """)
        self.btn_cancel.clicked.connect(self._on_cancel)

        right_col.addWidget(self.btn_upload)
        right_col.addWidget(self.btn_cancel)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: #27272a;
                border-radius: 4px;
                height: 14px;
                text-align: center;
                color: white;
                font-size: 11px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background: #10b981;
                border-radius: 4px;
            }
        """)
        right_col.addWidget(self.progress_bar)

        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color: #e4e4e7; font-size: 12px;")
        right_col.addWidget(self.lbl_status)

        content_layout.addLayout(right_col, stretch=1)

        preview_box_layout = QVBoxLayout(preview_box)
        preview_box_layout.addLayout(content_layout)

        layout.addWidget(preview_box)

        # Mode Notice
        self.lbl_notice = QLabel("💡 Note: Custom GIF uploads require the USB Cable connection (per keyboard firmware design).")
        self.lbl_notice.setStyleSheet("color: #eab308; background: #27272a; padding: 10px; border-radius: 6px; font-size: 12px;")
        self.lbl_notice.setWordWrap(True)
        layout.addWidget(self.lbl_notice)

        layout.addStretch(1)

    def is_uploading(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def update_connection_mode(self, is_dongle: bool):
        if is_dongle:
            self.lbl_notice.setText("⚠️ Currently in 2.4GHz Dongle mode: GIF uploading is disabled. Please plug in the USB cable to upload GIFs to the screen.")
            self.lbl_notice.setStyleSheet("color: #f87171; background: #27272a; padding: 10px; border-radius: 6px; font-size: 12px;")
            self.btn_upload.setEnabled(False)
        else:
            self.lbl_notice.setText("✓ USB Cable Connected: You can upload custom static images and animated GIFs.")
            self.lbl_notice.setStyleSheet("color: #34d399; background: #27272a; padding: 10px; border-radius: 6px; font-size: 12px;")
            if self.current_file:
                self.btn_upload.setEnabled(True)

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Image or GIF", "", "Images (*.gif *.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        self.current_file = path
        self._load_preview()

    def _on_scale_mode_changed(self):
        if self.current_file:
            self._load_preview()

    def _load_preview(self):
        if not self.current_file:
            return

        path = self.current_file
        self.anim_timer.stop()
        self.preview_frames.clear()
        scale_mode = self.combo_scale.currentData() if hasattr(self, "combo_scale") else "fill"

        try:
            img = Image.open(path)
            delays = []
            for frame in ImageSequence.Iterator(img):
                # Composite transparent pixels over black
                if frame.mode in ("RGBA", "LA") or (frame.mode == "P" and "transparency" in frame.info):
                    rgba = frame.convert("RGBA")
                    bg = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
                    bg.alpha_composite(rgba)
                    f = bg.convert("RGB")
                else:
                    f = frame.convert("RGB")

                w, h = f.size
                if scale_mode == "stretch":
                    final_img = f.resize((240, 135), Image.Resampling.LANCZOS)
                elif scale_mode == "fit":
                    scale = min(240 / w, 135 / h)
                    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
                    f_resized = f.resize((nw, nh), Image.Resampling.LANCZOS)
                    final_img = Image.new("RGB", (240, 135), (0, 0, 0))
                    left = (240 - nw) // 2
                    top = (135 - nh) // 2
                    final_img.paste(f_resized, (left, top))
                else:  # default "fill"
                    scale = max(240 / w, 135 / h)
                    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
                    f_resized = f.resize((nw, nh), Image.Resampling.LANCZOS)
                    left = (nw - 240) // 2
                    top = (nh - 135) // 2
                    final_img = f_resized.crop((left, top, left + 240, top + 135))

                data = final_img.tobytes("raw", "RGB")
                qimg = QImage(data, 240, 135, 240 * 3, QImage.Format_RGB888)
                self.preview_frames.append(QPixmap.fromImage(qimg).scaled(320, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation))

                d = frame.info.get("duration", 100)
                delays.append(d if d > 0 else 100)
                if len(self.preview_frames) >= 100:
                    break

            self.frame_delay_ms = sum(delays) // len(delays) if delays else 100
            self.lbl_info.setText(f"File: {os.path.basename(path)} | Frames: {len(self.preview_frames)} | Delay: {self.frame_delay_ms}ms")
            self.preview_frame_idx = 0
            self.lbl_screen.setPixmap(self.preview_frames[0])

            if len(self.preview_frames) > 1:
                self.anim_timer.start(self.frame_delay_ms)

            if not self.dev.is_dongle:
                self.btn_upload.setEnabled(True)
            self.lbl_status.setText("")

        except Exception as e:
            self.lbl_screen.setText(f"Failed to load image:\n{e}")

    def _next_preview_frame(self):
        if not self.preview_frames:
            return
        self.preview_frame_idx = (self.preview_frame_idx + 1) % len(self.preview_frames)
        self.lbl_screen.setPixmap(self.preview_frames[self.preview_frame_idx])

    def _on_upload(self):
        if not self.current_file or self.dev.is_dongle:
            return

        scale_mode = self.combo_scale.currentData() if hasattr(self, "combo_scale") else "fill"

        self.btn_browse.setEnabled(False)
        self.combo_scale.setEnabled(False)
        self.btn_upload.setVisible(False)
        self.btn_cancel.setVisible(True)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("Preparing upload...")

        self.upload_started.emit()

        self.worker = UploadWorker(self.dev, self.current_file, scale_mode=scale_mode)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_cancel(self):
        if self.worker:
            self.lbl_status.setText("Cancelling and resetting screen display...")
            self.btn_cancel.setEnabled(False)
            self.worker.cancel()

    def _on_progress(self, current, total, text):
        pct = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.lbl_status.setText(f"{text} ({pct}%)")

    def _on_finished(self, success, message):
        self.btn_browse.setEnabled(True)
        self.combo_scale.setEnabled(True)
        self.btn_cancel.setVisible(False)
        self.btn_upload.setVisible(True)
        if not self.dev.is_dongle:
            self.btn_upload.setEnabled(True)
        self.lbl_status.setText(f"✓ {message}" if success else f"⚠️ {message}")
        self.upload_finished.emit(success, message)
