"""Tabbed settings window — replaces the read-only ``app/settings.py``.

Wraps the same page widgets as the wizard so both UIs stay in lockstep. Save
behaviour mirrors the wizard (validate → persist → mark first-run complete),
plus a banner that lists fields needing an app restart.

The window talks to ``ConfigController`` exactly the same way the wizard does.
Only the chrome differs.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from agentvoca.setup.pages import (
    AdvancedPage,
    AppBasicsPage,
    AsrPage,
    AudioPage,
    CleanupPage,
    HotkeysPage,
    VocabSnippetsPage,
    WelcomePage,
)

if TYPE_CHECKING:
    from agentvoca.setup.controllers.config_controller import ConfigController, SaveResult

logger = logging.getLogger(__name__)


class SettingsWindow(QtWidgets.QMainWindow):
    """Tabbed editor for ``FullConfig`` with apply / discard / restart banner."""

    # Emitted whenever a save succeeds. The payload is the new ``FullConfig``
    # so main.py can hot-apply supported fields without a restart.
    config_saved = QtCore.Signal(object)

    def __init__(
        self,
        controller: "ConfigController",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller

        self.setWindowTitle("agentvoca Settings")
        self.resize(820, 640)

        # Persistent on top across closes so the user doesn't lose it.
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)

        self._build()

    # ── Construction ───────────────────────────────────────────────────

    def _build(self) -> None:
        central = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Restart banner — only shown when there are pending-restart changes.
        self._banner = QtWidgets.QFrame()
        self._banner.setObjectName("restartBanner")
        self._banner.setStyleSheet(
            "QFrame#restartBanner { background: #fff3cd; border: 1px solid #ffe69c; }"
        )
        banner_layout = QtWidgets.QHBoxLayout(self._banner)
        self._banner_label = QtWidgets.QLabel()
        self._banner_label.setWordWrap(True)
        self._banner_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        banner_layout.addWidget(self._banner_label, stretch=1)
        self._restart_btn = QtWidgets.QPushButton("Restart now")
        self._restart_btn.clicked.connect(self._on_restart)
        banner_layout.addWidget(self._restart_btn)
        self._banner.setVisible(False)
        layout.addWidget(self._banner)

        # Tab widget
        self._tabs = QtWidgets.QTabWidget()
        layout.addWidget(self._tabs, stretch=1)

        for page_cls in (
            WelcomePage,
            AppBasicsPage,
            AudioPage,
            AsrPage,
            CleanupPage,
            HotkeysPage,
            VocabSnippetsPage,
            AdvancedPage,
        ):
            page = page_cls(self._controller)
            self._tabs.addTab(page, page.title)

        # Bottom button row
        button_row = QtWidgets.QHBoxLayout()
        self._path_label = QtWidgets.QLabel(f"Config: {self._controller.path}")
        self._path_label.setStyleSheet("color: #666; padding: 0 8px;")
        button_row.addWidget(self._path_label, stretch=1)

        self._discard_btn = QtWidgets.QPushButton("Discard changes")
        self._discard_btn.clicked.connect(self._on_discard)
        button_row.addWidget(self._discard_btn)

        self._apply_btn = QtWidgets.QPushButton("Apply")
        self._apply_btn.clicked.connect(self._on_apply)
        button_row.addWidget(self._apply_btn)

        self._save_btn = QtWidgets.QPushButton("Save")
        self._save_btn.setDefault(True)
        self._save_btn.clicked.connect(self._on_save)
        button_row.addWidget(self._save_btn)

        button_widget = QtWidgets.QWidget()
        button_widget.setLayout(button_row)
        layout.addWidget(button_widget)

        self.setCentralWidget(central)
        self._refresh()

    # ── State helpers ──────────────────────────────────────────────────

    def _collect(self) -> None:
        """Push every page's UI state back into the controller draft."""
        for i in range(self._tabs.count()):
            page = self._tabs.widget(i)
            page.save_to_controller()

    def _refresh(self) -> None:
        """Reload every page from the controller and update the banner."""
        for i in range(self._tabs.count()):
            self._tabs.widget(i).load_from_controller()
        self._update_banner()
        self._update_button_states()

    def _update_banner(self) -> None:
        restart = self._controller.restart_paths()
        if restart:
            items = "<br>".join(f"• <code>{path}</code>" for path in restart)
            self._banner_label.setText(
                f"<b>Restart required</b> for the following settings:<br>{items}"
            )
            self._banner.setVisible(True)
        else:
            self._banner.setVisible(False)

    def _update_button_states(self) -> None:
        dirty = self._controller.is_dirty()
        self._apply_btn.setEnabled(dirty)
        self._discard_btn.setEnabled(dirty)
        self._save_btn.setEnabled(dirty)

    # ── Slots ──────────────────────────────────────────────────────────

    def _on_apply(self) -> None:
        self._collect()
        result = self._controller.save()
        self._handle_save_result(result, close=False)

    def _on_save(self) -> None:
        self._collect()
        result = self._controller.save()
        self._handle_save_result(result, close=True)

    def _on_discard(self) -> None:
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Discard changes?",
            "All unsaved changes will be reverted.",
        )
        if confirm == QtWidgets.QMessageBox.StandardButton.Yes:
            self._controller.revert()
            self._refresh()

    def _on_restart(self) -> None:
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Restart agentvoca?",
            "Quit and re-launch so the new settings take effect?",
        )
        if confirm == QtWidgets.QMessageBox.StandardButton.Yes:
            QtWidgets.QApplication.instance().quit()

    # ── Helpers ────────────────────────────────────────────────────────

    def _handle_save_result(self, result: "SaveResult", close: bool) -> None:
        if not result.success:
            QtWidgets.QMessageBox.critical(
                self,
                "Save failed",
                f"Could not write config:\n\n{result.error}",
            )
            return

        if result.success:
            try:
                self.config_saved.emit(self._controller.draft)
            except Exception:
                logger.exception("config_saved listener raised")

        if result.restart_paths:
            details = "\n".join(f"• {p}" for p in result.restart_paths)
            QtWidgets.QMessageBox.information(
                self,
                "Settings saved",
                f"Some settings require a restart:\n\n{details}",
            )
        if close:
            self.close()
        else:
            self._refresh()

    # ── Qt overrides ───────────────────────────────────────────────────

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._controller.is_dirty():
            choice = QtWidgets.QMessageBox.question(
                self,
                "Unsaved changes",
                "You have unsaved changes. Save before closing?",
                QtWidgets.QMessageBox.StandardButton.Save
                | QtWidgets.QMessageBox.StandardButton.Discard
                | QtWidgets.QMessageBox.StandardButton.Cancel,
            )
            if choice == QtWidgets.QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if choice == QtWidgets.QMessageBox.StandardButton.Save:
                self._on_save()
                if self._controller.is_dirty():
                    event.ignore()
                    return
        event.accept()
