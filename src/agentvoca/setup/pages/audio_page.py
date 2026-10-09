"""Audio page — input device, VAD, timeouts."""

from __future__ import annotations

from PySide6 import QtWidgets

from agentvoca.setup.controllers.device_probe import DeviceProbe
from agentvoca.setup.pages.base import ConfigPage


class AudioPage(ConfigPage):
    title = "Microphone"
    subtitle = "Pick an input device and tune silence detection."

    def _build(self) -> None:
        super()._build()
        layout = self._body_layout

        form = QtWidgets.QFormLayout()
        form.setSpacing(10)

        # Device dropdown
        device_row = QtWidgets.QHBoxLayout()
        self._device_combo = QtWidgets.QComboBox()
        self._device_combo.setMinimumWidth(320)
        device_row.addWidget(self._device_combo, stretch=1)
        self._refresh_btn = QtWidgets.QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._on_refresh_devices)
        device_row.addWidget(self._refresh_btn)
        form.addRow("Input device:", device_row)

        self._sample_rate = QtWidgets.QSpinBox()
        self._sample_rate.setRange(16000, 16000)
        self._sample_rate.setSuffix(" Hz")
        self._sample_rate.setToolTip("VAD and ASR require 16 kHz audio.")
        form.addRow("Sample rate:", self._sample_rate)

        self._channels = QtWidgets.QSpinBox()
        self._channels.setRange(1, 1)
        form.addRow("Channels:", self._channels)

        self._vad = QtWidgets.QCheckBox("Use voice-activity detection (VAD) to auto-stop")
        form.addRow("", self._vad)

        self._silence_timeout = QtWidgets.QSpinBox()
        self._silence_timeout.setRange(100, 5000)
        self._silence_timeout.setSingleStep(50)
        self._silence_timeout.setSuffix(" ms")
        form.addRow("Silence before auto-stop:", self._silence_timeout)

        self._max_duration = QtWidgets.QSpinBox()
        self._max_duration.setRange(5, 1800)
        self._max_duration.setSingleStep(30)
        self._max_duration.setSuffix(" s")
        form.addRow("Max recording duration:", self._max_duration)

        layout.addLayout(form)
        layout.addStretch()

        self._probe = DeviceProbe()
        self._devices_loaded = False

    def _on_refresh_devices(self) -> None:
        entries = self._probe.refresh()
        self._devices_loaded = True
        self._device_combo.clear()
        for entry in entries:
            self._device_combo.addItem(entry.label, entry.name)

    def load_from_controller(self) -> None:
        if not self._devices_loaded:
            self._on_refresh_devices()
        c = self.controller.draft
        # Pick current device in the combo if it matches an entry; otherwise
        # surface it as a custom row.
        target_name = c.audio.input_device or "default"
        idx = self._device_combo.findData(target_name)
        if idx < 0:
            self._device_combo.insertItem(0, target_name, target_name)
            self._device_combo.setCurrentIndex(0)
        else:
            self._device_combo.setCurrentIndex(idx)

        self._sample_rate.setValue(c.audio.sample_rate)
        self._channels.setValue(c.audio.channels)
        self._vad.setChecked(c.audio.vad_enabled)
        self._silence_timeout.setValue(c.audio.silence_timeout_ms)
        self._max_duration.setValue(c.audio.max_recording_duration_s)

    def save_to_controller(self) -> None:
        self.controller.update_section(
            audio={
                "input_device": self._device_combo.currentData() or "default",
                "sample_rate": self._sample_rate.value(),
                "channels": self._channels.value(),
                "vad_enabled": self._vad.isChecked(),
                "silence_timeout_ms": self._silence_timeout.value(),
                "max_recording_duration_s": self._max_duration.value(),
            }
        )
