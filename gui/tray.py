"""System Tray Icon for RK M87 Studio (Compatible with KDE Plasma, GNOME, Cinnamon, XFCE)."""

import os
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFont, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from rkm87.lighting import LightingConfig, LightingManager


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


class RKM87TrayIcon(QSystemTrayIcon):
    profile_selected = Signal(str)  # emits profile_name
    preset_selected = Signal(int, int, int)  # emits (effect_id, brightness, palette_id)
    music_toggled = Signal(bool)
    sync_requested = Signal()
    exit_requested = Signal()

    def __init__(self, lighting_mgr: LightingManager, parent=None):
        icon_path = os.path.join(DATA_DIR, "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        super().__init__(icon, parent)
        self.mgr = lighting_mgr
        self.parent_window = parent

        self.setToolTip("RK M87 Studio")
        self._init_menu()

        # Connect click actions
        self.activated.connect(self._on_tray_activated)

    def _init_menu(self):
        self.menu = QMenu()
        self.menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e24;
                color: #f4f4f5;
                border: 1px solid #3f3f46;
                border-radius: 6px;
                padding: 6px;
                font-size: 13px;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #38bdf8;
                color: #000000;
                font-weight: bold;
            }
            QMenu::separator {
                height: 1px;
                background: #3f3f46;
                margin: 4px 8px;
            }
        """)

        # Title / Status
        conn_str = "2.4GHz Wireless" if self.mgr.dev.is_dongle else "USB Cable"
        self.act_title = QAction(f"RK M87 ({conn_str})", self.menu)
        self.act_title.setEnabled(False)
        self.menu.addAction(self.act_title)
        self.menu.addSeparator()

        # Quick Profiles Submenu
        self.menu_profiles = self.menu.addMenu("🎨 Quick Profiles")
        self.menu_profiles.setStyleSheet(self.menu.styleSheet())
        self._populate_profiles_menu()

        self.menu.addSeparator()

        # Music Reactive Toggle
        self.act_music = QAction("🎵 Music Visualizer", self.menu)
        self.act_music.setCheckable(True)
        self.act_music.toggled.connect(self.music_toggled.emit)
        self.menu.addAction(self.act_music)

        # Clock & Volume Sync
        self.act_sync = QAction("⏰ Sync Clock && Volume", self.menu)
        self.act_sync.triggered.connect(self.sync_requested.emit)
        self.menu.addAction(self.act_sync)

        self.menu.addSeparator()

        # Open Window Action
        self.act_open = QAction("🖥️ Open RK M87 Studio", self.menu)
        bold_font = QFont()
        bold_font.setBold(True)
        self.act_open.setFont(bold_font)
        self.act_open.triggered.connect(self._toggle_window)
        self.menu.addAction(self.act_open)

        # Exit Action
        self.act_exit = QAction("❌ Exit", self.menu)
        self.act_exit.triggered.connect(self.exit_requested.emit)
        self.menu.addAction(self.act_exit)

        self.setContextMenu(self.menu)

    def _populate_profiles_menu(self):
        self.menu_profiles.clear()

        # 1. Custom JSON Profiles
        profiles = self.mgr.list_custom_profiles()
        if profiles:
            lbl = QAction("--- Custom Profiles ---", self.menu_profiles)
            lbl.setEnabled(False)
            self.menu_profiles.addAction(lbl)
            for p in profiles:
                act = QAction(p.replace("_", " ").title(), self.menu_profiles)
                act.triggered.connect(lambda _, name=p: self.profile_selected.emit(name))
                self.menu_profiles.addAction(act)
            self.menu_profiles.addSeparator()

        # 2. Hardware Presets
        lbl2 = QAction("--- Lighting Presets ---", self.menu_profiles)
        lbl2.setEnabled(False)
        self.menu_profiles.addAction(lbl2)

        presets = [
            ("🌈 Rainbow Wave", 1, 20, 7),
            ("💨 Breathing Blue", 2, 20, 2),
            ("🔴 Static Red", 1, 20, 0),
            ("🔵 Static Blue", 1, 20, 2),
            ("🟢 Static Green", 1, 20, 1),
            ("⚪ Static White", 1, 20, 6),
            ("💡 Turn Off Lights", 0, 0, 7),
        ]
        for title, eff, bright, pal in presets:
            act = QAction(title, self.menu_profiles)
            act.triggered.connect(lambda _, e=eff, b=bright, p=pal: self.preset_selected.emit(e, b, p))
            self.menu_profiles.addAction(act)

    def refresh_menu(self):
        self._populate_profiles_menu()
        conn_str = "2.4GHz Wireless" if self.mgr.dev.is_dongle else "USB Cable"
        self.act_title.setText(f"RK M87 ({conn_str})")

    def _on_tray_activated(self, reason):
        # Handle Single Click (Trigger) or Double Click
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self._toggle_window()

    def _toggle_window(self):
        if not self.parent_window:
            return
        if self.parent_window.isVisible() and not self.parent_window.isMinimized():
            self.parent_window.hide()
        else:
            self.parent_window.showNormal()
            self.parent_window.raise_()
            self.parent_window.activateWindow()
