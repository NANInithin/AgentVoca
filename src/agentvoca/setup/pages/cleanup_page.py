"""Cleanup page — provider, style, endpoint, API key."""

from __future__ import annotations

from PySide6 import QtWidgets

from agentvoca.setup.pages.base import ConfigPage
from agentvoca.setup.pages.env_helper_dialog import EnvHelperDialog

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
        llm_layout.addRow("Endpoint:", self._llm_endpoint)
        self._llm_model = QtWidgets.QLineEdit()
        self._llm_model.setPlaceholderText("gpt-4o-mini")
        llm_layout.addRow("Model:", self._llm_model)

        env_row = QtWidgets.QHBoxLayout()
        self._llm_api_key_env = QtWidgets.QLineEdit()
        self._llm_api_key_env.setPlaceholderText("OPENAI_API_KEY")
        env_row.addWidget(self._llm_api_key_env)
        self._llm_env_helper_btn = QtWidgets.QPushButton("Set API key…")
        self._llm_env_helper_btn.clicked.connect(self._on_open_env_helper)
        env_row.addWidget(self._llm_env_helper_btn)
        llm_layout.addRow("Env var name:", env_row)

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
        EnvHelperDialog(name, self).exec()

    def _on_browse_prompt(self) -> None:
        start = str(self._llm_prompt_path.text() or "")
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Pick a prompt file", start, "Text files (*.txt)"
        )
        if path:
            self._llm_prompt_path.setText(path)

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
        self._llm_model.setText(c.model or "")
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
            cleanup = {
                "provider": "openai_compatible",
                "model": self._llm_model.text().strip() or None,
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
