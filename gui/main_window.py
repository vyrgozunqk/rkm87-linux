"""Main Application Window for Royal Kludge M87."""

from typing import Optional
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from rkm87.audio import get_current_volume
from rkm87.device import RKDevice
from rkm87.keymap import KeyMappingManager
from rkm87.lighting import LightingConfig, LightingManager
from .canvas import KeyboardCanvas
from .custom_tab import CustomLightingTab
from .keymap_tab import KeymapTab
from .lighting_tab import LightingTab
from .music_tab import MusicTab
from .options_tab import KeyboardOptionsTab
from .screen_tab import ScreenTab
from .tray import RKM87TrayIcon


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Royal Kludge M87 Studio")
        self.resize(1040, 830)
        self.setMinimumSize(960, 720)

        # Apply dark theme styling
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121214;
            }
            QTabWidget::pane {
                border: 1px solid #27272a;
                background-color: #18181b;
                border-radius: 8px;
            }
            QTabBar::tab {
                background: #18181b;
                color: #a1a1aa;
                padding: 10px 20px;
                font-weight: bold;
                font-size: 13px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #27272a;
                color: #00ff88;
                border-bottom: 2px solid #00ff88;
            }
        """)

        # Hardware connection
        self.dev = RKDevice()
        self.dev.open()
        self.lighting_mgr = LightingManager(self.dev)
        self.keymap_mgr = KeyMappingManager(self.dev)

        self.last_hardware_config: Optional[LightingConfig] = None

        self._init_ui()

        # Hardware Polling Timer (1.5 seconds)
        # Keeps app in sync even if user changes RGB mode physically on keyboard
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_hardware_state)
        self.poll_timer.start(1500)

        # Initial probe and automatic clock & volume synchronization
        self._poll_hardware_state()
        self._on_quick_sync()

    def _init_ui(self):
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 15, 20, 15)
        main_layout.setSpacing(12)

        # Header bar
        header_layout = QHBoxLayout()
        title = QLabel("ROYAL KLUDGE M87 STUDIO")
        title.setFont(QFont("Sans-serif", 16, QFont.Bold))
        title.setStyleSheet("color: #ffffff; letter-spacing: 1px;")
        header_layout.addWidget(title)

        header_layout.addStretch(1)

        # Quick Sync Time & Volume Button
        self.btn_quick_sync = QPushButton("⚡ Sync Time && Volume")
        self.btn_quick_sync.setStyleSheet("QPushButton { background-color: #27272a; color: #38bdf8; border: 1px solid #38bdf8; font-weight: bold; padding: 6px 14px; border-radius: 6px; } QPushButton:hover { background-color: #38bdf8; color: #121214; }")
        self.btn_quick_sync.clicked.connect(self._on_quick_sync)
        header_layout.addWidget(self.btn_quick_sync)

        main_layout.addLayout(header_layout)

        # 2D Keyboard Visualizer Canvas
        self.canvas = KeyboardCanvas()
        self.canvas.key_clicked.connect(self._on_canvas_key_clicked)
        main_layout.addWidget(self.canvas)

        # Tabs
        self.tabs = QTabWidget()
        self.lighting_tab = LightingTab(self.lighting_mgr)
        self.lighting_tab.lighting_changed.connect(self._on_user_lighting_change)

        self.custom_tab = CustomLightingTab(self.lighting_mgr, self.canvas)
        self.custom_tab.custom_applied.connect(self._on_custom_lighting_applied)

        self.music_tab = MusicTab(self.dev, self.canvas)
        self.keymap_tab = KeymapTab(self.keymap_mgr)
        self.screen_tab = ScreenTab(self.dev)
        self.screen_tab.upload_started.connect(self._on_screen_upload_started)
        self.screen_tab.upload_finished.connect(self._on_screen_upload_finished)
        self.options_tab = KeyboardOptionsTab(self.dev, self.lighting_mgr, self.keymap_mgr)
        self.options_tab.options_changed.connect(self._on_options_changed)
        self.options_tab.data_reset.connect(self._on_keyboard_data_reset)

        self.tabs.addTab(self.lighting_tab, "🎨 RGB Lighting Studio")
        self.tabs.addTab(self.custom_tab, "💡 Per-Key Custom RGB")
        self.tabs.addTab(self.music_tab, "🎵 Real-Time Music Colors")
        self.tabs.addTab(self.keymap_tab, "⌨️ Key Remap && Macros")
        self.tabs.addTab(self.screen_tab, "🖥️ TFT Screen && Animations")
        self.tabs.addTab(self.options_tab, "⚙️ Keyboard Options")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tabs, stretch=1)

        # Bottom Status Bar
        status_bar = QHBoxLayout()
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet("color: #71717a; font-size: 16px;")
        self.status_text = QLabel("Checking connection...")
        self.status_text.setStyleSheet("color: #a1a1aa; font-size: 12px;")

        status_bar.addWidget(self.status_dot)
        status_bar.addWidget(self.status_text)
        status_bar.addStretch(1)

        main_layout.addLayout(status_bar)
        self.setCentralWidget(central)

        # Initialize System Tray Icon
        self.tray = RKM87TrayIcon(self.lighting_mgr, self)
        self.tray.profile_selected.connect(self._on_tray_profile_selected)
        self.tray.preset_selected.connect(self._on_tray_preset_selected)
        self.tray.music_toggled.connect(self._on_tray_music_toggled)
        self.tray.sync_requested.connect(self._on_quick_sync)
        self.tray.exit_requested.connect(self._on_tray_exit)
        self.tray.show()

    def _on_tab_changed(self, index: int):
        current_widget = self.tabs.currentWidget()
        if current_widget == self.custom_tab:
            self.canvas.selection_enabled = True
            self.canvas.set_custom_mode(True)
            self.canvas.set_music_mode(False)
            self.canvas.set_custom_colors(self.custom_tab.key_colors)
        elif current_widget == self.music_tab:
            self.canvas.selection_enabled = False
            self.canvas.set_music_mode(self.music_tab.is_active)
        else:
            self.canvas.selection_enabled = False
            self.canvas.set_custom_mode(False)
            self.canvas.set_music_mode(False)
            if self.last_hardware_config and 1 <= self.last_hardware_config.effect <= 17:
                self._update_canvas_from_config(self.last_hardware_config)
            else:
                default_cfg = LightingConfig(effect=1, brightness=20, speed=2, palette_index=7)
                self.last_hardware_config = default_cfg
                self._update_canvas_from_config(default_cfg)
        self.canvas.update()

    def _poll_hardware_state(self):
        """Poll keyboard hardware to reflect manual on-device RGB changes in the UI."""
        if hasattr(self, "music_tab") and self.music_tab.is_active:
            return
        # Don't touch the device while a GIF upload is streaming from the worker thread
        if hasattr(self, "screen_tab") and self.screen_tab.is_uploading():
            return

        # Check for hotplug changes (switching between USB cable and 2.4GHz dongle)
        old_dongle = self.dev.is_dongle
        old_fd = self.dev.fd
        has_device = self.dev.poll_hotplug()

        if not has_device or not self.dev.fd:
            self.status_dot.setStyleSheet("color: #ef4444; font-size: 16px;")
            self.status_text.setText("Keyboard Disconnected")
            return

        if old_dongle != self.dev.is_dongle or old_fd != self.dev.fd:
            self._update_status_indicator()
            self.tray.refresh_menu()

        # Check sleep state
        is_awake = self.dev.is_awake()
        self._update_status_indicator(is_awake)

        if not is_awake:
            return

        # Don't overwrite canvas if user is editing custom lighting or in music mode
        current_widget = self.tabs.currentWidget()
        if current_widget in (self.custom_tab, self.music_tab):
            return

        # Read actual lighting profile from keyboard
        cfg = self.lighting_mgr.get_current_lighting()
        if cfg and cfg != self.last_hardware_config:
            # Mode 18/19 is Gaoshou custom lighting, not a standard studio effect
            if cfg.effect in (18, 19):
                return
            self.last_hardware_config = cfg
            self.lighting_tab.update_from_hardware(cfg)
            if hasattr(self, "options_tab"):
                self.options_tab.update_from_hardware(cfg)
            self._update_canvas_from_config(cfg)

    def _update_canvas_from_config(self, cfg: LightingConfig):
        palette_color = None
        is_rainbow = (cfg.palette_index == 7)
        for p in self.lighting_mgr.palette:
            if p["id"] == cfg.palette_index:
                palette_color = p.get("rgb")
                break
        self.canvas.set_lighting_state(cfg.effect, palette_color, is_rainbow)

    def _update_status_indicator(self, is_awake: bool = True):
        mode_str = "2.4GHz Wireless Dongle" if self.dev.is_dongle else "USB Cable"
        self.screen_tab.update_connection_mode(self.dev.is_dongle)
        if hasattr(self, "music_tab"):
            self.music_tab.update_connection_mode(self.dev.is_dongle)

        if not is_awake:
            self.status_dot.setStyleSheet("color: #eab308; font-size: 16px;")
            self.status_text.setText(f"Connected: {mode_str} (Keyboard is in Wireless Sleep Mode - press any key to wake)")
        else:
            self.status_dot.setStyleSheet("color: #10b981; font-size: 16px;")
            self.status_text.setText(f"Connected: {mode_str} (Active)")

    def _on_options_changed(self, debounce: int, sleep_minutes: int):
        if self.last_hardware_config:
            self.last_hardware_config.debounce = debounce
            self.last_hardware_config.sleep_minutes = sleep_minutes

    def _on_user_lighting_change(self, cfg: LightingConfig, custom_rgb: Optional[tuple] = None):
        """Called when user changes lighting controls in GUI."""
        self.last_hardware_config = cfg
        self.lighting_mgr.set_lighting(cfg, custom_rgb=custom_rgb)
        if custom_rgb:
            palette_color = list(custom_rgb)
            is_rainbow = False
        else:
            palette_color = None
            is_rainbow = (cfg.palette_index == 7)
            for p in self.lighting_mgr.palette:
                if p["id"] == cfg.palette_index:
                    palette_color = p.get("rgb")
                    break
        self.canvas.set_lighting_state(cfg.effect, palette_color, is_rainbow)

    def _on_custom_lighting_applied(self, key_colors: dict, brightness: int):
        self.status_text.setText(f"✓ Custom per-key lighting applied ({len(key_colors)} keys configured)")
        self.tray.refresh_menu()

    def _on_canvas_key_clicked(self, key_id: str):
        """When a key is clicked on the visual 2D canvas, select it in the active editing tab."""
        if self.tabs.currentWidget() == self.keymap_tab:
            self.keymap_tab.select_key(key_id)

    def _on_screen_upload_started(self):
        """Lock navigation, quick sync, and hardware interactions while screen flash is burning."""
        self.tabs.tabBar().setEnabled(False)
        self.btn_quick_sync.setEnabled(False)
        self.canvas.setEnabled(False)
        self.status_dot.setStyleSheet("color: #38bdf8; font-size: 16px;")
        self.status_text.setText("🔒 Screen upload in progress — settings and tabs are locked to prevent hardware interruption")

    def _on_screen_upload_finished(self, success: bool, message: str):
        """Restore navigation and hardware interactions after screen upload finishes."""
        self.tabs.tabBar().setEnabled(True)
        self.btn_quick_sync.setEnabled(True)
        self.canvas.setEnabled(True)
        self._update_status_indicator()
        if not success:
            self._on_quick_sync()

    def _on_quick_sync(self):
        if hasattr(self, "screen_tab") and self.screen_tab.is_uploading():
            return
        deb = getattr(self.options_tab, "current_debounce", 4)
        sleep_m = getattr(self.options_tab, "current_sleep_minutes", 10)
        vol = get_current_volume()
        if self.dev.sync_time_and_volume(vol):
            if deb == 1:
                import time
                time.sleep(0.04)
                self.lighting_mgr.set_hardware_options(deb, sleep_m)
            self.status_text.setText("✓ Clock and volume successfully synchronized to keyboard screen!")
        else:
            self.status_text.setText("⚠️ Sync failed (keyboard might be asleep).")

    def _on_keyboard_data_reset(self):
        """Called when user executes Reset Keyboard Data in Options Tab."""
        default_cfg = LightingConfig(effect=1, brightness=20, speed=2, palette_index=7, debounce=4, sleep_minutes=10)
        self.last_hardware_config = default_cfg
        self.lighting_tab.update_from_hardware(default_cfg)
        self._update_canvas_from_config(default_cfg)
        self.canvas.set_custom_colors({})
        self.status_text.setText("✓ All keyboard data successfully reset to clean factory defaults!")
        self.tray.refresh_menu()

    def _on_tray_profile_selected(self, profile_name: str):
        if hasattr(self, "screen_tab") and self.screen_tab.is_uploading():
            self.tray.showMessage(
                "Upload in Progress",
                "Screen animation is currently writing to keyboard memory. Please wait for it to complete.",
                QSystemTrayIcon.Warning,
                2500
            )
            return
        prof = self.lighting_mgr.load_custom_profile(profile_name)
        if prof and "keys" in prof:
            keys_map = {k: tuple(v) for k, v in prof["keys"].items()}
            self.lighting_mgr.set_custom_matrix_lighting(keys_map, brightness=20)
            self.canvas.set_custom_colors(keys_map)
            self.canvas.set_custom_mode(True)
            self.status_text.setText(f"✓ Tray: Applied custom profile '{prof.get('name', profile_name)}'")

    def _on_tray_preset_selected(self, effect_id: int, brightness: int, palette_id: int):
        if hasattr(self, "screen_tab") and self.screen_tab.is_uploading():
            self.tray.showMessage(
                "Upload in Progress",
                "Screen animation is currently writing to keyboard memory. Please wait for it to complete.",
                QSystemTrayIcon.Warning,
                2500
            )
            return
        cfg = LightingConfig(effect=effect_id, brightness=brightness, speed=2, palette_index=palette_id)
        self.lighting_mgr.set_lighting(cfg)
        self.lighting_tab.update_from_hardware(cfg)
        self._update_canvas_from_config(cfg)
        name = "Off" if effect_id == 0 else self.lighting_mgr.get_mode_name(effect_id)
        self.status_text.setText(f"✓ Tray: Set lighting to {name}")

    def _on_tray_music_toggled(self, enabled: bool):
        if hasattr(self, "screen_tab") and self.screen_tab.is_uploading():
            self.tray.showMessage(
                "Upload in Progress",
                "Screen animation is currently writing to keyboard memory. Please wait for it to complete.",
                QSystemTrayIcon.Warning,
                2500
            )
            return
        self.tabs.setCurrentWidget(self.music_tab)
        self.music_tab.btn_toggle.setChecked(enabled)
        self.music_tab._toggle_visualizer(enabled)

    def _on_tray_exit(self):
        if hasattr(self, "screen_tab") and self.screen_tab.is_uploading():
            reply = QMessageBox.question(
                self,
                "Cancel Screen Upload?",
                "A screen animation upload is currently writing to keyboard flash memory.\n\n"
                "Exiting now will abort the transfer and reset the display. Do you want to cancel and exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            self.screen_tab._on_cancel()

        self.poll_timer.stop()
        if hasattr(self, "music_tab") and self.music_tab.controller:
            self.music_tab.controller.stop()
        self.dev.close()
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        """Minimize to system tray on window close button click, blocking if upload is active."""
        if hasattr(self, "screen_tab") and self.screen_tab.is_uploading():
            QMessageBox.warning(
                self,
                "Upload in Progress",
                "A screen animation upload is currently writing to keyboard flash memory.\n\n"
                "Please wait for the upload to complete, or click 'Cancel' in the Screen tab before closing."
            )
            event.ignore()
            return

        if self.tray and self.tray.isVisible():
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "RK M87 Studio",
                "Application minimized to system tray. Right-click the icon for quick profiles, presets, and music visualizer.",
                QSystemTrayIcon.Information,
                2000
            )
        else:
            self.poll_timer.stop()
            if hasattr(self, "music_tab") and self.music_tab.controller:
                self.music_tab.controller.stop()
            self.dev.close()
            event.accept()
