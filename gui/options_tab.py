"""Keyboard Options & Hardware Settings Tab."""

import os
import sys
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from rkm87.lighting import LightingConfig, LightingManager
from rkm87.keymap import KeymapManager


class KeyboardOptionsTab(QWidget):
    """Hardware options tab for Debounce filter, Wireless Sleep Timer, and Reset recovery."""

    options_changed = Signal(int, int)  # (debounce, sleep_minutes)
    data_reset = Signal()

    def __init__(
        self,
        dev,
        lighting_mgr: LightingManager,
        keymap_mgr: KeymapManager,
        parent=None,
    ):
        super().__init__(parent)
        self.dev = dev
        self.lighting_mgr = lighting_mgr
        self.keymap_mgr = keymap_mgr

        self.current_debounce = 4
        self.current_sleep_minutes = 10
        self._previous_sleep_index = 0
        self._block_signals = False

        self._init_ui()
        self._load_hardware_state()
        self._load_autostart_state()

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
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        box_style = (
            "QGroupBox { font-weight: bold; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 8px; margin-top: 10px; padding: 12px 14px; background-color: #18181b; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #38bdf8; }"
        )

        # 1. Hardware Debounce Filter Box
        debounce_box = QGroupBox("⌨️ Hardware Key Debounce Filter (Anti-Chatter && Response Time)")
        debounce_box.setStyleSheet(box_style)
        deb_layout = QVBoxLayout(debounce_box)
        deb_layout.setSpacing(8)

        deb_desc = QLabel(
            "Debounce controls how long the mechanical switch contacts must stabilize before registering a keystroke. "
            "Stored directly in on-device firmware memory."
        )
        deb_desc.setStyleSheet("color: #a1a1aa; font-size: 12px; margin-bottom: 5px;")
        deb_desc.setWordWrap(True)
        deb_layout.addWidget(deb_desc)

        self.btn_group_debounce = QButtonGroup(self)

        radio_style = (
            "QRadioButton { color: #f4f4f5; font-size: 13px; spacing: 8px; min-height: 24px; } "
            "QRadioButton::indicator { width: 18px; height: 18px; border: 1px solid #3f3f46; border-radius: 9px; background: #27272a; } "
            "QRadioButton::indicator:checked { background: #38bdf8; border-color: #38bdf8; }"
        )

        self.radio_gaming = QRadioButton("⚡ Gaming Mode (1ms) — Lowest input latency for competitive gaming")
        self.radio_gaming.setStyleSheet(radio_style)

        self.radio_office = QRadioButton("💼 Office Mode (4ms) — Recommended; eliminates double-presses (key chatter)")
        self.radio_office.setStyleSheet(radio_style)

        self.btn_group_debounce.addButton(self.radio_gaming, 1)
        self.btn_group_debounce.addButton(self.radio_office, 4)
        self.btn_group_debounce.idToggled.connect(self._on_debounce_toggled)

        deb_layout.addWidget(self.radio_gaming)
        deb_layout.addWidget(self.radio_office)
        deb_layout.addStretch(1)
        grid.addWidget(debounce_box, 0, 0)

        # 2. Wireless Sleep Timer Box
        sleep_box = QGroupBox("💤 Wireless Power && Sleep Timer")
        sleep_box.setStyleSheet(box_style)
        sleep_layout = QVBoxLayout(sleep_box)
        sleep_layout.setSpacing(10)

        sleep_desc = QLabel(
            "When running on 2.4GHz wireless or Bluetooth, the keyboard enters low-power sleep mode after inactivity to conserve battery life."
        )
        sleep_desc.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        sleep_desc.setWordWrap(True)
        sleep_layout.addWidget(sleep_desc)

        sleep_ctrl = QHBoxLayout()
        sleep_label = QLabel("Inactive Timeout:")
        sleep_label.setStyleSheet("color: #f4f4f5; font-size: 13px; font-weight: bold; min-height: 24px;")
        sleep_label.setFixedWidth(130)

        self.combo_sleep = QComboBox()
        self.combo_sleep.setStyleSheet(
            "QComboBox { background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; padding: 6px 12px; font-size: 13px; min-height: 28px; } "
            "QComboBox::drop-down { border: none; }"
        )
        self.combo_sleep.addItem("10 minutes (Recommended)", 10)
        self.combo_sleep.addItem("20 minutes", 20)
        self.combo_sleep.addItem("40 minutes", 40)
        self.combo_sleep.addItem("60 minutes", 60)
        self.combo_sleep.addItem("⚠️ Never (Keep awake indefinitely)", 0)
        self.combo_sleep.currentIndexChanged.connect(self._on_sleep_changed)

        sleep_ctrl.addWidget(sleep_label)
        sleep_ctrl.addWidget(self.combo_sleep, stretch=1)
        sleep_layout.addLayout(sleep_ctrl)
        sleep_layout.addStretch(1)
        grid.addWidget(sleep_box, 0, 1)

        # 3. Application Startup & Desktop Integration Box
        startup_box = QGroupBox("🚀 Application Startup && Desktop Integration")
        startup_box.setStyleSheet(box_style)
        startup_layout = QVBoxLayout(startup_box)
        startup_layout.setSpacing(10)

        startup_desc = QLabel(
            "Configure whether Royal Kludge M87 Studio launches automatically when you log into your desktop session."
        )
        startup_desc.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        startup_desc.setWordWrap(True)
        startup_layout.addWidget(startup_desc)

        self.chk_autostart = QCheckBox("🚀  Start Royal Kludge M87 Studio automatically on system login")
        self.chk_autostart.setStyleSheet(
            "QCheckBox { color: #f4f4f5; font-size: 13px; font-weight: bold; spacing: 8px; min-height: 24px; } "
            "QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #3f3f46; border-radius: 4px; background: #27272a; } "
            "QCheckBox::indicator:checked { background: #38bdf8; border-color: #38bdf8; }"
        )
        self.chk_autostart.toggled.connect(self._on_autostart_toggled)
        startup_layout.addWidget(self.chk_autostart)

        self.chk_start_to_tray = QCheckBox("📥  Start minimized to System Tray")
        self.chk_start_to_tray.setStyleSheet(
            "QCheckBox { color: #f4f4f5; font-size: 13px; spacing: 8px; margin-left: 26px; min-height: 24px; } "
            "QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #3f3f46; border-radius: 4px; background: #27272a; } "
            "QCheckBox::indicator:checked { background: #38bdf8; border-color: #38bdf8; } "
            "QCheckBox:disabled { color: #71717a; }"
        )
        self.chk_start_to_tray.setEnabled(False)
        self.chk_start_to_tray.toggled.connect(self._on_start_to_tray_toggled)
        startup_layout.addWidget(self.chk_start_to_tray)

        tray_note = QLabel(
            "⚠️ Note: Leave 'Start minimized to System Tray' unchecked if your desktop environment does not feature a "
            "system tray by default (e.g., standard GNOME without AppIndicator extensions)."
        )
        tray_note.setStyleSheet("color: #a1a1aa; font-size: 11px; margin-left: 26px;")
        tray_note.setWordWrap(True)
        startup_layout.addWidget(tray_note)
        startup_layout.addStretch(1)
        grid.addWidget(startup_box, 1, 0)

        # 4. Keyboard Maintenance & Reset Box
        reset_box = QGroupBox("🔄 Keyboard Maintenance && Recovery")
        reset_box.setStyleSheet(box_style)
        reset_layout = QVBoxLayout(reset_box)
        reset_layout.setSpacing(12)

        reset_desc = QLabel(
            "If key mappings stop responding or lighting state becomes inconsistent, you can safely reset the on-device "
            "key mapping scancodes, lighting profile, and color tables back to clean defaults."
        )
        reset_desc.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        reset_desc.setWordWrap(True)
        reset_layout.addWidget(reset_desc)

        reset_btn_layout = QHBoxLayout()

        self.btn_reset = QPushButton("🔄  Reset Keyboard Data")
        self.btn_reset.setStyleSheet(
            "QPushButton { background-color: #27272a; color: #f59e0b; font-weight: bold; font-size: 13px; border: 1px solid #f59e0b; border-radius: 6px; padding: 8px 18px; min-height: 28px; } "
            "QPushButton:hover { background-color: #f59e0b; color: #18181b; } "
            "QPushButton:pressed { background-color: #d97706; }"
        )
        self.btn_reset.clicked.connect(self._on_reset_clicked)

        self.btn_help = QPushButton("?")
        self.btn_help.setFixedSize(34, 34)
        self.btn_help.setStyleSheet(
            "QPushButton { background-color: #27272a; color: #38bdf8; font-weight: bold; font-size: 16px; border: 1px solid #38bdf8; border-radius: 6px; } "
            "QPushButton:hover { background-color: #38bdf8; color: #18181b; }"
        )
        self.btn_help.setToolTip("Click for details on Reset Keyboard Data vs Factory Restore")
        self.btn_help.clicked.connect(self._on_help_clicked)

        self.lbl_feedback = QLabel("")
        self.lbl_feedback.setStyleSheet("color: #34d399; font-size: 12px; font-weight: bold;")

        reset_btn_layout.addWidget(self.btn_reset)
        reset_btn_layout.addWidget(self.btn_help)
        reset_btn_layout.addWidget(self.lbl_feedback, stretch=1)
        reset_layout.addLayout(reset_btn_layout)
        reset_layout.addStretch(1)
        grid.addWidget(reset_box, 1, 1)

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    def update_from_hardware(self, cfg: Optional[LightingConfig]):
        """Silently update radio buttons and dropdown from hardware state."""
        if not cfg:
            return
        self._block_signals = True
        self.current_debounce = cfg.debounce if cfg.debounce in (1, 4) else 4
        self.current_sleep_minutes = cfg.sleep_minutes if cfg.sleep_minutes in (0, 10, 20, 40, 60) else 10

        if self.current_debounce == 1:
            self.radio_gaming.setChecked(True)
        else:
            self.radio_office.setChecked(True)

        idx = self.combo_sleep.findData(self.current_sleep_minutes)
        if idx >= 0:
            self.combo_sleep.setCurrentIndex(idx)
            self._previous_sleep_index = idx
        self._block_signals = False

    def _load_hardware_state(self):
        """Read initial debounce and sleep settings from the keyboard."""
        cfg = self.lighting_mgr.get_current_lighting()
        self.update_from_hardware(cfg)

    def _load_autostart_state(self):
        """Read existing ~/.config/autostart/rkm87.desktop to restore checkboxes."""
        autostart_file = os.path.expanduser("~/.config/autostart/rkm87.desktop")
        self._block_signals = True
        if os.path.exists(autostart_file):
            self.chk_autostart.setChecked(True)
            self.chk_start_to_tray.setEnabled(True)
            try:
                with open(autostart_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    if "--tray" in content or "--minimized" in content:
                        self.chk_start_to_tray.setChecked(True)
                    else:
                        self.chk_start_to_tray.setChecked(False)
            except OSError:
                self.chk_start_to_tray.setChecked(False)
        else:
            self.chk_autostart.setChecked(False)
            self.chk_start_to_tray.setChecked(False)
            self.chk_start_to_tray.setEnabled(False)
        self._block_signals = False

    def _on_autostart_toggled(self, checked: bool):
        if self._block_signals:
            return
        self.chk_start_to_tray.setEnabled(checked)
        self._apply_autostart_config()

    def _on_start_to_tray_toggled(self, checked: bool):
        if self._block_signals:
            return
        self._apply_autostart_config()

    def _apply_autostart_config(self):
        autostart_file = os.path.expanduser("~/.config/autostart/rkm87.desktop")
        if not self.chk_autostart.isChecked():
            if os.path.exists(autostart_file):
                try:
                    os.remove(autostart_file)
                except OSError:
                    pass
            self.lbl_feedback.setText("✓ Autostart on login disabled")
            return

        user_bin_rkm87 = os.path.expanduser("~/.local/bin/rkm87")
        if os.path.exists(user_bin_rkm87):
            exec_cmd = user_bin_rkm87
            icon_path = os.path.expanduser("~/.RKLinux/data/icon.png")
            if not os.path.exists(icon_path):
                project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                icon_path = os.path.join(project_dir, "data", "icon.png")
        else:
            project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            local_bin = os.path.join(project_dir, "bin", "rkm87")
            if os.path.exists(local_bin):
                exec_cmd = local_bin
            else:
                venv_python = os.path.join(project_dir, ".venv", "bin", "python3")
                py_exec = venv_python if os.path.exists(venv_python) else sys.executable
                exec_cmd = f"{py_exec} {os.path.join(project_dir, 'main.py')}"
            icon_path = os.path.join(project_dir, "data", "icon.png")

        if self.chk_start_to_tray.isChecked():
            exec_cmd += " --tray"

        content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Royal Kludge M87 Studio
GenericName=Keyboard Driver & RGB Studio
Comment=Native Linux control suite, RGB lighting, LCD screen animations and key remapper for RK M87
Exec={exec_cmd}
Icon={icon_path}
Terminal=false
Categories=Utility;Settings;HardwareSettings;
Keywords=keyboard;rgb;rk;m87;sinowealth;
StartupNotify=false
X-GNOME-Autostart-enabled=true
"""
        try:
            with open(autostart_file, "w", encoding="utf-8") as f:
                f.write(content)
            tray_str = " (minimized to system tray)" if self.chk_start_to_tray.isChecked() else " (window opens on login)"
            self.lbl_feedback.setText(f"✓ Autostart on login enabled{tray_str}")
        except OSError as e:
            self.lbl_feedback.setText(f"❌ Failed to save autostart: {e}")

    def _on_debounce_toggled(self, btn_id: int, checked: bool):
        if not checked or self._block_signals:
            return
        self.current_debounce = btn_id
        self._apply_hardware_options()

    def _on_sleep_changed(self, index: int):
        if self._block_signals:
            return

        selected_val = self.combo_sleep.currentData()

        # Warning when "Never" (0) is selected
        if selected_val == 0:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("⚠️ Battery Drain & Health Warning")
            box.setText(
                "<h3>Disabling Wireless Sleep (Battery Drain Warning)</h3>"
                "<p>Setting the wireless sleep timer to <b>Never</b> keeps the keyboard microcontroller and LEDs powered continuously while running on battery.</p>"
                "<p>If left unplugged or forgotten, the battery will drain to <b>0%</b>, which will permanently degrade or destroy the rechargeable lithium battery cells.</p>"
                "<p><b>Are you sure you want to disable sleep?</b></p>"
            )
            btn_proceed = box.addButton("Yes, Disable Sleep", QMessageBox.AcceptRole)
            btn_cancel = box.addButton("Cancel (Keep Sleep Enabled)", QMessageBox.RejectRole)
            box.setDefaultButton(btn_cancel)
            box.exec()

            if box.clickedButton() != btn_proceed:
                # Revert combo box
                self._block_signals = True
                self.combo_sleep.setCurrentIndex(self._previous_sleep_index)
                self._block_signals = False
                return

        self._previous_sleep_index = index
        self.current_sleep_minutes = selected_val
        self._apply_hardware_options()

    def _apply_hardware_options(self):
        """Commit current debounce and sleep timer to hardware."""
        ok = self.lighting_mgr.set_hardware_options(self.current_debounce, self.current_sleep_minutes)
        if ok:
            mode_name = "Gaming (1ms)" if self.current_debounce == 1 else "Office (4ms)"
            sleep_str = f"{self.current_sleep_minutes}m" if self.current_sleep_minutes > 0 else "Never"
            self.lbl_feedback.setText(f"✓ Settings applied ({mode_name}, Sleep: {sleep_str})")
            self.options_changed.emit(self.current_debounce, self.current_sleep_minutes)
        else:
            self.lbl_feedback.setText("❌ Failed to apply settings (keyboard asleep or disconnected)")

    def _on_help_clicked(self):
        """Displays explanation of Reset Keyboard Data vs Restore Factory Settings."""
        QMessageBox.information(
            self,
            "💡 Reset Keyboard Data vs. Factory Restore",
            "<h3>Reset Keyboard Data vs. Factory Restore</h3>"
            "<p><b>🔄 Reset Keyboard Data:</b><br>"
            "Safely restores on-device key mapping scancodes (104 default keys), default RGB lighting profile "
            "(Rainbow mode, full brightness), and clears custom macros back to clean factory defaults in keyboard memory. "
            "Use this if keys stop reacting or lighting state becomes corrupted.</p>"
            "<p><b>⚠️ Note on 'Restore Factory Settings':</b><br>"
            "This is <i>not</i> a complete factory firmware re-flash. If you need to completely restore the factory default "
            "TFT screen GIF animation or perform a low-level factory flash, please use the official Windows Royal Kludge software in Wine.</p>",
        )

    def _on_reset_clicked(self):
        """Execute safe reset of keyboard data upon user confirmation."""
        confirm = QMessageBox.question(
            self,
            "Confirm Reset Keyboard Data",
            "Are you sure you want to reset all keyboard data?\n\n"
            "This will restore the factory default keymap scancodes, reset RGB lighting to Rainbow mode, "
            "and clear custom macros in keyboard memory.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )

        if confirm != QMessageBox.Yes:
            return

        self.btn_reset.setEnabled(False)
        self.lbl_feedback.setText("Resetting keyboard data...")

        ok = self.lighting_mgr.reset_keyboard_data(keymap_mgr=self.keymap_mgr)
        self.btn_reset.setEnabled(True)

        if ok:
            self._block_signals = True
            self.current_debounce = 4
            self.current_sleep_minutes = 10
            self.radio_office.setChecked(True)
            idx = self.combo_sleep.findData(10)
            if idx >= 0:
                self.combo_sleep.setCurrentIndex(idx)
                self._previous_sleep_index = idx
            self._block_signals = False

            self.lbl_feedback.setText("✓ Keyboard data successfully restored to factory defaults!")
            self.data_reset.emit()
        else:
            self.lbl_feedback.setText("❌ Reset failed (keyboard may be disconnected)")
