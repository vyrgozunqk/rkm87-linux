"""Interactive Key Remapping and Macro Studio tab."""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from rkm87.keymap import (
    HID_KEYS,
    MEDIA_KEYS,
    MOUSE_BUTTONS,
    KeyBinding,
    KeyMappingManager,
    Macro,
    MacroEvent,
)


class KeymapTab(QWidget):
    key_selected = Signal(str)  # emits key_id

    def __init__(self, keymap_mgr: KeyMappingManager, parent=None):
        super().__init__(parent)
        self.mgr = keymap_mgr
        self.selected_key_id: Optional[str] = None
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Left Column: Key Remapper
        left_box = QGroupBox("Key Assignment")
        left_box.setStyleSheet("QGroupBox { font-weight: bold; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 6px; margin-top: 10px; padding: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        left_layout = QVBoxLayout(left_box)
        left_layout.setSpacing(12)

        # Key selection
        row_key = QHBoxLayout()
        lbl_k = QLabel("Select Key:")
        lbl_k.setStyleSheet("color: #a1a1aa; font-size: 13px; min-width: 90px;")
        self.combo_keys = QComboBox()
        self.combo_keys.setStyleSheet("QComboBox { background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; padding: 6px 12px; font-size: 13px; }")
        for k in self.mgr.layout_keys:
            self.combo_keys.addItem(f"{k['name']} ({k['id']})", k["id"])
        self.combo_keys.currentIndexChanged.connect(self._on_key_combo_changed)
        row_key.addWidget(lbl_k)
        row_key.addWidget(self.combo_keys, stretch=1)
        left_layout.addLayout(row_key)

        # Current binding display
        self.lbl_current_binding = QLabel("Current Binding: Default")
        self.lbl_current_binding.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px; padding: 6px; background: #27272a; border-radius: 4px;")
        left_layout.addWidget(self.lbl_current_binding)

        # Action Type selector
        row_action = QHBoxLayout()
        lbl_act = QLabel("Action Type:")
        lbl_act.setStyleSheet("color: #a1a1aa; font-size: 13px; min-width: 90px;")
        self.combo_action_type = QComboBox()
        self.combo_action_type.setStyleSheet("QComboBox { background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; padding: 6px 12px; font-size: 13px; }")
        self.combo_action_type.addItems([
            "Default (Original Key)",
            "Remap to Keyboard Key",
            "Multimedia / System Action",
            "Mouse Button",
            "Disable Key"
        ])
        self.combo_action_type.currentIndexChanged.connect(self._on_action_type_changed)
        row_action.addWidget(lbl_act)
        row_action.addWidget(self.combo_action_type, stretch=1)
        left_layout.addLayout(row_action)

        # Secondary target selector
        self.row_target = QHBoxLayout()
        self.lbl_target = QLabel("Target:")
        self.lbl_target.setStyleSheet("color: #a1a1aa; font-size: 13px; min-width: 90px;")
        self.combo_target = QComboBox()
        self.combo_target.setStyleSheet("QComboBox { background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; padding: 6px 12px; font-size: 13px; }")
        self.row_target.addWidget(self.lbl_target)
        self.row_target.addWidget(self.combo_target, stretch=1)
        left_layout.addLayout(self.row_target)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_save_binding = QPushButton("Assign to Key")
        self.btn_save_binding.setStyleSheet("QPushButton { background-color: #3b82f6; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px; } QPushButton:hover { background-color: #2563eb; }")
        self.btn_save_binding.clicked.connect(self._on_save_binding)

        self.btn_reset_key = QPushButton("Reset Key")
        self.btn_reset_key.setStyleSheet("QPushButton { background-color: #3f3f46; color: white; font-weight: bold; padding: 8px 16px; border-radius: 6px; } QPushButton:hover { background-color: #52525b; }")
        self.btn_reset_key.clicked.connect(self._on_reset_key)

        btn_layout.addWidget(self.btn_save_binding)
        btn_layout.addWidget(self.btn_reset_key)
        left_layout.addLayout(btn_layout)

        left_layout.addStretch(1)

        # Commit to Hardware
        self.btn_apply_hardware = QPushButton("⚡ Apply Key Mappings to Keyboard")
        self.btn_apply_hardware.setStyleSheet("QPushButton { background-color: #10b981; color: white; font-weight: bold; padding: 10px 18px; border-radius: 6px; font-size: 14px; } QPushButton:hover { background-color: #059669; }")
        self.btn_apply_hardware.clicked.connect(self._on_apply_hardware)
        left_layout.addWidget(self.btn_apply_hardware)

        layout.addWidget(left_box, stretch=1)

        # Right Column: Macro Manager
        right_box = QGroupBox("Macro Studio")
        right_box.setStyleSheet("QGroupBox { font-weight: bold; color: #e4e4e7; border: 1px solid #3f3f46; border-radius: 6px; margin-top: 10px; padding: 15px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        right_layout = QVBoxLayout(right_box)
        right_layout.setSpacing(10)

        # Macro name input
        m_row = QHBoxLayout()
        lbl_mname = QLabel("Macro Name:")
        lbl_mname.setStyleSheet("color: #a1a1aa; font-size: 13px;")
        self.txt_macro_name = QLineEdit("Macro 1")
        self.txt_macro_name.setStyleSheet("QLineEdit { background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; padding: 6px 10px; }")
        m_row.addWidget(lbl_mname)
        m_row.addWidget(self.txt_macro_name, stretch=1)
        right_layout.addLayout(m_row)

        # Quick Macro Generator (Text to Keystrokes)
        lbl_text = QLabel("Quick Text Macro:")
        lbl_text.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        self.txt_quick_macro = QLineEdit()
        self.txt_quick_macro.setPlaceholderText("Type text to automate (e.g. 'sudo systemctl restart')...")
        self.txt_quick_macro.setStyleSheet("QLineEdit { background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; padding: 6px 10px; }")
        right_layout.addWidget(lbl_text)
        right_layout.addWidget(self.txt_quick_macro)

        # Repeat count
        rep_row = QHBoxLayout()
        lbl_rep = QLabel("Repeat Count:")
        lbl_rep.setStyleSheet("color: #a1a1aa; font-size: 13px;")
        self.spin_repeat = QSpinBox()
        self.spin_repeat.setRange(1, 100)
        self.spin_repeat.setValue(1)
        self.spin_repeat.setStyleSheet("QSpinBox { background-color: #27272a; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 4px; padding: 4px 8px; }")
        rep_row.addWidget(lbl_rep)
        rep_row.addWidget(self.spin_repeat)
        rep_row.addStretch(1)
        right_layout.addLayout(rep_row)

        # Macro events preview list
        self.list_macro_events = QListWidget()
        self.list_macro_events.setStyleSheet("QListWidget { background-color: #18181b; color: #e4e4e7; border: 1px solid #27272a; border-radius: 6px; padding: 6px; font-family: monospace; }")
        right_layout.addWidget(self.list_macro_events, stretch=1)

        # Macro buttons
        mbtn_layout = QHBoxLayout()
        self.btn_gen_macro = QPushButton("Generate Macro")
        self.btn_gen_macro.setStyleSheet("QPushButton { background-color: #38bdf8; color: #121214; font-weight: bold; padding: 6px 14px; border-radius: 6px; }")
        self.btn_gen_macro.clicked.connect(self._on_generate_macro)

        self.btn_assign_macro = QPushButton("Assign to Selected Key")
        self.btn_assign_macro.setStyleSheet("QPushButton { background-color: #f59e0b; color: #121214; font-weight: bold; padding: 6px 14px; border-radius: 6px; }")
        self.btn_assign_macro.clicked.connect(self._on_assign_macro)

        mbtn_layout.addWidget(self.btn_gen_macro)
        mbtn_layout.addWidget(self.btn_assign_macro)
        right_layout.addLayout(mbtn_layout)

        layout.addWidget(right_box, stretch=1)

        # Trigger initial selection
        self._on_key_combo_changed(0)

    def select_key(self, key_id: str):
        """Called when a key is clicked on the visual 2D canvas."""
        for i in range(self.combo_keys.count()):
            if self.combo_keys.itemData(i) == key_id:
                self.combo_keys.setCurrentIndex(i)
                break

    def _on_key_combo_changed(self, index: int):
        self.selected_key_id = self.combo_keys.currentData()
        if not self.selected_key_id:
            return

        binding = self.mgr.bindings.get(self.selected_key_id, KeyBinding())
        self.lbl_current_binding.setText(f"Current Binding: {binding.action_type.upper()} ({binding.target})")
        self.key_selected.emit(self.selected_key_id)

    def _on_action_type_changed(self, index: int):
        self.combo_target.clear()
        if index == 0:  # Default
            self.row_target.setEnabled(False)
            self.lbl_target.setText("Target:")
            self.combo_target.addItem("(Original Function)")
        elif index == 1:  # Remap Key
            self.row_target.setEnabled(True)
            self.lbl_target.setText("Key:")
            for name in sorted(HID_KEYS.keys()):
                self.combo_target.addItem(name, HID_KEYS[name])
        elif index == 2:  # Media
            self.row_target.setEnabled(True)
            self.lbl_target.setText("Action:")
            for name in sorted(MEDIA_KEYS.keys()):
                self.combo_target.addItem(name, MEDIA_KEYS[name])
        elif index == 3:  # Mouse
            self.row_target.setEnabled(True)
            self.lbl_target.setText("Button:")
            for name in sorted(MOUSE_BUTTONS.keys()):
                self.combo_target.addItem(name, MOUSE_BUTTONS[name])
        elif index == 4:  # Disabled
            self.row_target.setEnabled(False)
            self.lbl_target.setText("Target:")
            self.combo_target.addItem("(Key Disabled)")

    def _on_save_binding(self):
        if not self.selected_key_id:
            return
        idx = self.combo_action_type.currentIndex()
        if idx == 0:
            self.mgr.reset_key(self.selected_key_id)
        elif idx == 1:
            name = self.combo_target.currentText()
            code = self.combo_target.currentData()
            self.mgr.remap_key(self.selected_key_id, "hid_key", name, code=code)
        elif idx == 2:
            name = self.combo_target.currentText()
            code = self.combo_target.currentData()
            self.mgr.remap_key(self.selected_key_id, "media", name, code=code)
        elif idx == 3:
            name = self.combo_target.currentText()
            code = self.combo_target.currentData()
            self.mgr.remap_key(self.selected_key_id, "mouse", name, code=code)
        elif idx == 4:
            self.mgr.remap_key(self.selected_key_id, "disabled", "Disabled")

        binding = self.mgr.bindings.get(self.selected_key_id, KeyBinding())
        self.lbl_current_binding.setText(f"Current Binding: {binding.action_type.upper()} ({binding.target})")
        QMessageBox.information(self, "Key Assigned", f"Assigned '{binding.target}' to key {self.selected_key_id}.\nClick 'Apply Key Mappings' to commit to hardware.")

    def _on_reset_key(self):
        if self.selected_key_id:
            self.mgr.reset_key(self.selected_key_id)
            binding = self.mgr.bindings.get(self.selected_key_id, KeyBinding())
            self.lbl_current_binding.setText(f"Current Binding: {binding.action_type.upper()} ({binding.target})")

    def _on_generate_macro(self):
        text = self.txt_quick_macro.text()
        if not text:
            return

        self.list_macro_events.clear()
        events = []
        for ch in text:
            # Map character to HID key
            up = ch.upper()
            hid = HID_KEYS.get(up, 0x2C if ch == " " else 0)
            if hid > 0:
                events.append(MacroEvent(hid_code=hid, is_down=True, delay_ms=20))
                events.append(MacroEvent(hid_code=hid, is_down=False, delay_ms=20))
                self.list_macro_events.addItem(f"Press & Release '{ch}' (HID 0x{hid:02X}, 20ms)")

        macro = Macro(
            name=self.txt_macro_name.text(),
            id=1,
            repeat=self.spin_repeat.value(),
            events=events
        )
        self.mgr.macros[1] = macro
        QMessageBox.information(self, "Macro Generated", f"Generated macro with {len(events)} events.")

    def _on_assign_macro(self):
        if not self.selected_key_id:
            return
        if 1 not in self.mgr.macros:
            QMessageBox.warning(self, "No Macro", "Please click 'Generate Macro' first.")
            return

        macro = self.mgr.macros[1]
        self.mgr.remap_key(self.selected_key_id, "macro", macro.name, macro_id=1)
        binding = self.mgr.bindings.get(self.selected_key_id, KeyBinding())
        self.lbl_current_binding.setText(f"Current Binding: MACRO ({macro.name})")
        QMessageBox.information(self, "Macro Assigned", f"Assigned Macro '{macro.name}' to key {self.selected_key_id}.\nClick 'Apply Key Mappings' to commit.")

    def _on_apply_hardware(self):
        # 1. Apply any macros first
        for m in self.mgr.macros.values():
            self.mgr.apply_macro(m)

        # 2. Apply matrix
        ok = self.mgr.apply_matrix()
        if ok:
            QMessageBox.information(self, "Success", "Key mappings successfully sent to keyboard hardware!")
        else:
            QMessageBox.critical(self, "Failed", "Could not apply key mappings (keyboard might be asleep or disconnected).")
