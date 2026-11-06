"""Custom per-key RGB lighting configuration tab ("Gaoshou" mode)."""

import os
from typing import Dict, Optional, Set, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from rkm87.lighting import LightingManager
from .canvas import KeyboardCanvas


# Predefined key clusters based on data/layout.json key IDs and names
PRESET_CLUSTERS = {
    "wasd": {"W", "A", "S", "D"},
    "numbers": {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0"},
    "arrows": {"Up", "Down", "Left", "Right"},
    "f_keys": {f"F{i}" for i in range(1, 13)},
    "modifiers": {"LShift", "RShift", "LCtrl", "RCtrl", "LAlt", "RAlt", "LWin", "Space", "Tab", "Enter", "Back"},
}


class CustomLightingTab(QWidget):
    custom_applied = Signal(object, int)  # emits (dict of key_ident->rgb, brightness)

    def __init__(self, lighting_mgr: LightingManager, canvas: KeyboardCanvas, parent=None):
        super().__init__(parent)
        self.mgr = lighting_mgr
        self.canvas = canvas
        self.key_colors: Dict[str, Tuple[int, int, int]] = {}
        self.active_custom_rgb: Tuple[int, int, int] = (255, 0, 0)  # Default Red
        self._init_ui()
        self._load_initial_profile("wasd_gaming")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # 1. Quick Cluster Selection Helpers
        sel_box = QGroupBox("Quick Key Selection")
        sel_box.setStyleSheet("QGroupBox { font-weight: bold; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 6px; margin-top: 10px; padding: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        sel_layout = QGridLayout(sel_box)
        sel_layout.setSpacing(10)

        self.chk_wasd = QCheckBox("WASD")
        self.chk_numbers = QCheckBox("Numbers (1-0)")
        self.chk_arrows = QCheckBox("Arrow Keys")
        self.chk_fkeys = QCheckBox("Function Keys (F1-F12)")
        self.chk_mods = QCheckBox("Modifiers (Shift, Ctrl, Alt, Space...)")

        for chk in [self.chk_wasd, self.chk_numbers, self.chk_arrows, self.chk_fkeys, self.chk_mods]:
            chk.setStyleSheet("QCheckBox { color: #f4f4f5; font-size: 13px; font-weight: bold; } QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #71717a; border-radius: 3px; background: #27272a; } QCheckBox::indicator:checked { background: #38bdf8; border-color: #38bdf8; }")

        self.chk_wasd.toggled.connect(lambda c: self._on_cluster_toggle("wasd", c))
        self.chk_numbers.toggled.connect(lambda c: self._on_cluster_toggle("numbers", c))
        self.chk_arrows.toggled.connect(lambda c: self._on_cluster_toggle("arrows", c))
        self.chk_fkeys.toggled.connect(lambda c: self._on_cluster_toggle("f_keys", c))
        self.chk_mods.toggled.connect(lambda c: self._on_cluster_toggle("modifiers", c))

        sel_layout.addWidget(self.chk_wasd, 0, 0)
        sel_layout.addWidget(self.chk_numbers, 0, 1)
        sel_layout.addWidget(self.chk_arrows, 0, 2)
        sel_layout.addWidget(self.chk_fkeys, 1, 0)
        sel_layout.addWidget(self.chk_mods, 1, 1)

        # Batch Selection Buttons
        batch_layout = QHBoxLayout()
        btn_sel_all = QPushButton("Select All")
        btn_clear = QPushButton("Clear Selection")
        btn_invert = QPushButton("Invert Selection")

        for b in [btn_sel_all, btn_clear, btn_invert]:
            b.setStyleSheet("QPushButton { background: #3f3f46; color: #f4f4f5; border: 1px solid #52525b; border-radius: 4px; padding: 6px 12px; font-size: 12px; font-weight: bold; } QPushButton:hover { background: #52525b; }")

        btn_sel_all.clicked.connect(self._select_all_keys)
        btn_clear.clicked.connect(self._clear_selection)
        btn_invert.clicked.connect(self._invert_selection)

        batch_layout.addWidget(btn_sel_all)
        batch_layout.addWidget(btn_invert)
        batch_layout.addWidget(btn_clear)
        sel_layout.addLayout(batch_layout, 1, 2)

        layout.addWidget(sel_box)

        # 2. Color Application Controls
        color_box = QGroupBox("Color Palette && Actions")
        color_box.setStyleSheet("QGroupBox { font-weight: bold; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 6px; margin-top: 10px; padding: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        color_layout = QHBoxLayout(color_box)
        color_layout.setSpacing(10)

        # Preset swatches
        swatches = [
            ("Red", (255, 0, 0)),
            ("Green", (0, 255, 0)),
            ("Blue", (0, 0, 255)),
            ("Yellow", (255, 255, 0)),
            ("Pink", (255, 50, 130)),
            ("Cyan", (0, 255, 255)),
            ("White", (255, 255, 255)),
        ]
        for name, rgb in swatches:
            btn = QPushButton(name)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgb({rgb[0]},{rgb[1]},{rgb[2]});
                    color: {"#000000" if sum(rgb) > 400 else "#ffffff"};
                    font-weight: bold;
                    border: 2px solid #27272a;
                    border-radius: 6px;
                    padding: 8px 12px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    border: 2px solid #ffffff;
                }}
            """)
            btn.clicked.connect(lambda _, c=rgb: self._apply_color_to_selected(c))
            color_layout.addWidget(btn)

        # Custom Color Picker button
        self.btn_pick = QPushButton("🎨 Pick Custom...")
        self.btn_pick.setStyleSheet("QPushButton { background: #3f3f46; color: #f4f4f5; font-weight: bold; border: 2px solid #52525b; border-radius: 6px; padding: 8px 12px; font-size: 12px; } QPushButton:hover { background: #52525b; }")
        self.btn_pick.clicked.connect(self._open_custom_picker)
        color_layout.addWidget(self.btn_pick)

        # Turn Off Selected Keys button
        btn_turn_off = QPushButton("🌑 Turn Off Selected")
        btn_turn_off.setStyleSheet("QPushButton { background: #18181b; color: #ef4444; border: 1px solid #ef4444; font-weight: bold; border-radius: 6px; padding: 8px 12px; font-size: 12px; } QPushButton:hover { background: #ef4444; color: #ffffff; }")
        btn_turn_off.clicked.connect(lambda: self._apply_color_to_selected((0, 0, 0)))
        color_layout.addWidget(btn_turn_off)

        layout.addWidget(color_box)

        # 3. Profile Management & Apply
        prof_box = QGroupBox("Lighting Profile && Hardware Commit")
        prof_box.setStyleSheet("QGroupBox { font-weight: bold; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 6px; margin-top: 10px; padding: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        prof_layout = QHBoxLayout(prof_box)
        prof_layout.setSpacing(12)

        prof_label = QLabel("Profile:")
        prof_label.setStyleSheet("color: #a1a1aa; font-size: 13px; font-weight: bold;")
        self.combo_profiles = QComboBox()
        self.combo_profiles.setStyleSheet("QComboBox { background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; padding: 6px 12px; font-size: 13px; min-width: 150px; }")
        self._refresh_profile_list()
        self.combo_profiles.currentTextChanged.connect(self._on_profile_selected)

        btn_save = QPushButton("💾 Save As...")
        btn_save.setStyleSheet("QPushButton { background: #27272a; color: #38bdf8; border: 1px solid #38bdf8; border-radius: 4px; padding: 6px 12px; font-weight: bold; } QPushButton:hover { background: #38bdf8; color: #000000; }")
        btn_save.clicked.connect(self._save_profile_dialog)

        btn_del = QPushButton("🗑️ Delete")
        btn_del.setStyleSheet("QPushButton { background: #27272a; color: #71717a; border: 1px solid #52525b; border-radius: 4px; padding: 6px 10px; } QPushButton:hover { color: #ef4444; border-color: #ef4444; }")
        btn_del.clicked.connect(self._delete_current_profile)

        # Brightness
        b_label = QLabel("Brightness:")
        b_label.setStyleSheet("color: #a1a1aa; font-size: 13px; font-weight: bold; margin-left: 10px;")
        self.slider_bright = QSlider(Qt.Horizontal)
        self.slider_bright.setRange(0, 5)
        self.slider_bright.setValue(5)
        self.slider_bright.setStyleSheet("QSlider::groove:horizontal { height: 6px; background: #27272a; border-radius: 3px; } QSlider::sub-page:horizontal { background: #10b981; border-radius: 3px; } QSlider::handle:horizontal { background: #f4f4f5; width: 14px; margin-top: -4px; margin-bottom: -4px; border-radius: 7px; }")
        self.val_bright = QLabel("20 / 20")
        self.val_bright.setStyleSheet("color: #10b981; font-weight: bold; min-width: 50px;")
        self.slider_bright.valueChanged.connect(self._on_brightness_change)

        # Big Apply Button
        btn_apply = QPushButton("⚡ Apply to Keyboard")
        btn_apply.setStyleSheet("QPushButton { background: #10b981; color: #ffffff; font-weight: bold; font-size: 13px; border-radius: 6px; padding: 8px 18px; } QPushButton:hover { background: #059669; }")
        btn_apply.clicked.connect(self.apply_to_hardware)

        prof_layout.addWidget(prof_label)
        prof_layout.addWidget(self.combo_profiles)
        prof_layout.addWidget(btn_save)
        prof_layout.addWidget(btn_del)
        prof_layout.addWidget(b_label)
        prof_layout.addWidget(self.slider_bright)
        prof_layout.addWidget(self.val_bright)
        prof_layout.addWidget(btn_apply)

        layout.addWidget(prof_box)
        layout.addStretch(1)

    def _on_brightness_change(self, val):
        steps = [0, 4, 8, 12, 16, 20]
        self.val_bright.setText(f"{steps[val]} / 20")

    def _refresh_profile_list(self):
        current = self.combo_profiles.currentText()
        self.combo_profiles.blockSignals(True)
        self.combo_profiles.clear()
        profiles = self.mgr.list_custom_profiles()
        for p in profiles:
            self.combo_profiles.addItem(p)
        if current and self.combo_profiles.findText(current) >= 0:
            self.combo_profiles.setCurrentText(current)
        self.combo_profiles.blockSignals(False)

    def _canonical_key_id(self, key_ident: str) -> str:
        ident_clean = str(key_ident).strip().upper()
        for k in self.canvas.keys:
            if k.get("id", "").upper() == ident_clean or k.get("name", "").upper() == ident_clean:
                return k["id"]
        return str(key_ident)

    def _load_initial_profile(self, name: str):
        self._load_profile_data(name)

    def _on_profile_selected(self, name: str):
        if not name:
            return
        self._load_profile_data(name)

    def _load_profile_data(self, name: str):
        prof = self.mgr.load_custom_profile(name)
        if prof and "keys" in prof:
            self.key_colors.clear()
            for k, v in prof["keys"].items():
                cid = self._canonical_key_id(k)
                self.key_colors[cid] = tuple(v)
            self.canvas.set_custom_colors(self.key_colors)
            self.canvas.set_custom_mode(True)

    def _open_custom_picker(self):
        initial = QColor(self.active_custom_rgb[0], self.active_custom_rgb[1], self.active_custom_rgb[2])
        chosen = QColorDialog.getColor(initial, self, "Select Color for Selected Keys")
        if chosen.isValid():
            rgb = (chosen.red(), chosen.green(), chosen.blue())
            self.active_custom_rgb = rgb
            self._apply_color_to_selected(rgb)

    def _apply_color_to_selected(self, rgb: Tuple[int, int, int]):
        if not self.canvas.selected_keys:
            QMessageBox.information(self, "No Keys Selected", "Please select one or more keys on the canvas or using the quick-select checkboxes first.")
            return

        for kid in self.canvas.selected_keys:
            cid = self._canonical_key_id(kid)
            self.key_colors[cid] = rgb

        self.canvas.set_custom_colors(self.key_colors)
        self.canvas.set_custom_mode(True)

    def _on_cluster_toggle(self, cluster_name: str, checked: bool):
        names_to_match = PRESET_CLUSTERS.get(cluster_name, set())
        for k in self.canvas.keys:
            if k.get("name") in names_to_match:
                kid = k["id"]
                if checked:
                    self.canvas.selected_keys.add(kid)
                else:
                    self.canvas.selected_keys.discard(kid)
        self.canvas.update()

    def _select_all_keys(self):
        for k in self.canvas.keys:
            self.canvas.selected_keys.add(k["id"])
        self.canvas.update()

    def _clear_selection(self):
        self.canvas.selected_keys.clear()
        self.chk_wasd.setChecked(False)
        self.chk_numbers.setChecked(False)
        self.chk_arrows.setChecked(False)
        self.chk_fkeys.setChecked(False)
        self.chk_mods.setChecked(False)
        self.canvas.update()

    def _invert_selection(self):
        all_ids = {k["id"] for k in self.canvas.keys}
        self.canvas.selected_keys = all_ids - self.canvas.selected_keys
        self.canvas.update()

    def _save_profile_dialog(self):
        name, ok = QInputDialog.getText(self, "Save Profile", "Enter a name for this custom lighting profile:")
        if ok and name.strip():
            safe_name = name.strip().lower().replace(" ", "_")
            saved = self.mgr.save_custom_profile(safe_name, self.key_colors)
            if saved:
                self._refresh_profile_list()
                self.combo_profiles.setCurrentText(safe_name)
                QMessageBox.information(self, "Profile Saved", f"Profile '{name}' saved successfully!")
            else:
                QMessageBox.critical(self, "Save Error", "Failed to save profile.")

    def _delete_current_profile(self):
        current = self.combo_profiles.currentText()
        if not current:
            return
        res = QMessageBox.question(self, "Confirm Delete", f"Are you sure you want to delete profile '{current}'?", QMessageBox.Yes | QMessageBox.No)
        if res == QMessageBox.Yes:
            self.mgr.delete_custom_profile(current)
            self._refresh_profile_list()

    def apply_to_hardware(self):
        steps = [0, 4, 8, 12, 16, 20]
        bright = steps[self.slider_bright.value()]
        ok = self.mgr.set_custom_matrix_lighting(self.key_colors, brightness=bright)
        if ok:
            self.custom_applied.emit(self.key_colors, bright)
            QMessageBox.information(self, "Applied", "Custom lighting committed to keyboard successfully!")
        else:
            QMessageBox.warning(self, "Device Error", "Failed to commit lighting. Ensure the keyboard is connected and awake.")
