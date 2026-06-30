"""Env-var helper dialog.

Shown when the user clicks "Set API key now" on the ASR or Cleanup page.
Displays:

- The current status of the env var.
- A password-style input for the value.
- A "Set for this session" button that mutates ``os.environ``.
- Three read-only fields with copyable persistence snippets for the major
  shells (PowerShell, bash/zsh, fish).

The dialog never writes the value to disk. The user pastes the snippet into
their own shell manually.
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from agentvoca.setup.controllers.env_helper import (
    EnvStatus,
    all_snippets,
    set_for_session,
    unset_for_session,
)


class EnvHelperDialog(QtWidgets.QDialog):
    """Modal dialog to inspect / set an env var with copyable snippets."""

    def __init__(
        self,
        env_var_name: str,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Set {env_var_name}")
        self.setModal(True)
        self.setMinimumWidth(560)

        self._env_var_name = env_var_name
        self._build_ui()
        self._refresh_status()

    # ── UI construction ────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout()
        layout.setSpacing(10)

        # Status row
        self._status_label = QtWidgets.QLabel()
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Value input
        value_layout = QtWidgets.QFormLayout()
        self._value_input = QtWidgets.QLineEdit()
        self._value_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self._value_input.setPlaceholderText("Paste your API key here…")
        value_layout.addRow("Value:", self._value_input)
        layout.addLayout(value_layout)

        # Session buttons
        button_row = QtWidgets.QHBoxLayout()
        self._set_session_btn = QtWidgets.QPushButton("Set for this session only")
        self._set_session_btn.clicked.connect(self._on_set_session)
        self._unset_session_btn = QtWidgets.QPushButton("Clear (this session)")
        self._unset_session_btn.clicked.connect(self._on_unset_session)
        button_row.addWidget(self._set_session_btn)
        button_row.addWidget(self._unset_session_btn)
        button_row.addStretch()
        layout.addLayout(button_row)

        # Persistence snippets
        snippets_label = QtWidgets.QLabel(
            "To make this env var permanent, paste the matching line into "
            "your shell profile. AgentVoca never stores the value."
        )
        snippets_label.setWordWrap(True)
        snippets_label.setStyleSheet("color: #666;")
        layout.addWidget(snippets_label)

        for shell_name, snippet in all_snippets(self._env_var_name, "<your-api-key>").items():
            group = QtWidgets.QGroupBox(shell_name)
            group_layout = QtWidgets.QHBoxLayout(group)
            snippet_edit = QtWidgets.QPlainTextEdit(snippet)
            snippet_edit.setReadOnly(True)
            snippet_edit.setMaximumHeight(70)
            group_layout.addWidget(snippet_edit)
            copy_btn = QtWidgets.QPushButton("Copy")
            copy_btn.clicked.connect(lambda _checked=False, s=snippet: self._copy_to_clipboard(s))
            group_layout.addWidget(copy_btn, alignment=QtCore.Qt.AlignmentFlag.AlignTop)
            layout.addWidget(group)

        # Close
        close_row = QtWidgets.QHBoxLayout()
        close_row.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self.setLayout(layout)

    # ── Status refresh ─────────────────────────────────────────────────

    def _refresh_status(self) -> None:
        status = EnvStatus.probe(self._env_var_name)
        if status.is_set:
            self._status_label.setText(
                f"✓ <b>{self._env_var_name}</b> is set in this session (…{status.value_preview})."
            )
            self._status_label.setStyleSheet("color: #1f8a3a;")
        else:
            self._status_label.setText(f"⚠ <b>{self._env_var_name}</b> is not set in this session.")
            self._status_label.setStyleSheet("color: #b36400;")

    # ── Slots ──────────────────────────────────────────────────────────

    def _on_set_session(self) -> None:
        value = self._value_input.text()
        if not value:
            QtWidgets.QMessageBox.warning(
                self, "Empty value", "Paste an API key before setting it."
            )
            return
        set_for_session(self._env_var_name, value)
        self._refresh_status()
        # Also push the same line to the PowerShell snippet field as a hint.
        self._value_input.clear()

    def _on_unset_session(self) -> None:
        unset_for_session(self._env_var_name)
        self._refresh_status()

    def _copy_to_clipboard(self, text: str) -> None:
        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
