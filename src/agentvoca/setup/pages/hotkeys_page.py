"""Hotkeys page — one preset dropdown per action."""

from __future__ import annotations

from PySide6 import QtWidgets

from agentvoca.setup.controllers.hotkey_presets import (
    ALL_ACTIONS,
    CUSTOM,
    find_preset,
    labels_for_dropdown,
    value_for_label,
)
from agentvoca.setup.pages.base import ConfigPage


class HotkeysPage(ConfigPage):
    title = "Hotkeys"
    subtitle = "Pick a preset for each action. Optional hotkeys can be disabled."

    def _build(self) -> None:
        super()._build()
        layout = self._body_layout

        self._rows: list[
            tuple[str, QtWidgets.QComboBox, QtWidgets.QLineEdit, QtWidgets.QLabel]
        ] = []

        for action in ALL_ACTIONS:
            row_layout = QtWidgets.QHBoxLayout()
            label = QtWidgets.QLabel(action.label)
            label.setMinimumWidth(180)
            label.setToolTip(action.description)
            row_layout.addWidget(label)

            combo = QtWidgets.QComboBox()
            combo.setMinimumWidth(220)
            combo.addItem("(custom — advanced)", CUSTOM)
            for label_text in labels_for_dropdown():
                if action.required and label_text == "(disabled)":
                    continue
                combo.addItem(label_text)
            combo.currentIndexChanged.connect(
                lambda _idx, field=action.config_field: self._on_combo_changed(field)
            )
            row_layout.addWidget(combo)

            custom = QtWidgets.QLineEdit()
            custom.setPlaceholderText("e.g. ctrl+shift+z")
            custom.setVisible(False)
            row_layout.addWidget(custom)

            hint = QtWidgets.QLabel("")
            hint.setStyleSheet("color: #b36400;")
            hint.setWordWrap(True)
            row_layout.addWidget(hint, stretch=1)

            layout.addLayout(row_layout)
            self._rows.append((action.config_field, combo, custom, hint))

        layout.addStretch()

    def _on_combo_changed(self, field: str) -> None:
        for f, combo, custom, hint in self._rows:
            if f != field:
                continue
            label = combo.currentText()
            value = value_for_label(label)
            if value == CUSTOM:
                hint.setText("Enter a valid combination.")
                custom.setVisible(True)
            else:
                preset = find_preset(value)
                hint.setText(preset.warning if preset and preset.warning else "")
                custom.setVisible(False)

    # ── Load / save ────────────────────────────────────────────────────

    def load_from_controller(self) -> None:
        c = self.controller.draft
        for field, combo, custom, _hint in self._rows:
            section_name, key = field.split(".", 1)
            value = getattr(getattr(c, section_name), key)
            preset = find_preset(value)
            if preset is not None:
                idx = combo.findText(preset.label)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    continue
            # Custom value — switch to the (custom) row
            combo.setCurrentIndex(combo.findData(CUSTOM))
            custom.setText(value or "")
            custom.setVisible(True)

    def save_to_controller(self) -> None:
        updates: dict[str, dict[str, str | None]] = {}
        for field, combo, custom, _hint in self._rows:
            section_name, key = field.split(".", 1)
            value = value_for_label(combo.currentText())
            if value == CUSTOM:
                value = custom.text().strip() or None
            updates.setdefault(section_name, {})[key] = value
        self.controller.update_section(**updates)
