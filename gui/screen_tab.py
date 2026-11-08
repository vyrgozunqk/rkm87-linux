"""TFT Screen & GIF animation manager tab."""

import os
from typing import List, Optional
from PIL import Image, ImageSequence

from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
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

    def __init__(self, dev: RKDevice, file_path: str):
        super().__init__()
        self.dev = dev
        self.file_path = file_path
        self._is_cancelled = False
        self.uploader = ScreenUploader(self.dev)

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            ok = self.uploader.upload_gif(
                self.file_path,
                progress_callback=lambda cur, tot, txt: self.progress.emit(cur, tot, txt),
                cancel_check=lambda: self._is_cancelled
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
        box_layout = QVBoxLayout(preview_box)
        box_layout.setAlignment(Qt.AlignCenter)

        # LCD Preview screen
        self.lbl_screen = QLabel()
        self.lbl_screen.setFixedSize(240 * 1.5, 135 * 1.5)  # 360x202 preview
        self.lbl_screen.setStyleSheet("background-color: #000000; border: 3px solid #27272a; border-radius: 8px; color: #71717a; font-size: 13px;")
        self.lbl_screen.setAlignment(Qt.AlignCenter)
        self.lbl_screen.setText("No Image or GIF Selected\nClick 'Choose File' below")
        box_layout.addWidget(self.lbl_screen)

        self.lbl_info = QLabel("Resolution: 240×135 | Frames: 0")
        self.lbl_info.setStyleSheet("color: #a1a1aa; font-size: 12px; margin-top: 6px;")
        self.lbl_info.setAlignment(Qt.AlignCenter)
        box_layout.addWidget(self.lbl_info)

        # Controls
        ctrl_layout = QHBoxLayout()
        self.btn_browse = QPushButton("Choose Image / GIF...")
        self.btn_browse.setStyleSheet("QPushButton { background-color: #3b82f6; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px; } QPushButton:hover { background-color: #2563eb; }")
        self.btn_browse.clicked.connect(self._on_browse)

        self.btn_upload = QPushButton("Upload to Screen")
        self.btn_upload.setEnabled(False)
        self.btn_upload.setStyleSheet("QPushButton { background-color: #10b981; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px; } QPushButton:hover { background-color: #059669; } QPushButton:disabled { background-color: #27272a; color: #71717a; }")
        self.btn_upload.clicked.connect(self._on_upload)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setVisible(False)
        self.btn_cancel.setStyleSheet("QPushButton { background-color: #ef4444; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px; } QPushButton:hover { background-color: #dc2626; }")
        self.btn_cancel.clicked.connect(self._on_cancel)

        ctrl_layout.addWidget(self.btn_browse)
        ctrl_layout.addWidget(self.btn_upload)
        ctrl_layout.addWidget(self.btn_cancel)
        box_layout.addLayout(ctrl_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { background: #27272a; border-radius: 4px; height: 12px; text-align: center; color: white; font-size: 11px; } QProgressBar::chunk { background: #10b981; border-radius: 4px; }")
        box_layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color: #e4e4e7; font-size: 12px;")
        box_layout.addWidget(self.lbl_status)

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
        self.anim_timer.stop()
        self.preview_frames.clear()

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

                # Fit and center on 240x135 black canvas
                w, h = f.size
                scale = min(240 / w, 135 / h)
                nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
                f_resized = f.resize((nw, nh), Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", (240, 135), (0, 0, 0))
                left = (240 - nw) // 2
                top = (135 - nh) // 2
                canvas.paste(f_resized, (left, top))

                # Convert PIL to QPixmap
                data = canvas.tobytes("raw", "RGB")
                qimg = QImage(data, 240, 135, 240 * 3, QImage.Format_RGB888)
                self.preview_frames.append(QPixmap.fromImage(qimg).scaled(360, 202, Qt.KeepAspectRatio, Qt.SmoothTransformation))

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

        self.btn_browse.setEnabled(False)
        self.btn_upload.setVisible(False)
        self.btn_cancel.setVisible(True)
        self.btn_cancel.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setText("Preparing upload...")

        self.upload_started.emit()

        self.worker = UploadWorker(self.dev, self.current_file)
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
        self.btn_cancel.setVisible(False)
        self.btn_upload.setVisible(True)
        if not self.dev.is_dongle:
            self.btn_upload.setEnabled(True)
        self.lbl_status.setText(f"✓ {message}" if success else f"⚠️ {message}")
        self.upload_finished.emit(success, message)
