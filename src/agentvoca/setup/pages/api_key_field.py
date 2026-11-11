"""Inline API-key editor: paste a key, choose how long to keep it, delete it."""

from __future__ import annotations

import datetime as _dt
from typing import Callable

from PySide6 import QtCore, QtWidgets

from agentvoca import keystore


class ApiKeyField(QtWidgets.QWidget):
    """Paste-and-save API key widget shared by every provider page.

    ``env_name`` returns the env var the key belongs to; it is re-evaluated on
    every action so the field follows endpoint / name edits on the page.
    """

    key_changed = QtCore.Signal(str)

    def __init__(
        self,
        env_name: Callable[[], str | None],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._env_name = env_name

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        row = QtWidgets.QHBoxLayout()
        self._value = QtWidgets.QLineEdit()
        self._value.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self._value.setPlaceholderText("Paste your API key")
        row.addWidget(self._value, stretch=1)
        self._retention = QtWidgets.QComboBox()
        for label, value in keystore.RETENTION_CHOICES:
            self._retention.addItem(label, value)
        row.addWidget(self._retention)
        self._save_btn = QtWidgets.QPushButton("Save key")
        self._save_btn.clicked.connect(self._on_save)
        row.addWidget(self._save_btn)
        self._delete_btn = QtWidgets.QPushButton("Delete key")
        self._delete_btn.clicked.connect(self._on_delete)
        row.addWidget(self._delete_btn)
        outer.addLayout(row)

        self._status = QtWidgets.QLabel()
        self._status.setWordWrap(True)
        outer.addWidget(self._status)

        self.refresh()

    # ── Public ─────────────────────────────────────────────────────────

    def commit_pending(self) -> None:
        """Save a pasted-but-unsaved key (called when the page is saved)."""
        if self._value.text().strip():
            self._save(confirm_fallback=False)

    def refresh(self) -> None:
        name = self._env_name() or ""
        status = keystore.key_status(name)
        self._delete_btn.setEnabled(status.source in ("saved", "session"))
        if status.retention:
            idx = self._retention.findData(status.retention)
            if idx >= 0:
                self._retention.setCurrentIndex(idx)
        if not name:
            self._set_status("This endpoint does not need an API key.", "#666")
        elif status.source == "saved":
            if status.expires_at:
                when = _dt.datetime.fromtimestamp(status.expires_at).strftime("%Y-%m-%d")
                keep = f"deleted automatically on {when}"
            else:
                keep = "kept until you delete it"
            self._set_status(f"✓ Key saved securely (…{status.preview}), {keep}.", "#1f8a3a")
        elif status.source == "session":
            self._set_status(
                f"✓ Key set (…{status.preview}). It is deleted when AgentVoca closes.",
                "#1f8a3a",
            )
        elif status.source == "environment":
            self._set_status(
                f"✓ Using {name} from your environment (…{status.preview}).", "#1f8a3a"
            )
        else:
            self._set_status("No API key saved yet.", "#b36400")

    # ── Slots ──────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        if not self._value.text().strip():
            QtWidgets.QMessageBox.warning(self, "No key", "Paste an API key first.")
            return
        self._save(confirm_fallback=True)

    def _save(self, *, confirm_fallback: bool) -> None:
        name = self._env_name()
        if not name:
            return
        retention = self._retention.currentData() or keystore.KEEP_FOREVER
        persisted = keystore.save_key(name, self._value.text().strip(), retention)
        self._value.clear()
        if not persisted and retention != keystore.KEEP_SESSION and confirm_fallback:
            QtWidgets.QMessageBox.information(
                self,
                "Key kept for this session only",
                "No secure credential store is available on this system, so the "
                "key will be forgotten when AgentVoca closes.",
            )
        self.refresh()
        self.key_changed.emit(name)

    def _on_delete(self) -> None:
        name = self._env_name()
        if not name:
            return
        confirm = QtWidgets.QMessageBox.question(
            self, "Delete API key?", f"Delete the saved key for {name}?"
        )
        if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        keystore.delete_key(name)
        self.refresh()
        self.key_changed.emit(name)

    def _set_status(self, text: str, color: str) -> None:
        self._status.setText(text)
        self._status.setStyleSheet(f"color: {color};")
