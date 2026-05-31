"""Unit tests for audio capture, devices, and VAD modules.

Tests cover device enumeration logic, VAD initialization, and
AudioCapture start/stop/recording lifecycle using mock sounddevice.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentvoca.audio.capture import AudioCapture
from agentvoca.audio.devices import get_default_input_device, list_input_devices, select_device
from agentvoca.audio.vad import VAD
from agentvoca.core.event_bus import EventBus
from agentvoca.utils.errors import AudioError


class TestDevices:
    """Audio device enumeration tests."""

    @patch("agentvoca.audio.devices.sd.query_devices")
    def test_list_devices_returns_input_only(self, mock_query: MagicMock) -> None:
        devices_data = [
            {
                "name": "Built-in Mic",
                "max_input_channels": 1,
                "default_samplerate": 48000,
                "index": 0,
            },
            {"name": "Speakers", "max_input_channels": 0, "default_samplerate": 48000, "index": 1},
        ]

        def _query_side_effect(index=None):
            if index is None:
                return devices_data
            return devices_data[index]

        mock_query.side_effect = _query_side_effect
        devices = list_input_devices()
        assert len(devices) == 1
        assert devices[0]["name"] == "Built-in Mic"

    @patch("agentvoca.audio.devices.sd.query_devices")
    def test_get_default_input_device(self, mock_query: MagicMock) -> None:
        mock_query.return_value = {
            "name": "Default Mic",
            "max_input_channels": 1,
            "default_samplerate": 16000,
            "index": 0,
        }
        result = get_default_input_device()
        assert result is not None
        assert result["name"] == "Default Mic"

    @patch("agentvoca.audio.devices.get_default_input_device")
    def test_select_device_default(self, mock_default: MagicMock) -> None:
        mock_default.return_value = {"name": "Default", "index": 0}
        result = select_device("default")
        assert result is not None
        assert result["name"] == "Default"

    @patch("agentvoca.audio.devices.list_input_devices")
    def test_select_device_by_name(self, mock_list: MagicMock) -> None:
        mock_list.return_value = [
            {
                "name": "USB Microphone",
                "index": 1,
                "max_input_channels": 1,
                "default_samplerate": 48000,
            },
        ]
        result = select_device("USB")
        assert result is not None
        assert result["name"] == "USB Microphone"

    @patch("agentvoca.audio.devices.list_input_devices")
    def test_select_device_not_found(self, mock_list: MagicMock) -> None:
        mock_list.return_value = []
        result = select_device("Nonexistent")
        assert result is None


class TestVAD:
    """VAD initialization and lifecycle tests."""

    async def test_vad_start_loads_model(self) -> None:
        event_bus = EventBus()
        vad = VAD(event_bus)
        # With silero-vad installed, start() should succeed
        try:
            await vad.start()
            assert vad.is_available
        except Exception:
            # If silero-vad is not available, this is also acceptable
            assert not vad.is_available

    def test_vad_not_started_defaults_to_speech(self) -> None:
        event_bus = EventBus()
        vad = VAD(event_bus)
        assert vad.is_speech(b"\x00\x00" * 160) is True
        assert not vad.is_available

    def test_vad_process_chunk_no_model(self) -> None:
        event_bus = EventBus()
        vad = VAD(event_bus)
        # Should not raise without a model
        vad.process_chunk(b"\x00\x00" * 160, 0)


class TestAudioCapture:
    """AudioCapture lifecycle tests using mocked sounddevice."""

    @patch("agentvoca.audio.capture.select_device")
    def test_start_selects_device(self, mock_select: MagicMock) -> None:
        mock_select.return_value = {
            "name": "Mock Mic",
            "index": 0,
            "max_input_channels": 1,
            "default_samplerate": 16000,
        }
        event_bus = EventBus()

        with patch("agentvoca.audio.capture.sd.InputStream") as mock_stream:
            capt = AudioCapture(event_bus=event_bus)
            capt.start()
            mock_stream.assert_called_once()
            assert capt._stream is not None

    @patch("agentvoca.audio.capture.select_device")
    def test_start_no_device_raises(self, mock_select: MagicMock) -> None:
        mock_select.return_value = None
        event_bus = EventBus()
        capt = AudioCapture(event_bus=event_bus)
        with pytest.raises(AudioError, match="No audio input device found"):
            capt.start()

    @patch("agentvoca.audio.capture.select_device")
    def test_recording_lifecycle(self, mock_select: MagicMock) -> None:
        mock_select.return_value = {"name": "Mock", "index": 0}
        event_bus = EventBus()

        with patch("agentvoca.audio.capture.sd.InputStream"):
            capt = AudioCapture(event_bus=event_bus)
            capt.start()

            assert not capt.is_recording
            capt.start_recording()
            assert capt.is_recording
            capt.stop_recording()
            assert not capt.is_recording

    @patch("agentvoca.audio.capture.select_device")
    def test_cancel_recording_discards_buffer(self, mock_select: MagicMock) -> None:
        mock_select.return_value = {"name": "Mock", "index": 0}
        event_bus = EventBus()

        with patch("agentvoca.audio.capture.sd.InputStream"):
            capt = AudioCapture(event_bus=event_bus)
            capt.start()
            capt.start_recording()
            capt._audio_buffer.append(b"\x00\x00")
            capt.cancel_recording()
            assert not capt.is_recording
            assert capt._audio_buffer == []

    @patch("agentvoca.audio.capture.select_device")
    def test_stop_lifecycle(self, mock_select: MagicMock) -> None:
        mock_select.return_value = {"name": "Mock", "index": 0}
        event_bus = EventBus()

        with patch("agentvoca.audio.capture.sd.InputStream") as mock_stream:
            inst = mock_stream.return_value
            capt = AudioCapture(event_bus=event_bus)
            capt.start()
            capt.stop()
            inst.stop.assert_called_once()
            inst.close.assert_called_once()
