"""Tests for the v0.4.0 ambient tap on AudioCapture._audio_callback (OBS-10).

The ambient tap is the seam that lets Observer hear the whole session —
not just dictations. The cost is a ``put_nowait`` on the audio callback
thread, so the budget is hard: p99 < 5 ms with the tap installed.

These tests are the budget gate. A regression here means dictation is
in danger, so the assertions are conservative.
"""

from __future__ import annotations

import queue
import time
from unittest.mock import MagicMock, patch

import numpy as np

from agentvoca.audio.capture import AudioCapture
from agentvoca.core.event_bus import EventBus

_MOCK_DEVICE = {"name": "Mock", "index": 0}


def _indata() -> np.ndarray:
    return np.zeros((1024, 1), dtype=np.float32)


class _CollectingSink:
    """AmbientSink that records every (audio_bytes, timestamp_ms) pair."""

    def __init__(self) -> None:
        self.feed_count = 0
        self.blocks: list[bytes] = []
        self.timestamps: list[int] = []

    def feed(self, audio_bytes: bytes, timestamp_ms: int) -> None:
        self.feed_count += 1
        self.blocks.append(audio_bytes)
        self.timestamps.append(timestamp_ms)


class _FullQueueSink:
    """A sink that drops every block on a full queue — exercises the
    drop-on-full path that protects the audio callback from blocking."""

    def __init__(self) -> None:
        self.q: queue.Queue = queue.Queue(maxsize=4)
        self.feed_count = 0

    def feed(self, audio_bytes: bytes, timestamp_ms: int) -> None:
        self.feed_count += 1
        try:
            self.q.put_nowait((audio_bytes, timestamp_ms))
        except queue.Full:
            pass  # drop-on-full is the contract


class _RaisingSink:
    """A sink that raises on every block — must not break dictation."""

    def __init__(self) -> None:
        self.feed_count = 0

    def feed(self, audio_bytes: bytes, timestamp_ms: int) -> None:
        self.feed_count += 1
        raise RuntimeError("intentional sink failure")


class TestAmbientTapDelivery:
    """The sink receives every block, whether or not dictation is active."""

    @patch("agentvoca.audio.capture.select_device")
    def test_sink_receives_blocks_when_not_recording(self, mock_select: MagicMock) -> None:
        mock_select.return_value = _MOCK_DEVICE
        event_bus = EventBus()
        sink = _CollectingSink()

        with patch("agentvoca.audio.capture.sd.InputStream"):
            capt = AudioCapture(event_bus=event_bus)
            capt.start()
            capt.set_ambient_sink(sink)

            N = 10
            for _ in range(N):
                capt._audio_callback(_indata(), 1024, None, None)

            assert not capt.is_recording
            assert sink.feed_count == N, (
                f"Sink should receive {N} blocks while idle, got {sink.feed_count}"
            )
            # The dictation buffer must remain empty — ambient does not
            # accidentally double-feed dictation.
            assert capt._audio_buffer == []
            capt.stop()

    @patch("agentvoca.audio.capture.select_device")
    def test_sink_receives_blocks_while_recording(self, mock_select: MagicMock) -> None:
        mock_select.return_value = _MOCK_DEVICE
        event_bus = EventBus()
        sink = _CollectingSink()

        with patch("agentvoca.audio.capture.sd.InputStream"):
            capt = AudioCapture(event_bus=event_bus)
            capt.start()
            capt.set_ambient_sink(sink)

            capt.start_recording()
            for _ in range(5):
                capt._audio_callback(_indata(), 1024, None, None)

            assert sink.feed_count == 5
            # Dictation buffer must have received the same 5 blocks.
            assert len(capt._audio_buffer) == 5
            capt.stop_recording()
            capt.stop()


class TestAmbientTapBudget:
    """Audio-callback p99 < 5 ms with the tap installed.

    Same methodology as the existing R2 budget test in
    ``test_capture_vad_worker.py`` — feed N synthetic blocks through
    ``_audio_callback`` directly, time each call, assert the p99.
    """

    @patch("agentvoca.audio.capture.select_device")
    def test_callback_p99_under_5ms_with_sink_installed(self, mock_select: MagicMock) -> None:
        mock_select.return_value = _MOCK_DEVICE
        event_bus = EventBus()
        # A sink that takes a few microseconds (mirrors a put_nowait).
        sink = _FullQueueSink()

        with patch("agentvoca.audio.capture.sd.InputStream"):
            capt = AudioCapture(event_bus=event_bus)
            capt.start()
            capt.set_ambient_sink(sink)

            # 469 blocks ≈ 30 s of fake audio at 1024 frames @ 16 kHz.
            N = 469
            durations_ms: list[float] = []
            for _ in range(N):
                t0 = time.perf_counter()
                capt._audio_callback(_indata(), 1024, None, None)
                durations_ms.append((time.perf_counter() - t0) * 1000)

            durations_ms.sort()
            p99_idx = max(0, int(0.99 * len(durations_ms)) - 1)
            p99 = durations_ms[p99_idx]
            assert p99 < 5.0, f"Callback p99 {p99:.2f} ms exceeds 5 ms budget"

            # The sink saw every block, even though its queue stayed full.
            assert sink.feed_count == N

            capt.stop()


class TestNoSink:
    """With no sink installed, the callback is byte-identical to v0.3.6."""

    @patch("agentvoca.audio.capture.select_device")
    def test_callback_works_without_sink(self, mock_select: MagicMock) -> None:
        mock_select.return_value = _MOCK_DEVICE
        event_bus = EventBus()

        with patch("agentvoca.audio.capture.sd.InputStream"):
            capt = AudioCapture(event_bus=event_bus)
            capt.start()
            # No set_ambient_sink call.

            # Not-recording branch.
            capt._audio_callback(_indata(), 1024, None, None)
            assert capt._audio_buffer == []

            # Recording branch.
            capt.start_recording()
            capt._audio_callback(_indata(), 1024, None, None)
            assert len(capt._audio_buffer) == 1
            capt.stop_recording()
            capt.stop()

    @patch("agentvoca.audio.capture.select_device")
    def test_sink_can_be_cleared(self, mock_select: MagicMock) -> None:
        mock_select.return_value = _MOCK_DEVICE
        event_bus = EventBus()
        sink = _CollectingSink()

        with patch("agentvoca.audio.capture.sd.InputStream"):
            capt = AudioCapture(event_bus=event_bus)
            capt.start()
            capt.set_ambient_sink(sink)

            capt._audio_callback(_indata(), 1024, None, None)
            assert sink.feed_count == 1

            capt.set_ambient_sink(None)
            capt._audio_callback(_indata(), 1024, None, None)
            assert sink.feed_count == 1, "Clearing the sink should stop delivery"
            capt.stop()


class TestRaisingSink:
    """A sink that raises must not break dictation."""

    @patch("agentvoca.audio.capture.select_device")
    def test_raising_sink_does_not_break_dictation(self, mock_select: MagicMock) -> None:
        mock_select.return_value = _MOCK_DEVICE
        event_bus = EventBus()
        sink = _RaisingSink()

        with patch("agentvoca.audio.capture.sd.InputStream"):
            capt = AudioCapture(event_bus=event_bus)
            capt.start()
            capt.set_ambient_sink(sink)

            capt.start_recording()
            for _ in range(3):
                capt._audio_callback(_indata(), 1024, None, None)

            # Sink saw every block even though it raised on every one.
            assert sink.feed_count == 3
            # Dictation still received the same blocks.
            assert len(capt._audio_buffer) == 3
            capt.stop_recording()
            capt.stop()
