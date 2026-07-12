"""ASR (speech-to-text) page — provider, model, endpoint, API key."""

from __future__ import annotations

import logging
import os

from PySide6 import QtCore, QtWidgets

from agentvoca.setup.controllers.model_catalog import ModelCatalog
from agentvoca.setup.pages._combobox_utils import resolve_editable_combo_id
from agentvoca.setup.pages.base import ConfigPage
from agentvoca.setup.pages.env_helper_dialog import EnvHelperDialog

logger = logging.getLogger(__name__)

# Hosts that expose an OpenAI-compatible *chat* API but have no speech-to-text
# ``/audio/transcriptions`` route. Pointing ASR at them always fails. They are
# perfectly fine for the Cleanup step, which is a chat/LLM call.
#
# NOTE: OpenRouter is intentionally NOT in this list. It added a dedicated
# ``/api/v1/audio/transcriptions`` endpoint that accepts OpenAI-style multipart
# uploads (models like ``openai/whisper-1`` / ``openai/whisper-large-v3``), so
# it works for speech-to-text just like OpenAI or Groq.
_HOSTS_WITHOUT_TRANSCRIPTION = {
    "anthropic.com": "Anthropic",
}


def _asr_endpoint_warning(endpoint: str) -> str | None:
    """Return a warning if ``endpoint`` is a known chat-only (no-STT) host."""
    ep = (endpoint or "").lower()
    for host, name in _HOSTS_WITHOUT_TRANSCRIPTION.items():
        if host in ep:
            return (
                f"{name} has no speech-to-text endpoint, so transcription will "
                f"fail here. Use OpenAI (whisper-1), Groq (whisper-large-v3), or "
                f"a local Whisper server for speech-to-text. You can still use "
                f"{name} for the Cleanup step."
            )
    return None


_LOCAL_MODELS = [
    ("Tiny (fastest, lowest accuracy)", "tiny"),
    ("Base (~145 MB, recommended)", "base"),
    ("Small", "small"),
    ("Medium", "medium"),
    ("Large-v3 (most accurate, ~3 GB)", "large-v3"),
]


class AsrPage(ConfigPage):
    title = "Speech-to-text"
    subtitle = (
        "Pick how agentvoca turns your voice into text. "
        "Local is private and offline; cloud is more accurate."
    )

    # Emitted from the model-catalog worker thread once a fetch completes.
    # Qt automatically queues cross-thread signal emissions onto the
    # receiver's (GUI) thread, which is what actually gets us back onto the
    # main loop safely — a bare QTimer.singleShot() called from a thread
    # with no Qt event loop of its own never fires.
    _fetch_result = QtCore.Signal(object, object)

    def __init__(self, controller=None) -> None:
        # Catalog used to populate the cloud-model dropdown. Held on the page
        # so the cache survives across navigation away and back.
        self._model_catalog = ModelCatalog()
        self._fetch_in_flight: bool = False
        super().__init__(controller)
        self._fetch_result.connect(self._apply_fetch_result)

    def _build(self) -> None:
        super()._build()
        layout = self._body_layout

        # Provider choice — two cards side by side
        provider_row = QtWidgets.QHBoxLayout()
        self._local_btn = QtWidgets.QRadioButton("Local (faster-whisper, offline)")
        self._cloud_btn = QtWidgets.QRadioButton("Cloud (OpenAI-compatible API)")
        self._local_btn.setChecked(True)
        provider_row.addWidget(self._local_btn)
        provider_row.addWidget(self._cloud_btn)
        provider_row.addStretch()
        layout.addLayout(provider_row)

        # Stacked area for provider-specific controls
        self._stack = QtWidgets.QStackedWidget()

        # Local page
        local_page = QtWidgets.QWidget()
        local_layout = QtWidgets.QFormLayout(local_page)
        self._local_model = QtWidgets.QComboBox()
        for label, value in _LOCAL_MODELS:
            self._local_model.addItem(label, value)
        local_layout.addRow("Model:", self._local_model)

        self._warm_up = QtWidgets.QCheckBox("Preload model at startup (recommended)")
        self._warm_up.setChecked(True)
        local_layout.addRow("", self._warm_up)

        streaming_box = QtWidgets.QGroupBox("Streaming (v2 — show live partials)")
        streaming_layout = QtWidgets.QFormLayout(streaming_box)
        self._streaming = QtWidgets.QCheckBox("Enable streaming partial transcripts")
        streaming_layout.addRow("", self._streaming)
        self._streaming_model = QtWidgets.QComboBox()
        for label, value in _LOCAL_MODELS:
            self._streaming_model.addItem(label, value)
        streaming_layout.addRow("Streaming model:", self._streaming_model)
        self._streaming_chunk = QtWidgets.QSpinBox()
        self._streaming_chunk.setRange(100, 2000)
        self._streaming_chunk.setSingleStep(50)
        self._streaming_chunk.setSuffix(" ms")
        streaming_layout.addRow("Chunk interval:", self._streaming_chunk)
        self._streaming_window = QtWidgets.QSpinBox()
        self._streaming_window.setRange(0, 60)
        self._streaming_window.setSuffix(" s")
        streaming_layout.addRow("Window (0 = cumulative):", self._streaming_window)
        local_layout.addRow(streaming_box)

        self._stack.addWidget(local_page)

        # Cloud page
        cloud_page = QtWidgets.QWidget()
        cloud_layout = QtWidgets.QFormLayout(cloud_page)

        self._endpoint = QtWidgets.QLineEdit()
        self._endpoint.setPlaceholderText("https://api.openai.com/v1")
        # Editing the endpoint invalidates any cached model list so the next
        # "Fetch models" call hits the new server, and re-checks whether the
        # host can actually do speech-to-text.
        self._endpoint.textChanged.connect(lambda _t: self._model_catalog.clear_cache())
        self._endpoint.textChanged.connect(self._update_endpoint_warning)
        cloud_layout.addRow("Endpoint:", self._endpoint)

        # Warning shown when the endpoint is a known chat-only host (no STT).
        self._endpoint_warning = QtWidgets.QLabel()
        self._endpoint_warning.setStyleSheet("color: #b36400;")
        self._endpoint_warning.setWordWrap(True)
        self._endpoint_warning.setVisible(False)
        cloud_layout.addRow("", self._endpoint_warning)

        # Model — combobox populated by "Fetch models", but editable so the
        # user can still type a custom id without first fetching the list.
        model_row = QtWidgets.QHBoxLayout()
        self._api_model = QtWidgets.QComboBox()
        self._api_model.setEditable(True)
        self._api_model.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self._api_model.setMinimumWidth(320)
        # Use a sentinel user-data role so we can store the original id even
        # when the dropdown shows a friendlier label.
        self._api_model_role = QtCore.Qt.ItemDataRole.UserRole
        # Store the last successful fetch URL so the picker doesn't have to
        # be re-populated on every focus change.
        model_row.addWidget(self._api_model, stretch=1)
        self._fetch_models_btn = QtWidgets.QPushButton("Fetch models…")
        self._fetch_models_btn.setToolTip(
            "Call GET {endpoint}/models with the configured API key "
            "and show the available models here."
        )
        self._fetch_models_btn.clicked.connect(self._on_fetch_models)
        model_row.addWidget(self._fetch_models_btn)
        cloud_layout.addRow("Model:", model_row)

        env_row = QtWidgets.QHBoxLayout()
        self._api_key_env = QtWidgets.QLineEdit()
        self._api_key_env.setPlaceholderText("OPENAI_API_KEY")
        # Editing the env-var name invalidates the model cache too — the
        # cached entry was fetched with the old key.
        self._api_key_env.textChanged.connect(lambda _t: self._model_catalog.clear_cache())
        env_row.addWidget(self._api_key_env)
        self._env_helper_btn = QtWidgets.QPushButton("Set API key…")
        self._env_helper_btn.clicked.connect(self._on_open_env_helper)
        env_row.addWidget(self._env_helper_btn)
        cloud_layout.addRow("Env var name:", env_row)

        # Status line for fetch errors. Hidden by default; shown after a
        # failed fetch with the error message.
        self._model_status = QtWidgets.QLabel()
        self._model_status.setStyleSheet("color: #b36400;")
        self._model_status.setWordWrap(True)
        self._model_status.setVisible(False)
        cloud_layout.addRow("", self._model_status)

        self._stack.addWidget(cloud_page)

        layout.addWidget(self._stack)

        # Shared extras
        self._language_hint = QtWidgets.QLineEdit()
        self._language_hint.setPlaceholderText("(optional) en, de, fr…")
        layout.addWidget(QtWidgets.QLabel("Language hint (optional, overrides app.language):"))
        layout.addWidget(self._language_hint)

        # Provider switch handler
        self._local_btn.toggled.connect(self._on_provider_toggled)

        layout.addStretch()

    # ── Slots ──────────────────────────────────────────────────────────

    def _on_provider_toggled(self, checked: bool) -> None:
        self._stack.setCurrentIndex(0 if checked else 1)

    def _update_endpoint_warning(self, _text: str = "") -> None:
        """Show/hide the 'this host can't do speech-to-text' warning."""
        warning = _asr_endpoint_warning(self._endpoint.text())
        if warning:
            self._endpoint_warning.setText(warning)
            self._endpoint_warning.setVisible(True)
        else:
            self._endpoint_warning.setVisible(False)

    def _on_open_env_helper(self) -> None:
        name = self._api_key_env.text().strip() or "OPENAI_API_KEY"
        dialog = EnvHelperDialog(name, self)
        # Keep the env-var field in sync with whatever name the user settled
        # on inside the dialog. Without this the controller would still see
        # the old name even after the user picked a new one.
        dialog.env_var_changed.connect(self._api_key_env.setText)
        dialog.exec()

    def _on_fetch_models(self) -> None:
        """Kick off an async model-list fetch for the current endpoint + key."""
        if self._fetch_in_flight:
            return
        endpoint = self._endpoint.text().strip() or "https://api.openai.com/v1"
        env_var = self._api_key_env.text().strip()
        api_key = os.environ.get(env_var) if env_var else None
        if env_var and not api_key:
            self._show_model_status(
                f"Env var '{env_var}' is not set. "
                "Click 'Set API key…' or set it in your shell, then retry.",
                error=True,
            )
            return

        self._fetch_in_flight = True
        self._fetch_models_btn.setEnabled(False)
        self._fetch_models_btn.setText("Fetching…")
        self._show_model_status(f"Fetching models from {endpoint}…", error=False)

        # The catalog callback fires on a worker thread. Emit a signal
        # instead of touching widgets directly — Qt queues the emission
        # onto this page's (GUI) thread so ``_apply_fetch_result`` runs
        # safely there.
        def _on_done(entries, error) -> None:
            self._fetch_result.emit(entries, error)

        # This is the ASR (speech-to-text) picker, so ask OpenRouter for only
        # its transcription models — otherwise its ~300 chat models bury the
        # handful of Whisper models. Ignored by non-OpenRouter hosts.
        self._model_catalog.fetch_async(
            endpoint, api_key, _on_done, output_modality="transcription"
        )

    def _apply_fetch_result(self, entries, error) -> None:
        self._fetch_in_flight = False
        self._fetch_models_btn.setEnabled(True)
        self._fetch_models_btn.setText("Fetch models…")
        if error is not None:
            self._show_model_status(error, error=True)
            return
        # Preserve the user's currently-selected/typed id so we don't blow it
        # away when repopulating the dropdown. ``resolve_editable_combo_id``
        # resolves a selected item's *label* back to its real id (or returns
        # the typed text verbatim for a hand-typed custom id).
        current_id = resolve_editable_combo_id(self._api_model)
        self._api_model.blockSignals(True)
        try:
            self._api_model.clear()
            for entry in entries or []:
                self._api_model.addItem(entry.label, entry.id)
            if current_id:
                idx = self._api_model.findData(current_id)
                if idx >= 0:
                    self._api_model.setCurrentIndex(idx)
                else:
                    # Not in the fetched list — keep the hand-typed id.
                    self._api_model.addItem(current_id, current_id)
                    self._api_model.setCurrentIndex(self._api_model.count() - 1)
        finally:
            self._api_model.blockSignals(False)
        count = len(entries or [])
        self._show_model_status(
            f"Loaded {count} model{'s' if count != 1 else ''}. Pick one above.",
            error=False,
        )

    def _show_model_status(self, message: str, *, error: bool) -> None:
        self._model_status.setText(message)
        self._model_status.setStyleSheet("color: #b36400;" if error else "color: #1f8a3a;")
        self._model_status.setVisible(True)

    # ── Load / save ────────────────────────────────────────────────────

    def load_from_controller(self) -> None:
        c = self.controller.draft.asr
        is_cloud = c.provider == "openai_compatible"
        self._local_btn.setChecked(not is_cloud)
        self._cloud_btn.setChecked(is_cloud)
        self._stack.setCurrentIndex(1 if is_cloud else 0)

        # Local defaults
        self._set_combo(self._local_model, c.model or "base")
        self._warm_up.setChecked(c.warm_up)
        self._streaming.setChecked(c.streaming)
        self._set_combo(self._streaming_model, c.streaming_model or "tiny")
        self._streaming_chunk.setValue(c.streaming_chunk_ms)
        self._streaming_window.setValue(c.streaming_window_s)

        # Cloud defaults
        self._endpoint.setText(c.endpoint or "")
        # Populate the model combobox with the saved value (and only the
        # saved value, so the dropdown is not empty on first paint). A real
        # fetch is only triggered when the user clicks "Fetch models…".
        self._api_model.blockSignals(True)
        try:
            self._api_model.clear()
            if c.model:
                self._api_model.addItem(c.model, c.model)
                self._api_model.setCurrentIndex(0)
        finally:
            self._api_model.blockSignals(False)
        self._api_key_env.setText(c.api_key_env or "")

        self._language_hint.setText(c.language_hint or "")

        # Re-evaluate the no-STT warning for the freshly-loaded endpoint.
        self._update_endpoint_warning()

    def save_to_controller(self) -> None:
        is_cloud = self._cloud_btn.isChecked()
        if is_cloud:
            # The combobox is editable: the actual id lives in userData when
            # the user picked an entry from the dropdown, and in currentText
            # when they typed manually. ``resolve_editable_combo_id`` picks
            # the right one (see its docstring for why currentData() alone
            # is not enough).
            model_value = resolve_editable_combo_id(self._api_model)
            asr = {
                "provider": "openai_compatible",
                "model": (model_value or "").strip() or None,
                "endpoint": self._endpoint.text().strip() or None,
                "api_key_env": self._api_key_env.text().strip() or None,
                "language_hint": self._language_hint.text().strip() or None,
                "streaming": False,
                "streaming_model": None,
            }
        else:
            asr = {
                "provider": "faster_whisper",
                "model": self._local_model.currentData(),
                "warm_up": self._warm_up.isChecked(),
                "streaming": self._streaming.isChecked(),
                "streaming_model": self._streaming_model.currentData(),
                "streaming_chunk_ms": self._streaming_chunk.value(),
                "streaming_window_s": self._streaming_window.value(),
            }
        self.controller.update_section(asr=asr)

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _set_combo(combo: QtWidgets.QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
