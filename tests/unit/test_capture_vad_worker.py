"""Tests for ``AudioCapture`` VAD inference on a dedicated worker thread (R2).

Covers:
- The audio callback does NOT call ``VAD.is_speech`` itself — only the
  worker does, exactly once per block. (R1 invariant preserved under R2.)
- Worker thread joins cleanly on ``stop()`` (within 2 s).
- ``start_recording()`` flushes stale items left in the queue.
- Callback latency p99 stays well under real-time even when inference is slow
  (because the callback never blocks on inference; it reads a cached bool).
- Auto-stop still fires within ``silence_timeout_ms + a few blocks``.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import numpy as np

from agentvoca.audio.capture import AudioCapture
from agentvoca.audio.vad import VAD
from agentvoca.core.async_loop import AsyncLoopThread
from agentvoca.core.event_bus import EventBus


def _make_block() -> bytes:
    """One block of float32 silence (1024 frames approx 64 ms @ 16 kHz)."""
    return b"\x00\x00\x00\x00" * 1024


def _make_indata() -> np.ndarray:
    """A 1024-frame silent ``indata`` shaped like sounddevice's callback."""
    return np.zeros((1024, 1), dtype=np.float32)


def _stub_vad(event_bus: EventBus, is_speech_fn) -> VAD:
    """Build a ``VAD`` whose ``is_available`` is True and ``is_speech`` is stubbed."""
    vad = VAD(event_bus=event_bus)
    vad._model = object()  # pretend silero loaded
    vad.is_speech = is_speech_fn  # type: ignore[assignment]
    return vad


def _drain_worker(capt: AudioCapture, expected: int, timeout: float = 2.0) -> int:
    """Wait until the worker has consumed ``expected`` items.

    Useful to make assertions deterministic; the worker is one element per
    loop iteration, so this just gives it time to drain.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if capt._vad_queue.qsize() == 0 and expected > 0:
            break
        time.sleep(0.01)
    return expected


class TestSingleVADInference:
    """R1: each 64 ms audio block triggers exactly ONE silero inference."""

    @patch("agentvoca.audio.capture.select_device")
    def test_callback_enqueues_each_block_worker_counts_once(
        self, mock_select: MagicMock
    ) -> None:
        mock_select.return_value = {"name": "Mock", "index": 0}
        event_bus = EventBus()
        call_counter = {"n": 0}

        def counting_is_speech(chunk: bytes) -> bool:
            call_counter["n"] += 1
            return True

        vad = _stub_vad(event_bus, counting_is_speech)

        with patch("agentvoca.audio.capture.sd.InputStream"):
            capt = AudioCapture(event_bus=event_bus, vad=vad)
            capt.start()
            capt.start_recording()

        N = 15
        for _ in range(N):
            capt._audio_callback(_make_indata(), 1024, None, None)

        # Wait for the worker to drain (best-effort determinism).
        _drain_worker(capt, expected=N)

        # Allow a short grace period for the last item to be processed.
        deadline = time.time() + 1.0
        while time.time() < deadline and call_counter["n"] < N:
            time.sleep(0.01)

        # R1+R2: exactly one is_speech call per block. Old pre-R1 code called
        # it twice per block (2N). New code: worker is the only call site.
        assert call_counter["n"] == N, (
            f"Expected {N} is_speech calls, got {call_counter['n']}"
        )

        capt.stop_recording()
        capt.stop()


class TestVADWorkerShutdown:
    """R2: the VAD worker thread joins cleanly on stream close."""

    @patch("agentvoca.audio.capture.select_device")
    def test_worker_joins_after_stop(self, mock_select: MagicMock) -> None:
        mock_select.return_value = {"name": "Mock", "index": 0}
        event_bus = EventBus()
        vad = _stub_vad(event_bus, lambda chunk: True)

        with patch("agentvoca.audio.capture.sd.InputStream"):
            capt = AudioCapture(event_bus=event_bus, vad=vad)
            capt.start()
            capt.start_recording()
            assert capt._vad_thread is not None
            assert capt._vad_thread.is_alive()

            capt.stop_recording()  # drain chunker flush via loop thread
            capt.stop()  # should join the VAD worker within 2 s

        assert capt._vad_thread is None


class TestStaleQueueHygiene:
    """R2: ``start_recording`` clears leftover blocks from a prior recording."""

    @patch("agentvoca.audio.capture.select_device")
    def test_stale_queue_drained_at_recording_start(
        self, mock_select: MagicMock
    ) -> None:
        mock_select.return_value = {"name": "Mock", "index": 0}
        event_bus = EventBus()
        vad = _stub_vad(event_bus, lambda chunk: True)

        with patch("agentvoca.audio.capture.sd.InputStream"):
            capt = AudioCapture(event_bus=event_bus, vad=vad)
            capt.start()

            # Manually push a few items onto the queue without a worker.
            for _ in range(3):
                capt._vad_queue.put_nowait((_make_block(), 0))

            assert capt._vad_queue.qsize() == 3

            capt.start_recording()

            assert capt._vad_queue.qsize() == 0
            assert capt._last_vad_speech is True  # optimistic default

            capt.stop()


class TestCallbackLatency:
    """R2: callback p99 stays under real-time even when VAD is slow."""

    @patch("agentvoca.audio.capture.select_device")
    def test_callback_p99_under_5ms_with_slow_inference(
        self, mock_select: MagicMock
    ) -> None:
        mock_select.return_value = {"name": "Mock", "index": 0}
        event_bus = EventBus()

        def slow_inference(chunk: bytes) -> bool:
            time.sleep(0.01)  # 10 ms; would blow the budget if on-thread
            return True

        vad = _stub_vad(event_bus, slow_inference)

        with patch("agentvoca.audio.capture.sd.InputStream"):
            capt = AudioCapture(event_bus=event_bus, vad=vad)
            capt.start()
            capt.start_recording()

            # Pre-warm the cached bool by triggering a single inference,
            # then reading the result after letting the worker drain. We
            # avoid simulating the full slow path on the test thread; we
            # only need _last_vad_speech to settle to True before timing.
            capt._audio_callback(_make_indata(), 1024, None, None)
            # Wait for the worker to drain the single item.
            for _ in range(50):
                if capt._vad_queue.qsize() == 0:
                    break
                time.sleep(0.01)
            # Now assert cached bool is True (first chunk returns True).
            deadline = time.time() + 0.5
            while time.time() < deadline and not capt._last_vad_speech:
                time.sleep(0.005)

            # Feed 30 synthetic blocks (approx 2 s of fake audio) and time
            # each callback. None of these calls should block on silero.
            durations_ms = []
            for _ in range(30):
                t0 = time.perf_counter()
                capt._audio_callback(_make_indata(), 1024, None, None)
                durations_ms.append((time.perf_counter() - t0) * 1000)

            durations_ms.sort()
            p99 = durations_ms[int(0.99 * len(durations_ms)) - 1]
            assert p99 < 5.0, f"Callback p99 {p99:.2f} ms exceeds 5 ms budget"

            capt.stop_recording()
            capt.stop()


class TestAutoStopStillFires:
    """R2: auto-stop still fires within ``silence_timeout_ms + a few blocks``."""

    @patch("agentvoca.audio.capture.select_device")
    async def test_auto_stop_fires_after_timeout(
        self, mock_select: MagicMock
    ) -> None:
        loop_thread = AsyncLoopThread()
        loop_thread.start()

        try:
            mock_select.return_value = {"name": "Mock", "index": 0}
            event_bus = EventBus()
            event_bus.set_loop(loop_thread.loop)

            speech_blocks = {"n": 0}

            def stubbed_is_speech(chunk: bytes) -> bool:
                speech_blocks["n"] += 1
                return speech_blocks["n"] <= 16  # speech for first 16, then silence

            vad = _stub_vad(event_bus, stubbed_is_speech)

            from agentvoca.audio.chunker import AudioChunker

            chunker = AudioChunker(
                event_bus=event_bus,
                chunk_ms=500,
                window_s=0,
                sample_rate=16000,
            )

            with patch("agentvoca.audio.capture.sd.InputStream"):
                capt = AudioCapture(
                    event_bus=event_bus,
                    vad=vad,
                    silence_timeout_ms=900,
                    chunker=chunker,
                    loop=loop_thread.loop,
                )
                capt.start()
                capt.start_recording()

                stopped_at: list[float] = []
                old_stop = capt.stop_recording

                def capture_stop() -> None:
                    stopped_at.append(time.time())
                    old_stop()

                capt.stop_recording = capture_stop  # type: ignore[assignment]

                t0 = time.time()
                # Feed blocks until the stub flips to silence (block 17+).
                for _ in range(20):
                    capt._audio_callback(_make_indata(), 1024, None, None)
                    await asyncio.sleep(0.005)

                # Wait for the worker to reflect the flip in the cached bool.
                deadline = time.time() + 2.0
                while time.time() < deadline and capt._last_vad_speech:
                    await asyncio.sleep(0.01)
                assert capt._last_vad_speech is False, "worker never flipped to silence"

                # The silence timeout is wall-clock: real time must exceed
                # silence_timeout_ms (900) before the callback's check trips.
                await asyncio.sleep(1.0)
                for _ in range(3):
                    capt._audio_callback(_make_indata(), 1024, None, None)
                    if stopped_at:
                        break

                assert stopped_at, "auto-stop never fired"
                elapsed = stopped_at[0] - t0
                # Bound: flip detection (~0.2 s) + timeout wait (1.0 s) + slack.
                assert elapsed < 3.0, f"auto-stop fired after {elapsed:.2f}s"

                capt.stop()
        finally:
            loop_thread.stop()
