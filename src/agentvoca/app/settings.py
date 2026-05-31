"""Settings window for voice dictation — read-only display of loaded config.

Uses PySide6 to show the current configuration values in a simple
form layout. v1 is read-only — users edit the config file directly.
"""

from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from agentvoca.config.schema import FullConfig

try:
    from agentvoca.config.loader import load_config
except ImportError:
    # Fallback for testing: no-op load
    def load_config(path: str) -> FullConfig:  # type: ignore[misc]
        raise ValueError(f"Cannot load config in this context: {path}")


class SettingsWindow(QtWidgets.QWidget):
    """Read-only settings window displaying the loaded configuration.

    Args:
        config: The loaded application config to display.
    """

    def __init__(
        self,
        config: FullConfig,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config

        self.setWindowTitle("agentvoca Settings")
        self.setMinimumSize(500, 400)

        layout = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("agentvoca Configuration")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 8px;")
        subtitle = QtWidgets.QLabel("Settings are read-only in v1. Edit your config file directly.")
        subtitle.setStyleSheet("color: #888; padding: 0 8px 8px;")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        # Scrollable config display
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._build_form())
        layout.addWidget(scroll)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

        self.setLayout(layout)

    def _build_form(self) -> QtWidgets.QWidget:
        """Build a form widget displaying all config sections."""
        container = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(20)
        form.setVerticalSpacing(6)

        def add_section(title: str) -> None:
            label = QtWidgets.QLabel(title)
            label.setStyleSheet("font-weight: bold; font-size: 14px; padding-top: 12px;")
            form.addRow(label, QtWidgets.QLabel(""))

        def add_field(label: str, value: object) -> None:
            val_label = QtWidgets.QLabel(str(value))
            val_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(f"{label}:", val_label)

        # App section
        add_section("App")
        add_field("Profile", self._config.app.profile)
        add_field("Language", self._config.app.language)
        add_field("Mode", self._config.app.mode)
        add_field("Debug", str(self._config.app.debug))

        # Audio section
        add_section("Audio")
        add_field("Input Device", self._config.audio.input_device)
        add_field("Sample Rate", self._config.audio.sample_rate)
        add_field("Channels", self._config.audio.channels)
        add_field("VAD Enabled", str(self._config.audio.vad_enabled))
        add_field("Silence Timeout (ms)", self._config.audio.silence_timeout_ms)
        add_field("Max Recording (s)", self._config.audio.max_recording_duration_s)

        # ASR section
        add_section("ASR")
        add_field("Provider", self._config.asr.provider)
        add_field("Model", self._config.asr.model or "(default)")
        add_field("Endpoint", self._config.asr.endpoint or "(none)")
        add_field("API Key Env", self._config.asr.api_key_env or "(none)")
        add_field("Language Hint", self._config.asr.language_hint or "(auto)")

        # Cleanup section
        add_section("Cleanup")
        add_field("Provider", self._config.cleanup.provider)
        add_field("Model", self._config.cleanup.model or "(default)")
        add_field("Endpoint", self._config.cleanup.endpoint or "(none)")
        add_field("Style", self._config.cleanup.style)
        add_field("Preserve Code", str(self._config.cleanup.preserve_code))

        # Insertion section
        add_section("Insertion")
        add_field("Strategy", self._config.insertion.strategy)
        add_field("Clipboard Fallback", str(self._config.insertion.clipboard_fallback))
        add_field("Char Delay (ms)", self._config.insertion.delay_between_chars_ms)

        # Hotkeys section
        add_section("Hotkeys")
        add_field("Toggle Recording", self._config.hotkeys.toggle_recording)
        add_field("Open Settings", self._config.hotkeys.open_settings)
        add_field(
            "Insert Last",
            self._config.hotkeys.insert_last_transcript or "(not set)",
        )
        add_field("Cancel", self._config.hotkeys.cancel)

        container.setLayout(form)
        return container

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Override close to properly clean up."""
        event.accept()
