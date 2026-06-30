"""App basics page — language hint, recording mode, debug toggle."""

from __future__ import annotations

from PySide6 import QtWidgets

from agentvoca.setup.pages.base import ConfigPage

_MODE_OPTIONS = [
    ("Toggle (press once to start, once to stop)", "toggle"),
    ("Push-to-talk (hold to record)", "push_to_talk"),
    ("Auto-stop (VAD detects silence)", "auto_stop"),
]

_PROFILE_OPTIONS = [
    ("Standard", "standard"),
    ("Light (punctuation only)", "light"),
    ("Technical (preserve code)", "technical"),
    ("Professional (formal)", "professional"),
    ("Raw (no cleanup)", "raw"),
]


class AppBasicsPage(ConfigPage):
    title = "App basics"
    subtitle = "Set your language, recording trigger, and cleanup style."

    def _build(self) -> None:
        super()._build()
        layout = self._body_layout

        form = QtWidgets.QFormLayout()
        form.setSpacing(10)

        self._language = QtWidgets.QLineEdit()
        self._language.setPlaceholderText("auto, en, de, fr, …")
        form.addRow("Language hint:", self._language)

        self._mode = QtWidgets.QComboBox()
        for label, _value in _MODE_OPTIONS:
            self._mode.addItem(label)
        form.addRow("Recording mode:", self._mode)

        self._profile = QtWidgets.QComboBox()
        for label, _value in _PROFILE_OPTIONS:
            self._profile.addItem(label)
        form.addRow("Default cleanup style:", self._profile)

        self._debug = QtWidgets.QCheckBox("Enable debug logging")
        form.addRow("", self._debug)

        layout.addLayout(form)
        layout.addStretch()

    def load_from_controller(self) -> None:
        c = self.controller.draft
        self._language.setText(c.app.language)
        for i, (_, value) in enumerate(_MODE_OPTIONS):
            if value == c.app.mode:
                self._mode.setCurrentIndex(i)
                break
        for i, (_, value) in enumerate(_PROFILE_OPTIONS):
            if value == c.app.profile:
                self._profile.setCurrentIndex(i)
                break
        self._debug.setChecked(c.app.debug)

    def save_to_controller(self) -> None:
        mode_value = _MODE_OPTIONS[self._mode.currentIndex()][1]
        profile_value = _PROFILE_OPTIONS[self._profile.currentIndex()][1]
        self.controller.update_section(
            app={
                "language": self._language.text().strip() or "auto",
                "mode": mode_value,
                "profile": profile_value,
                "debug": self._debug.isChecked(),
            }
        )
