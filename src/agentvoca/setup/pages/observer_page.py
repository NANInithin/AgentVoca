"""Observer settings page (v0.4.0, Track 3, OBS-27).

Exposes every ``observer.*`` config block to the user. The two
Observer hotkeys (``toggle_observer`` and ``pause_observer``) live
on the Hotkeys page instead \u2014 they are global UI controls and
duplicating the dropdown here would risk the two views going out
of sync.

Two things this page does that the other pages do not:

1. A prominent privacy notice at the top, always visible, not in a
   collapsed section.
2. A cloud warning that appears the moment ``ocr.provider`` or
   ``compile.provider`` is set to ``openai_compatible``.
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from agentvoca.config.schema import ObserverConfig
from agentvoca.setup.pages.base import ConfigPage

# Default exclusion lists, kept in sync with the schema's defaults
# (the schema is the source of truth \u2014 these are mirrored here so
# the placeholder text is informative when the user has not edited).
_DEFAULT_EXCLUDE_APPS_HINT = (
    "1Password.exe\nKeePass.exe\nKeePassXC.exe\nBitwarden.exe\nSignal.exe"
    "\nDashlane.exe\nLastPass.exe"
)
_DEFAULT_EXCLUDE_TITLES_HINT = "*InPrivate*\n*Incognito*\n*Private Browsing*\n*Password*"

_PROVIDER_OPTIONS = [
    ("Rules (offline, no API key)", "rules"),
    ("OpenAI-compatible (LLM)", "openai_compatible"),
]

_OCR_PROVIDER_OPTIONS = [
    ("RapidOCR (offline, no API key)", "rapidocr"),
    ("OpenAI-compatible (VLM)", "openai_compatible"),
    ("None (no OCR)", "none"),
]

_SELECTION_METHOD_OPTIONS = [
    ("Windows UI Automation (UIA)", "uia"),
    ("OCR rect fallback", "ocr_rect"),
    ("Disabled", "none"),
]

_FORMAT_OPTIONS = [
    ("Markdown", "markdown"),
    ("JSON sidecar", "json"),
]


class ObserverPage(ConfigPage):
    title = "Observer"
    subtitle = "Configure session recording (microphone + screen + selection)."

    def _build(self) -> None:
        super()._build()
        layout = self._body_layout

        # ── Privacy notice (always visible) ─────────────────────────
        notice = QtWidgets.QLabel(
            "Observer records your microphone and screenshots of the active "
            "window for the whole session. Data is stored <b>unencrypted</b> "
            "in <code>~/.agentvoca/observer</code>. Sessions older than N "
            "days are deleted automatically."
        )
        notice.setWordWrap(True)
        notice.setStyleSheet(
            "QLabel { background: #fff3cd; border: 1px solid #ffe69c; "
            "padding: 8px; border-radius: 4px; }"
        )
        notice.setTextFormat(QtCore.Qt.TextFormat.RichText)
        layout.addWidget(notice)

        # ── Master switch ──────────────────────────────────────────
        self._enabled = QtWidgets.QCheckBox("Enable Observer mode")
        layout.addWidget(self._enabled)

        # Cloud warning, shown only when a remote provider is selected.
        self._cloud_warning = QtWidgets.QLabel(
            "\u26a0\ufe0f <b>Cloud mode:</b> screenshots and transcripts will "
            "be sent to the configured endpoint."
        )
        self._cloud_warning.setWordWrap(True)
        self._cloud_warning.setTextFormat(QtCore.Qt.TextFormat.RichText)
        self._cloud_warning.setStyleSheet(
            "QLabel { background: #f8d7da; border: 1px solid #f5c2c7; "
            "padding: 8px; border-radius: 4px; }"
        )
        self._cloud_warning.setVisible(False)
        layout.addWidget(self._cloud_warning)

        # ── Storage ────────────────────────────────────────────────
        storage_box = QtWidgets.QGroupBox("Storage")
        storage_form = QtWidgets.QFormLayout(storage_box)
        self._retention_days = QtWidgets.QSpinBox()
        self._retention_days.setRange(0, 365)
        self._retention_days.setSuffix(" days")
        self._retention_days.setToolTip("0 disables auto-purge.")
        storage_form.addRow("Retention:", self._retention_days)
        self._max_session_mb = QtWidgets.QSpinBox()
        self._max_session_mb.setRange(1, 10_000)
        self._max_session_mb.setSuffix(" MB")
        storage_form.addRow("Max session size:", self._max_session_mb)
        layout.addWidget(storage_box)

        # ── Triggers ───────────────────────────────────────────────
        triggers_box = QtWidgets.QGroupBox("Keyframe triggers")
        triggers_layout = QtWidgets.QVBoxLayout(triggers_box)
        self._trig_window = QtWidgets.QCheckBox("Capture when foreground window changes")
        self._trig_scroll = QtWidgets.QCheckBox("Capture after scrolling settles (set delay below)")
        self._trig_click = QtWidgets.QCheckBox("Capture on click / selection")
        self._trig_speech = QtWidgets.QCheckBox("Capture on speech onset (D9)")
        triggers_layout.addWidget(self._trig_window)
        triggers_layout.addWidget(self._trig_scroll)
        triggers_layout.addWidget(self._trig_click)
        triggers_layout.addWidget(self._trig_speech)
        triggers_form = QtWidgets.QFormLayout()
        self._scroll_settle_ms = QtWidgets.QSpinBox()
        self._scroll_settle_ms.setRange(100, 5_000)
        self._scroll_settle_ms.setSuffix(" ms")
        self._scroll_settle_ms.setSingleStep(50)
        triggers_form.addRow("Scroll settle delay:", self._scroll_settle_ms)
        self._min_interval_ms = QtWidgets.QSpinBox()
        self._min_interval_ms.setRange(500, 60_000)
        self._min_interval_ms.setSuffix(" ms")
        self._min_interval_ms.setSingleStep(500)
        triggers_form.addRow("Min interval between keyframes:", self._min_interval_ms)
        self._max_keyframes_per_min = QtWidgets.QSpinBox()
        self._max_keyframes_per_min.setRange(1, 60)
        self._max_keyframes_per_min.setSuffix(" / min")
        triggers_form.addRow("Max keyframes per minute:", self._max_keyframes_per_min)
        triggers_layout.addLayout(triggers_form)
        layout.addWidget(triggers_box)

        # ── OCR ─────────────────────────────────────────────────────
        ocr_box = QtWidgets.QGroupBox("OCR")
        ocr_form = QtWidgets.QFormLayout(ocr_box)
        self._ocr_provider = QtWidgets.QComboBox()
        for label, value in _OCR_PROVIDER_OPTIONS:
            self._ocr_provider.addItem(label, value)
        self._ocr_provider.currentIndexChanged.connect(lambda _i: self._update_cloud_warning())
        ocr_form.addRow("Provider:", self._ocr_provider)
        self._ocr_endpoint = QtWidgets.QLineEdit()
        self._ocr_endpoint.setPlaceholderText("https://api.openai.com/v1")
        ocr_form.addRow("Endpoint:", self._ocr_endpoint)
        self._ocr_model = QtWidgets.QLineEdit()
        self._ocr_model.setPlaceholderText("(only for cloud providers)")
        ocr_form.addRow("Model:", self._ocr_model)
        self._ocr_api_key_env = QtWidgets.QLineEdit()
        self._ocr_api_key_env.setPlaceholderText("OPENAI_API_KEY")
        ocr_form.addRow("API key env var:", self._ocr_api_key_env)
        self._ocr_max_queue = QtWidgets.QSpinBox()
        self._ocr_max_queue.setRange(4, 256)
        ocr_form.addRow("OCR queue size:", self._ocr_max_queue)
        layout.addWidget(ocr_box)

        # ── Selection ──────────────────────────────────────────────
        sel_box = QtWidgets.QGroupBox("Selection capture")
        sel_form = QtWidgets.QFormLayout(sel_box)
        self._selection_method = QtWidgets.QComboBox()
        for label, value in _SELECTION_METHOD_OPTIONS:
            self._selection_method.addItem(label, value)
        sel_form.addRow("Method:", self._selection_method)
        self._selection_max_chars = QtWidgets.QSpinBox()
        self._selection_max_chars.setRange(100, 100_000)
        self._selection_max_chars.setSingleStep(500)
        sel_form.addRow("Max chars per selection:", self._selection_max_chars)
        layout.addWidget(sel_box)

        # ── Compile ────────────────────────────────────────────────
        comp_box = QtWidgets.QGroupBox("Compilation")
        comp_form = QtWidgets.QFormLayout(comp_box)
        self._compile_provider = QtWidgets.QComboBox()
        for label, value in _PROVIDER_OPTIONS:
            self._compile_provider.addItem(label, value)
        self._compile_provider.currentIndexChanged.connect(lambda _i: self._update_cloud_warning())
        comp_form.addRow("Provider:", self._compile_provider)
        self._compile_endpoint = QtWidgets.QLineEdit()
        self._compile_endpoint.setPlaceholderText("https://api.openai.com/v1")
        comp_form.addRow("Endpoint:", self._compile_endpoint)
        self._compile_model = QtWidgets.QLineEdit()
        comp_form.addRow("Model:", self._compile_model)
        self._compile_api_key_env = QtWidgets.QLineEdit()
        self._compile_api_key_env.setPlaceholderText("OPENAI_API_KEY")
        comp_form.addRow("API key env var:", self._compile_api_key_env)
        # Output formats
        self._format_checks: dict[str, QtWidgets.QCheckBox] = {}
        fmt_row = QtWidgets.QHBoxLayout()
        for label, value in _FORMAT_OPTIONS:
            cb = QtWidgets.QCheckBox(label)
            self._format_checks[value] = cb
            fmt_row.addWidget(cb)
        fmt_widget = QtWidgets.QWidget()
        fmt_widget.setLayout(fmt_row)
        comp_form.addRow("Output formats:", fmt_widget)
        layout.addWidget(comp_box)

        # ── Privacy / exclusions ───────────────────────────────────
        priv_box = QtWidgets.QGroupBox("Privacy \u2014 exclusion lists")
        priv_layout = QtWidgets.QFormLayout(priv_box)
        self._exclude_apps = QtWidgets.QPlainTextEdit()
        self._exclude_apps.setPlaceholderText(_DEFAULT_EXCLUDE_APPS_HINT)
        self._exclude_apps.setMaximumHeight(120)
        priv_layout.addRow("Excluded apps (one per line):", self._exclude_apps)
        self._exclude_titles = QtWidgets.QPlainTextEdit()
        self._exclude_titles.setPlaceholderText(_DEFAULT_EXCLUDE_TITLES_HINT)
        self._exclude_titles.setMaximumHeight(120)
        priv_layout.addRow("Excluded title patterns (one per line):", self._exclude_titles)
        layout.addWidget(priv_box)

        # ── Hotkeys cross-reference ────────────────────────────────
        hk_label = QtWidgets.QLabel(
            "The two Observer hotkeys "
            "(<b>Toggle Observer session</b>, <b>Pause / resume Observer</b>) "
            "are configured in the Hotkeys tab."
        )
        hk_label.setWordWrap(True)
        hk_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
        hk_label.setStyleSheet("color: #666;")
        layout.addWidget(hk_label)

        layout.addStretch()

    # ── Cloud-warning helpers ────────────────────────────────────────

    def _update_cloud_warning(self) -> None:
        ocr_remote = self._ocr_provider.currentData() == "openai_compatible"
        comp_remote = self._compile_provider.currentData() == "openai_compatible"
        self._cloud_warning.setVisible(ocr_remote or comp_remote)

    # ── Load / save ──────────────────────────────────────────────────

    def _set_combo(self, combo: QtWidgets.QComboBox, value: str) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _text_to_list(self, text: str) -> list[str]:
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _list_to_text(self, items: list[str]) -> str:
        return "\n".join(items)

    def load_from_controller(self) -> None:
        c: ObserverConfig = self.controller.draft.observer
        self._enabled.setChecked(c.enabled)
        self._retention_days.setValue(c.storage.retention_days)
        self._max_session_mb.setValue(c.storage.max_session_mb)
        self._trig_window.setChecked(c.triggers.window_change)
        self._trig_scroll.setChecked(c.triggers.scroll_settle)
        self._trig_click.setChecked(c.triggers.click_selection)
        self._trig_speech.setChecked(c.triggers.speech_onset)
        self._scroll_settle_ms.setValue(c.triggers.scroll_settle_ms)
        self._min_interval_ms.setValue(c.triggers.min_interval_ms)
        self._max_keyframes_per_min.setValue(c.triggers.max_keyframes_per_min)
        self._set_combo(self._ocr_provider, c.ocr.provider)
        self._ocr_endpoint.setText(c.ocr.endpoint or "")
        self._ocr_model.setText(c.ocr.model or "")
        self._ocr_api_key_env.setText(c.ocr.api_key_env or "")
        self._ocr_max_queue.setValue(c.ocr.max_queue)
        self._set_combo(self._selection_method, c.selection.method)
        self._selection_max_chars.setValue(c.selection.max_chars)
        self._set_combo(self._compile_provider, c.compile.provider)
        self._compile_endpoint.setText(c.compile.endpoint or "")
        self._compile_model.setText(c.compile.model or "")
        self._compile_api_key_env.setText(c.compile.api_key_env or "")
        # Output formats: list -> checks
        for value, cb in self._format_checks.items():
            cb.setChecked(value in c.compile.formats)
        self._exclude_apps.setPlainText(self._list_to_text(list(c.privacy.exclude_apps)))
        self._exclude_titles.setPlainText(
            self._list_to_text(list(c.privacy.exclude_title_patterns))
        )
        self._update_cloud_warning()

    def save_to_controller(self) -> None:
        formats = [v for v, cb in self._format_checks.items() if cb.isChecked()]
        if not formats:
            formats = ["markdown"]  # schema requires non-empty
        self.controller.update_section(
            observer={
                "enabled": self._enabled.isChecked(),
                "storage": {
                    "retention_days": self._retention_days.value(),
                    "max_session_mb": self._max_session_mb.value(),
                },
                "triggers": {
                    "window_change": self._trig_window.isChecked(),
                    "scroll_settle": self._trig_scroll.isChecked(),
                    "click_selection": self._trig_click.isChecked(),
                    "speech_onset": self._trig_speech.isChecked(),
                    "scroll_settle_ms": self._scroll_settle_ms.value(),
                    "min_interval_ms": self._min_interval_ms.value(),
                    "max_keyframes_per_min": self._max_keyframes_per_min.value(),
                },
                "ocr": {
                    "provider": self._ocr_provider.currentData() or "rapidocr",
                    "endpoint": self._ocr_endpoint.text().strip() or None,
                    "model": self._ocr_model.text().strip() or None,
                    "api_key_env": self._ocr_api_key_env.text().strip() or None,
                    "max_queue": self._ocr_max_queue.value(),
                },
                "selection": {
                    "method": self._selection_method.currentData() or "uia",
                    "max_chars": self._selection_max_chars.value(),
                },
                "compile": {
                    "provider": self._compile_provider.currentData() or "rules",
                    "endpoint": self._compile_endpoint.text().strip() or None,
                    "model": self._compile_model.text().strip() or None,
                    "api_key_env": self._compile_api_key_env.text().strip() or None,
                    "formats": formats,
                },
                "privacy": {
                    "exclude_apps": self._text_to_list(self._exclude_apps.toPlainText()),
                    "exclude_title_patterns": self._text_to_list(
                        self._exclude_titles.toPlainText()
                    ),
                },
            }
        )
