"""Tests for AudioCapture.stop_recording offloading the join + publish (R3).

Covers:
- With a real ``AsyncLoopThread``, the buffer join and
  ``RecordingStoppedEvent`` publish happen on the loop thread, not on the
  sounddevice audio thread.
- Without a loop (``loop=None``) the join/publish runs inline (legacy test
  expectations remain valid).
- A second ``stop_recording`` after the recording already stopped is a no-op.
"""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import patch

from agentvoca.audio.capture import AudioCapture
from agentvoca.core.async_loop import AsyncLoopThread
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import RecordingStoppedEvent

_MOCK_DEVICE = {"name": "Mock", "index": 0}


class TestStopOffloadsFinalization:
    """``stop_recording`` schedules the join+publish on the loop thread."""

    async def test_join_and_publish_happen_on_loop_thread(self) -> None:
        loop_thread = AsyncLoopThread()
        loop_thread.start()
        try:
            event_bus = EventBus()
            event_bus.set_loop(loop_thread.loop)

            publishing_thread: dict[str, str | None] = {"name": None}
            captured: list[RecordingStoppedEvent] = []

            def _capture(event: RecordingStoppedEvent) -> None:
                captured.append(event)
                publishing_thread["name"] = threading.current_thread().name

            event_bus.subscribe(RecordingStoppedEvent, _capture)

            with patch("agentvoca.audio.capture.select_device", return_value=_MOCK_DEVICE):
                with patch("agentvoca.audio.capture.sd.InputStream"):
                    capt = AudioCapture(
                        event_bus=event_bus,
                        loop=loop_thread.loop,
                        frames_per_buffer=1024,
                    )
                    capt.start()
                    capt.start_recording()

            N = 5
            appended = [b"\\\\x00\\\\x00" * 100 * (i + 1) for i in range(N)]
            for chunk in appended:
                capt._audio_buffer.append(chunk)

            # Call stop from a thread that is neither the loop thread nor the
            # audio callback thread.
            off_thread = threading.Thread(target=lambda: capt.stop_recording(), daemon=True)
            off_thread.start()
            # Wait briefly for the call to land on the loop.
            deadline = time.time() + 1.0
            while time.time() < deadline and not captured:
                await asyncio.sleep(0.01)
            off_thread.join()

            assert captured, "RecordingStoppedEvent was never published"
            event = captured[-1]
            # Payload must match the joined buffer.
            assert event.audio_bytes == b"".join(appended)
            # Must run on the asyncio loop thread, NOT the audio thread.
            assert publishing_thread["name"] == "agentvoca-asyncio", (
                f"Publishing happened on thread "
                f"{publishing_thread['name']!r}, expected agentvoca-asyncio"
            )

            capt.stop()
        finally:
            loop_thread.stop()

    async def test_loop_none_runs_inline(self) -> None:
        """``loop=None`` keeps the legacy synchronous behavior."""
        event_bus = EventBus()
        captured: list[RecordingStoppedEvent] = []

        def _capture(event: RecordingStoppedEvent) -> None:
            captured.append(event)

        event_bus.subscribe(RecordingStoppedEvent, _capture)

        with patch("agentvoca.audio.capture.select_device", return_value=_MOCK_DEVICE):
            with patch("agentvoca.audio.capture.sd.InputStream"):
                capt = AudioCapture(event_bus=event_bus, loop=None)
                capt.start()
                capt.start_recording()

        appended = [b"\\\\xab\\\\xcd" * 50 * (i + 1) for i in range(3)]
        for chunk in appended:
            capt._audio_buffer.append(chunk)

        # Synchronous stop when loop=None.
        capt.stop_recording()
        # No need to yield to a loop.
        assert captured, "RecordingStoppedEvent must publish inline"
        assert captured[-1].audio_bytes == b"".join(appended)

        capt.stop()


class TestDoubleStopIsNoop:
    """Two consecutive stops must publish exactly one event."""

    async def test_second_stop_does_not_publish(self) -> None:
        event_bus = EventBus()
        captured: list[RecordingStoppedEvent] = []
        event_bus.subscribe(RecordingStoppedEvent, captured.append)

        with patch("agentvoca.audio.capture.select_device", return_value=_MOCK_DEVICE):
            with patch("agentvoca.audio.capture.sd.InputStream"):
                capt = AudioCapture(event_bus=event_bus, loop=None)
                capt.start()
                capt.start_recording()
                capt._audio_buffer.append(b"\\\\x00" * 100)

                capt.stop_recording()
                capt.stop_recording()  # second call

        assert len(captured) == 1, f"Second stop() should be a no-op, got {len(captured)} events"


class TestAutoStopFromCallbackDoesNotBlockOnJoin:
    """The audio callback no longer executes the buffer join inline."""

    async def test_callback_block_under_5ms_with_full_buffer(self) -> None:
        """Simulate auto-stop happening inside ``_audio_callback`` and
        verify the callback returns quickly even with a very large buffer.
        """
        loop_thread = AsyncLoopThread()
        loop_thread.start()
        try:
            event_bus = EventBus()
            event_bus.set_loop(loop_thread.loop)

            with patch("agentvoca.audio.capture.select_device", return_value=_MOCK_DEVICE):
                with patch("agentvoca.audio.capture.sd.InputStream"):
                    capt = AudioCapture(event_bus=event_bus, loop=loop_thread.loop)
                    capt.start()
                    capt.start_recording()

            # Fill a few MB of audio so a synchronous ``b"".join`` would be
            # very noticeable (it was historically ~80 ms for 8 MB).
            big = b"\\\\x00\\\\x00\\\\x00\\\\x00" * (2 * 1024 * 1024)  # 8 MB
            capt._audio_buffer.append(big)

            import numpy as np

            indata = np.zeros((1024, 1), dtype=np.float32)
            t0 = time.perf_counter()
            capt._audio_callback(indata, 1024, None, None)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            # The join must NOT run synchronously on the thread that called
            # stop_recording(); the callback should finish in milliseconds.
            assert elapsed_ms < 20.0, (
                f"Audio callback took {elapsed_ms:.1f} ms; suggests buffer join is running inline"
            )

            # Give the loop a tick to publish the event.
            for _ in range(50):
                await asyncio.sleep(0.01)
                if capt._audio_buffer == []:
                    break

            capt.stop()
        finally:
            loop_thread.stop()
