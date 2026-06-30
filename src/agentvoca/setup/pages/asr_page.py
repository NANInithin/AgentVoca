"""ASR (speech-to-text) page — provider, model, endpoint, API key."""

from __future__ import annotations

from PySide6 import QtWidgets

from agentvoca.setup.pages.base import ConfigPage
from agentvoca.setup.pages.env_helper_dialog import EnvHelperDialog

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
        cloud_layout.addRow("Endpoint:", self._endpoint)

        self._api_model = QtWidgets.QLineEdit()
        self._api_model.setPlaceholderText("whisper-1")
        cloud_layout.addRow("Model:", self._api_model)

        env_row = QtWidgets.QHBoxLayout()
        self._api_key_env = QtWidgets.QLineEdit()
        self._api_key_env.setPlaceholderText("OPENAI_API_KEY")
        env_row.addWidget(self._api_key_env)
        self._env_helper_btn = QtWidgets.QPushButton("Set API key…")
        self._env_helper_btn.clicked.connect(self._on_open_env_helper)
        env_row.addWidget(self._env_helper_btn)
        cloud_layout.addRow("Env var name:", env_row)

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

    def _on_open_env_helper(self) -> None:
        name = self._api_key_env.text().strip() or "OPENAI_API_KEY"
        dialog = EnvHelperDialog(name, self)
        dialog.exec()

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
        self._api_model.setText(c.model or "")
        self._api_key_env.setText(c.api_key_env or "")

        self._language_hint.setText(c.language_hint or "")

    def save_to_controller(self) -> None:
        is_cloud = self._cloud_btn.isChecked()
        if is_cloud:
            asr = {
                "provider": "openai_compatible",
                "model": self._api_model.text().strip() or None,
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
