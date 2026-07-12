"""Welcome page for the setup wizard.

Always shown first. Three options:

- **Use defaults** — adopt the v1 zero-config (faster_whisper + rules cleanup,
  no API key, ctrl+space hotkey). Skips most subsequent pages.
- **Customize** — proceed through every page.
- **Restore from backup** — open a file dialog, load a ``.bak.*`` file.

The page also exposes a checkbox for "Show this wizard every time I launch
agentvoca" so users can opt out of the always-open behaviour.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtWidgets

from agentvoca.setup.controllers.config_controller import defaults_controller
from agentvoca.setup.first_run import set_wizard_auto_open
from agentvoca.setup.pages.base import ConfigPage

if TYPE_CHECKING:
    pass


class WelcomePage(ConfigPage):
    title = "Welcome to agentvoca"
    subtitle = (
        "Set up your voice dictation in a few steps. "
        "You can change everything later from the Settings window."
    )

    def _build(self) -> None:
        super()._build()
        layout = self._body_layout

        # Banner surfaced when the app was launched with a config that could
        # not be fully loaded (e.g. a missing API-key env var). Hidden unless
        # ``show_startup_warning`` is called by the wizard. Replaces the old
        # standalone "Config needs attention" message box.
        self._warning_banner = QtWidgets.QLabel()
        self._warning_banner.setWordWrap(True)
        self._warning_banner.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._warning_banner.setStyleSheet(
            "background-color: #4d3b00; color: #ffd666;"
            " border: 1px solid #8a6d00; border-radius: 6px; padding: 10px;"
        )
        self._warning_banner.setVisible(False)
        layout.addWidget(self._warning_banner)

        intro = QtWidgets.QLabel(
            "agentvoca listens to your microphone, transcribes speech, "
            "and types the result wherever your cursor is. The Setup wizard "
            "will configure everything end-to-end so you don't have to edit "
            "a config file."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # Three big buttons, vertically stacked.
        defaults_btn = QtWidgets.QPushButton("Use defaults (fast, offline)")
        defaults_btn.setMinimumHeight(44)
        defaults_btn.clicked.connect(self._on_use_defaults)
        layout.addWidget(defaults_btn)

        customize_btn = QtWidgets.QPushButton("Customize (recommended)")
        customize_btn.setMinimumHeight(44)
        customize_btn.clicked.connect(self._on_customize)
        layout.addWidget(customize_btn)

        restore_btn = QtWidgets.QPushButton("Restore from backup…")
        restore_btn.setMinimumHeight(36)
        restore_btn.clicked.connect(self._on_restore_from_backup)
        layout.addWidget(restore_btn)

        layout.addSpacing(12)

        self._auto_open_check = QtWidgets.QCheckBox(
            "Show this wizard every time I launch agentvoca"
        )
        self._auto_open_check.setChecked(True)
        self._auto_open_check.toggled.connect(set_wizard_auto_open)
        layout.addWidget(self._auto_open_check)

        layout.addStretch()

        # Version + docs links
        try:
            from agentvoca import __version__  # noqa: PLC0415

            version_text = f"agentvoca v{__version__}"
        except ImportError:
            version_text = "agentvoca"
        version_label = QtWidgets.QLabel(version_text)
        version_label.setStyleSheet("color: #888;")
        layout.addWidget(version_label)

    def show_startup_warning(self, message: str) -> None:
        """Display an amber banner explaining a config that failed to load.

        Called by the wizard when the app was started with an invalid config
        (e.g. a remote provider whose API-key env var is unset). The user can
        fix it via "Customize", start over with "Use defaults", or load a
        good "Restore from backup".
        """
        self._warning_banner.setText(
            "<b>Your saved config could not be fully loaded.</b><br>"
            f"{message}<br><br>"
            "Fix it below — <b>Customize</b> to edit it, <b>Use defaults</b> to "
            "start fresh, or <b>Restore from backup</b>. agentvoca is running on "
            "safe defaults until you save."
        )
        self._warning_banner.setVisible(True)

    # ── Slots ──────────────────────────────────────────────────────────

    def _on_use_defaults(self) -> None:
        """Reset the controller to v1 zero-config and jump to the finish page."""
        if not self._confirm_reset():
            return
        defaults = defaults_controller(self.controller.path)
        self.controller.replace_draft(defaults.draft)
        if self._wizard() is not None:
            # Jump to the last page so the user can review and save.
            self._wizard().next()  # Advance past Welcome once, then jump.

    def _on_customize(self) -> None:
        """No-op: customize means letting the wizard proceed naturally."""
        return

    def _on_restore_from_backup(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Restore config from backup",
            str(Path.home() / ".agentvoca"),
            "YAML backups (*.yaml.bak.* *.yaml);;All files (*)",
        )
        if not path:
            return
        try:
            from agentvoca.setup.persistence import load_from_disk  # noqa: PLC0415

            loaded = load_from_disk(path)
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Restore failed", f"Could not load backup:\n{exc}")
            return
        self.controller.replace_draft(loaded)
        QtWidgets.QMessageBox.information(
            self, "Restored", "Backup loaded. Continue to review and save."
        )

    # ── Helpers ────────────────────────────────────────────────────────

    def _confirm_reset(self) -> bool:
        result = QtWidgets.QMessageBox.question(
            self,
            "Reset to defaults?",
            "This will replace any unsaved changes with the v1 zero-config defaults. Continue?",
        )
        return result == QtWidgets.QMessageBox.StandardButton.Yes

    def _wizard(self) -> QtWidgets.QWizard | None:
        """Return the enclosing QWizard, if any (None inside the settings window)."""
        parent = self.parent()
        while parent is not None and not isinstance(parent, QtWidgets.QWizard):
            parent = parent.parent()
        return parent  # type: ignore[return-value]
