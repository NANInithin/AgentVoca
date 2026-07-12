"""Cleanup page — provider, style, endpoint, API key."""

from __future__ import annotations

import logging
import os

from PySide6 import QtCore, QtWidgets

from agentvoca.setup.controllers.model_catalog import ModelCatalog
from agentvoca.setup.pages._combobox_utils import resolve_editable_combo_id
from agentvoca.setup.pages.base import ConfigPage
from agentvoca.setup.pages.env_helper_dialog import EnvHelperDialog

logger = logging.getLogger(__name__)

_STYLE_OPTIONS = [
    ("Standard (remove fillers, punctuation)", "standard"),
    ("Light (punctuation only)", "light"),
    ("Technical (preserve code)", "technical"),
    ("Professional (formal)", "professional"),
    ("Raw (no cleanup)", "raw"),
    ("Custom (use your own prompt file)", "custom"),
]


class CleanupPage(ConfigPage):
    title = "Cleanup"
    subtitle = "Polish the transcript after transcription."

    # Emitted from the model-catalog worker thread once a fetch completes.
    # Qt automatically queues cross-thread signal emissions onto the
    # receiver's (GUI) thread, which is what actually gets us back onto the
    # main loop safely — a bare QTimer.singleShot() called from a thread
    # with no Qt event loop of its own never fires.
    _fetch_result = QtCore.Signal(object, object)

    def __init__(self, controller=None) -> None:
        # Catalog used to populate the LLM-model dropdown. Held on the page
        # so the cache survives across navigation away and back.
        self._model_catalog = ModelCatalog()
        self._fetch_in_flight: bool = False
        super().__init__(controller)
        self._fetch_result.connect(self._apply_fetch_result)

    def _build(self) -> None:
        super()._build()
        layout = self._body_layout

        # Three provider radios
        provider_row = QtWidgets.QHBoxLayout()
        self._off_btn = QtWidgets.QRadioButton("Off (insert raw transcript)")
        self._rules_btn = QtWidgets.QRadioButton("Rules (offline, no API key)")
        self._llm_btn = QtWidgets.QRadioButton("LLM (OpenAI-compatible)")
        self._rules_btn.setChecked(True)
        provider_row.addWidget(self._off_btn)
        provider_row.addWidget(self._rules_btn)
        provider_row.addWidget(self._llm_btn)
        provider_row.addStretch()
        layout.addLayout(provider_row)

        # Stack for provider-specific options
        self._stack = QtWidgets.QStackedWidget()

        # Off — nothing
        self._stack.addWidget(QtWidgets.QLabel("Raw transcript will be inserted."))

        # Rules — style + warm-up
        rules_page = QtWidgets.QWidget()
        rules_layout = QtWidgets.QFormLayout(rules_page)
        self._rules_style = QtWidgets.QComboBox()
        for label, value in _STYLE_OPTIONS[:5]:
            self._rules_style.addItem(label, value)
        rules_layout.addRow("Style:", self._rules_style)
        self._rules_warm_up = QtWidgets.QCheckBox("Warm up at startup")
        self._rules_warm_up.setChecked(True)
        rules_layout.addRow("", self._rules_warm_up)
        self._stack.addWidget(rules_page)

        # LLM — endpoint + env + style
        llm_page = QtWidgets.QWidget()
        llm_layout = QtWidgets.QFormLayout(llm_page)
        self._llm_endpoint = QtWidgets.QLineEdit()
        self._llm_endpoint.setPlaceholderText("https://api.openai.com/v1")
        # Editing the endpoint invalidates any cached model list so the next
        # "Fetch models" call hits the new server.
        self._llm_endpoint.textChanged.connect(lambda _t: self._model_catalog.clear_cache())
        llm_layout.addRow("Endpoint:", self._llm_endpoint)

        # Model — combobox populated by "Fetch models", but editable so the
        # user can still type a custom id without first fetching the list.
        model_row = QtWidgets.QHBoxLayout()
        self._llm_model = QtWidgets.QComboBox()
        self._llm_model.setEditable(True)
        self._llm_model.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self._llm_model.setMinimumWidth(320)
        model_row.addWidget(self._llm_model, stretch=1)
        self._llm_fetch_models_btn = QtWidgets.QPushButton("Fetch models…")
        self._llm_fetch_models_btn.setToolTip(
            "Call GET {endpoint}/models with the configured API key "
            "and show the available models here."
        )
        self._llm_fetch_models_btn.clicked.connect(self._on_fetch_models)
        model_row.addWidget(self._llm_fetch_models_btn)
        llm_layout.addRow("Model:", model_row)

        env_row = QtWidgets.QHBoxLayout()
        self._llm_api_key_env = QtWidgets.QLineEdit()
        self._llm_api_key_env.setPlaceholderText("OPENAI_API_KEY")
        # Editing the env-var name invalidates the model cache too — the
        # cached entry was fetched with the old key.
        self._llm_api_key_env.textChanged.connect(lambda _t: self._model_catalog.clear_cache())
        env_row.addWidget(self._llm_api_key_env)
        self._llm_env_helper_btn = QtWidgets.QPushButton("Set API key…")
        self._llm_env_helper_btn.clicked.connect(self._on_open_env_helper)
        env_row.addWidget(self._llm_env_helper_btn)
        llm_layout.addRow("Env var name:", env_row)

        # Status line for fetch errors. Hidden by default; shown after a
        # failed fetch with the error message.
        self._llm_model_status = QtWidgets.QLabel()
        self._llm_model_status.setStyleSheet("color: #b36400;")
        self._llm_model_status.setWordWrap(True)
        self._llm_model_status.setVisible(False)
        llm_layout.addRow("", self._llm_model_status)

        self._llm_style = QtWidgets.QComboBox()
        for label, value in _STYLE_OPTIONS:
            self._llm_style.addItem(label, value)
        llm_layout.addRow("Style:", self._llm_style)

        self._llm_preserve_code = QtWidgets.QCheckBox(
            "Preserve code identifiers / URLs / file paths"
        )
        self._llm_preserve_code.setChecked(True)
        llm_layout.addRow("", self._llm_preserve_code)

        prompt_row = QtWidgets.QHBoxLayout()
        self._llm_prompt_path = QtWidgets.QLineEdit()
        self._llm_prompt_path.setPlaceholderText("(optional) ~/.agentvoca/prompt.txt")
        prompt_row.addWidget(self._llm_prompt_path)
        prompt_btn = QtWidgets.QPushButton("Browse…")
        prompt_btn.clicked.connect(self._on_browse_prompt)
        prompt_row.addWidget(prompt_btn)
        llm_layout.addRow("Custom prompt file:", prompt_row)

        self._llm_warm_up = QtWidgets.QCheckBox("Warm up connection at startup")
        self._llm_warm_up.setChecked(True)
        llm_layout.addRow("", self._llm_warm_up)

        self._stack.addWidget(llm_page)

        layout.addWidget(self._stack)
        layout.addStretch()

        self._off_btn.toggled.connect(lambda c: c and self._stack.setCurrentIndex(0))
        self._rules_btn.toggled.connect(lambda c: c and self._stack.setCurrentIndex(1))
        self._llm_btn.toggled.connect(lambda c: c and self._stack.setCurrentIndex(2))

    # ── Slots ──────────────────────────────────────────────────────────

    def _on_open_env_helper(self) -> None:
        name = self._llm_api_key_env.text().strip() or "OPENAI_API_KEY"
        dialog = EnvHelperDialog(name, self)
        # Keep the env-var field in sync with whatever name the user settled
        # on inside the dialog. Without this the controller would still see
        # the old name even after the user picked a new one.
        dialog.env_var_changed.connect(self._llm_api_key_env.setText)
        dialog.exec()

    def _on_browse_prompt(self) -> None:
        start = str(self._llm_prompt_path.text() or "")
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Pick a prompt file", start, "Text files (*.txt)"
        )
        if path:
            self._llm_prompt_path.setText(path)

    def _on_fetch_models(self) -> None:
        """Kick off an async model-list fetch for the current endpoint + key."""
        if self._fetch_in_flight:
            return
        endpoint = self._llm_endpoint.text().strip() or "https://api.openai.com/v1"
        env_var = self._llm_api_key_env.text().strip()
        api_key = os.environ.get(env_var) if env_var else None
        if env_var and not api_key:
            self._show_model_status(
                f"Env var '{env_var}' is not set. "
                "Click 'Set API key…' or set it in your shell, then retry.",
                error=True,
            )
            return

        self._fetch_in_flight = True
        self._llm_fetch_models_btn.setEnabled(False)
        self._llm_fetch_models_btn.setText("Fetching…")
        self._show_model_status(f"Fetching models from {endpoint}…", error=False)

        # The catalog callback fires on a worker thread. Emit a signal
        # instead of touching widgets directly — Qt queues the emission
        # onto this page's (GUI) thread so ``_apply_fetch_result`` runs
        # safely there.
        def _on_done(entries, error) -> None:
            self._fetch_result.emit(entries, error)

        self._model_catalog.fetch_async(endpoint, api_key, _on_done)

    def _apply_fetch_result(self, entries, error) -> None:
        self._fetch_in_flight = False
        self._llm_fetch_models_btn.setEnabled(True)
        self._llm_fetch_models_btn.setText("Fetch models…")
        if error is not None:
            self._show_model_status(error, error=True)
            return
        # Preserve the user's currently-selected/typed id so we don't blow it
        # away when repopulating the dropdown. ``resolve_editable_combo_id``
        # resolves a selected item's *label* back to its real id (or returns
        # the typed text verbatim for a hand-typed custom id).
        current_id = resolve_editable_combo_id(self._llm_model)
        self._llm_model.blockSignals(True)
        try:
            self._llm_model.clear()
            for entry in entries or []:
                self._llm_model.addItem(entry.label, entry.id)
            if current_id:
                idx = self._llm_model.findData(current_id)
                if idx >= 0:
                    self._llm_model.setCurrentIndex(idx)
                else:
                    # Not in the fetched list — keep the hand-typed id.
                    self._llm_model.addItem(current_id, current_id)
                    self._llm_model.setCurrentIndex(self._llm_model.count() - 1)
        finally:
            self._llm_model.blockSignals(False)
        count = len(entries or [])
        self._show_model_status(
            f"Loaded {count} model{'s' if count != 1 else ''}. Pick one above.",
            error=False,
        )

    def _show_model_status(self, message: str, *, error: bool) -> None:
        self._llm_model_status.setText(message)
        self._llm_model_status.setStyleSheet("color: #b36400;" if error else "color: #1f8a3a;")
        self._llm_model_status.setVisible(True)

    # ── Load / save ────────────────────────────────────────────────────

    def load_from_controller(self) -> None:
        c = self.controller.draft.cleanup
        provider = c.provider or "rules"
        if provider == "none":
            self._off_btn.setChecked(True)
            self._stack.setCurrentIndex(0)
        elif provider == "openai_compatible":
            self._llm_btn.setChecked(True)
            self._stack.setCurrentIndex(2)
        else:
            self._rules_btn.setChecked(True)
            self._stack.setCurrentIndex(1)

        self._set_combo(self._rules_style, c.style)
        self._rules_warm_up.setChecked(c.warm_up)

        self._llm_endpoint.setText(c.endpoint or "")
        # Populate the model combobox with the saved value (and only the
        # saved value, so the dropdown is not empty on first paint). A real
        # fetch is only triggered when the user clicks "Fetch models…".
        self._llm_model.blockSignals(True)
        try:
            self._llm_model.clear()
            if c.model:
                self._llm_model.addItem(c.model, c.model)
                self._llm_model.setCurrentIndex(0)
        finally:
            self._llm_model.blockSignals(False)
        self._llm_api_key_env.setText(c.api_key_env or "")
        self._set_combo(self._llm_style, c.style)
        self._llm_preserve_code.setChecked(c.preserve_code)
        self._llm_prompt_path.setText(c.custom_prompt_path or "")
        self._llm_warm_up.setChecked(c.warm_up)

    def save_to_controller(self) -> None:
        if self._off_btn.isChecked():
            cleanup = {"provider": "none"}
        elif self._rules_btn.isChecked():
            cleanup = {
                "provider": "rules",
                "style": self._rules_style.currentData() or "standard",
                "warm_up": self._rules_warm_up.isChecked(),
            }
        else:
            # Combobox is editable: ``resolve_editable_combo_id`` picks the
            # right id (see its docstring).
            model_value = resolve_editable_combo_id(self._llm_model)
            cleanup = {
                "provider": "openai_compatible",
                "model": (model_value or "").strip() or None,
                "endpoint": self._llm_endpoint.text().strip() or None,
                "api_key_env": self._llm_api_key_env.text().strip() or None,
                "style": self._llm_style.currentData() or "standard",
                "preserve_code": self._llm_preserve_code.isChecked(),
                "custom_prompt_path": self._llm_prompt_path.text().strip() or None,
                "warm_up": self._llm_warm_up.isChecked(),
            }
        self.controller.update_section(cleanup=cleanup)

    @staticmethod
    def _set_combo(combo: QtWidgets.QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
