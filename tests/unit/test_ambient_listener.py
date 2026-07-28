"""Tests for ``AmbientListener`` (OBS-11).

The listener segments a stream of audio blocks into utterances using a
VAD. Tests inject a scripted VAD that returns a deterministic sequence
of speech/silence decisions without loading silero. ``feed()`` is fed
synthetic blocks at 64 ms per block; the listener's state machine and
emission are asserted deterministically.

The only "real time" in these tests is the time spent joining the
worker thread — well under a second. No ``time.sleep``.
"""

from __future__ import annotations

import time
import tracemalloc
from typing import Optional

import pytest

from agentvoca.core.async_loop import AsyncLoopThread
from agentvoca.core.event_bus import EventBus
from agentvoca.observer.audio import AmbientListener

# 1024 frames @ 16 kHz float32 mono = 4096 bytes. Matches the sounddevice
# callback block in production.
_BYTES_PER_BLOCK = 1024 * 4


class ScriptedVAD:
    """Returns a scripted sequence of (is_speech) per ``process_chunk`` call.

    When the script is exhausted the last value is repeated.
    """

    def __init__(self, script: list[bool]) -> None:
        self._script = list(script)
        self._idx = 0
        self._available = True
        self.calls: list[tuple[bytes, int]] = []

    @property
    def is_available(self) -> bool:
        return self._available

    def process_chunk(self, audio_bytes: bytes, timestamp_ms: int) -> bool:
        self.calls.append((audio_bytes, timestamp_ms))
        if self._idx < len(self._script):
            v = self._script[self._idx]
            self._idx += 1
            return v
        return self._script[-1] if self._script else False


def _ts(i: int) -> int:
    """Block i's timestamp at 64 ms per block, starting at 1000 ms."""
    return 1000 + i * 64


def _make_block(seed: int = 0) -> bytes:
    """One block of fake audio. Distinct per ``seed`` for debugging."""
    return bytes([seed % 256]) * _BYTES_PER_BLOCK


def _wait_for_count(listener: AmbientListener, n: int, timeout: float = 2.0) -> None:
    """Block until ``utterance_count >= n`` or timeout. Test-only barrier."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if listener.utterance_count >= n:
            return
        time.sleep(0.005)
    raise AssertionError(
        f"Timeout waiting for utterance_count >= {n} (got {listener.utterance_count})"
    )


@pytest.fixture
def loop_thread():
    t = AsyncLoopThread()
    t.start()
    yield t
    t.stop()


@pytest.fixture
def collected_utterances() -> list[tuple[bytes, int, int]]:
    return []


def _make_listener(
    loop: AsyncLoopThread,
    utterances_out: list[tuple[bytes, int, int]],
    *,
    vad: Optional[ScriptedVAD] = None,
    on_speech_onset_out: Optional[list[int]] = None,
    silence_timeout_ms: int = 900,
    min_utterance_ms: int = 400,
    max_utterance_ms: int = 30000,
) -> AmbientListener:
    """Build a listener with a real (or scripted) VAD."""

    def on_utterance(audio: bytes, ts_ms: int, duration_ms: int) -> None:
        utterances_out.append((audio, ts_ms, duration_ms))

    def on_speech_onset() -> None:
        if on_speech_onset_out is not None:
            on_speech_onset_out.append(1)

    return AmbientListener(
        event_bus=EventBus(),
        loop=loop.loop,
        on_utterance=on_utterance,
        silence_timeout_ms=silence_timeout_ms,
        min_utterance_ms=min_utterance_ms,
        max_utterance_ms=max_utterance_ms,
        vad=vad,
        on_speech_onset=on_speech_onset if on_speech_onset_out is not None else None,
    )


# ── Happy path ─────────────────────────────────────────────────────


class TestUtteranceEmission:
    def test_speech_then_silence_emits_one_utterance(
        self, loop_thread: AsyncLoopThread, collected_utterances: list
    ) -> None:
        # 5 speech blocks then 16 silence blocks (~1 s) → one utterance.
        # duration ≈ 21 blocks * 64 ms = 1344 ms (above min_utterance_ms=400).
        script = [True] * 5 + [False] * 16
        vad = ScriptedVAD(script)
        listener = _make_listener(loop_thread, collected_utterances, vad=vad)
        listener.start()
        try:
            for i in range(len(script)):
                listener.feed(_make_block(i), _ts(i))
            _wait_for_count(listener, 1)
        finally:
            listener.stop()

        assert len(collected_utterances) == 1
        audio, ts_ms, duration_ms = collected_utterances[0]
        # The emitted audio must include all blocks observed during
        # SPEAKING (5 speech + 16 silence). Pre-roll is empty.
        assert len(audio) == (5 + 16) * _BYTES_PER_BLOCK
        assert ts_ms == _ts(0)
        assert duration_ms >= 5 * 64

    def test_short_burst_below_min_utterance_is_dropped(
        self, loop_thread: AsyncLoopThread, collected_utterances: list
    ) -> None:
        # 1 speech block, then enough silence to close the utterance,
        # but total duration (1*64 + silence_timeout_ms) is ≥ min if we
        # set min high. So instead, set min_utterance_ms high enough that
        # the emit is dropped post-hoc. duration ≈ 5 blocks × 64ms = 320ms.
        script = [True, False, False, False, False]
        vad = ScriptedVAD(script)
        listener = _make_listener(
            loop_thread,
            collected_utterances,
            vad=vad,
            silence_timeout_ms=64,  # 1 block of silence closes
            min_utterance_ms=10_000,  # higher than the actual duration
        )
        listener.start()
        try:
            for i in range(len(script)):
                listener.feed(_make_block(i), _ts(i))
            # Give the worker a chance to process everything.
            time.sleep(0.1)
        finally:
            listener.stop()

        assert collected_utterances == [], (
            f"Expected 0 utterances (below min_utterance_ms), got {len(collected_utterances)}"
        )
        assert listener.utterance_count == 0

    def test_continuous_speech_emits_multiple_utterances(
        self, loop_thread: AsyncLoopThread, collected_utterances: list
    ) -> None:
        # max_utterance_ms = 5 * 64 = 320ms. Feed 30 speech blocks
        # (1920 ms) with no silence — expect ≈ 5 emits during the feed
        # loop, plus the trailing in-progress emit on stop() → 6 total.
        # We pick silence_timeout_ms larger than max_utterance_ms so
        # the only emission path is the max cap.
        script = [True] * 30
        vad = ScriptedVAD(script)
        listener = _make_listener(
            loop_thread,
            collected_utterances,
            vad=vad,
            silence_timeout_ms=60_000,  # never fires
            min_utterance_ms=0,
            max_utterance_ms=320,  # 5 blocks
        )
        listener.start()
        try:
            for i in range(len(script)):
                listener.feed(_make_block(i), _ts(i))
            # Flush+stop is called in the finally; wait for the trailing emit.
            listener.flush()
            _wait_for_count(listener, 6)
        finally:
            listener.stop()

        assert listener.utterance_count == 6, (
            f"Expected 6 utterances from max_utterance_ms cap, got {listener.utterance_count}"
        )

    def test_peak_memory_bounded_under_continuous_speech(
        self, loop_thread: AsyncLoopThread, collected_utterances: list
    ) -> None:
        # Same shape as above but measure tracemalloc. RSS test in
        # OBS-19 is the budget gate; this is a smoke check that the
        # listener does not retain a growing buffer.
        script = [True] * 60
        vad = ScriptedVAD(script)
        listener = _make_listener(
            loop_thread,
            collected_utterances,
            vad=vad,
            silence_timeout_ms=60_000,
            min_utterance_ms=0,
            max_utterance_ms=320,
        )
        tracemalloc.start()
        try:
            listener.start()
            for i in range(len(script)):
                listener.feed(_make_block(i), _ts(i))
            listener.flush()
            _wait_for_count(listener, 12)
            current, peak = tracemalloc.get_traced_memory()
        finally:
            listener.stop()
            tracemalloc.stop()

        # One cap-emission at 16 kHz float32 is 320 ms × 16_000 × 4
        # = 20.5 KB. Allow 50× that for pre-roll + VAD + list overhead.
        one_utt_bytes = 320 * 16 * 4
        assert peak < 50 * one_utt_bytes, (
            f"Peak {peak} bytes exceeds 50x one max utterance ({one_utt_bytes})"
        )


# ── Speech-onset hook ──────────────────────────────────────────────


class TestSpeechOnset:
    def test_on_speech_onset_fires_once_per_utterance(
        self, loop_thread: AsyncLoopThread, collected_utterances: list
    ) -> None:
        # Two utterances: speech1 → silence → speech2 → silence.
        script = (
            [True] * 3
            + [False] * 16  # utterance 1
            + [True] * 3
            + [False] * 16  # utterance 2
        )
        vad = ScriptedVAD(script)
        onsets: list[int] = []
        listener = _make_listener(
            loop_thread, collected_utterances, vad=vad, on_speech_onset_out=onsets
        )
        listener.start()
        try:
            for i in range(len(script)):
                listener.feed(_make_block(i), _ts(i))
            _wait_for_count(listener, 2)
        finally:
            listener.stop()

        assert listener.utterance_count == 2
        assert len(onsets) == 2, f"Expected 2 onsets, got {len(onsets)}"

    def test_on_speech_onset_not_fired_on_silence(
        self, loop_thread: AsyncLoopThread, collected_utterances: list
    ) -> None:
        script = [False] * 30
        vad = ScriptedVAD(script)
        onsets: list[int] = []
        listener = _make_listener(
            loop_thread, collected_utterances, vad=vad, on_speech_onset_out=onsets
        )
        listener.start()
        try:
            for i in range(len(script)):
                listener.feed(_make_block(i), _ts(i))
            time.sleep(0.05)  # let worker drain
        finally:
            listener.stop()

        assert onsets == []


# ── Pre-roll ───────────────────────────────────────────────────────


class TestPreRoll:
    def test_emitted_buffer_includes_blocks_before_speech(
        self, loop_thread: AsyncLoopThread, collected_utterances: list
    ) -> None:
        # 4 silence blocks (pre-roll), 3 speech blocks, then enough
        # silence to close. Pre-roll maxlen default ≈ 5 blocks.
        preroll_count = 4
        speech_count = 3
        trailing_silence = 16
        script = [False] * preroll_count + [True] * speech_count + [False] * trailing_silence
        vad = ScriptedVAD(script)
        listener = _make_listener(loop_thread, collected_utterances, vad=vad)
        listener.start()
        try:
            for i in range(len(script)):
                listener.feed(_make_block(i), _ts(i))
            _wait_for_count(listener, 1)
        finally:
            listener.stop()

        assert len(collected_utterances) == 1
        audio, ts_ms, _dur = collected_utterances[0]
        # The buffer includes pre-roll + speech + trailing silence. The
        # pre-roll is exactly ``preroll_count`` blocks because that is
        # what the deque held at the IDLE→SPEAKING transition.
        assert len(audio) == (preroll_count + speech_count + trailing_silence) * _BYTES_PER_BLOCK
        # The start ts of the utterance is the start of the pre-roll.
        assert ts_ms == _ts(0)
        # The first block in the emitted audio is the first pre-roll
        # block (which is silence — block 0). That proves the pre-roll
        # actually made it into the buffer.
        assert audio[:8] == _make_block(0)[:8]


# ── Hot-path budget ────────────────────────────────────────────────


class TestHotPathBudget:
    def test_feed_does_not_block_with_full_queue(
        self, loop_thread: AsyncLoopThread, collected_utterances: list
    ) -> None:
        # Silero would be the realistic slow path. Here we use a VAD
        # whose process_chunk sleeps — the worker is the bottleneck.
        # feed() must still return in microseconds.
        class SlowVAD(ScriptedVAD):
            def process_chunk(self, audio_bytes: bytes, ts_ms: int) -> bool:  # type: ignore[override]
                time.sleep(0.01)  # 10 ms — would blow the budget
                return super().process_chunk(audio_bytes, ts_ms)

        vad = SlowVAD([True] * 200)  # many speech blocks; the worker chokes
        listener = _make_listener(
            loop_thread,
            collected_utterances,
            vad=vad,
            silence_timeout_ms=60_000,
            min_utterance_ms=0,
            max_utterance_ms=64 * 50,  # 3.2s — single utterance
        )
        listener.start()
        try:
            t0 = time.perf_counter()
            for i in range(1000):
                listener.feed(_make_block(i), _ts(i))
            elapsed = (time.perf_counter() - t0) * 1000
        finally:
            listener.stop()
        # 1000 feed calls must take well under 10 ms total — the budget
        # is microseconds per call, the whole burst under 10 ms.
        assert elapsed < 10.0, f"1000 feed() calls took {elapsed:.1f} ms; budget is < 10 ms"


# ── Lifecycle ──────────────────────────────────────────────────────


class TestLifecycle:
    def test_stop_joins_within_timeout(
        self, loop_thread: AsyncLoopThread, collected_utterances: list
    ) -> None:
        vad = ScriptedVAD([True] * 10)
        listener = _make_listener(loop_thread, collected_utterances, vad=vad)
        listener.start()
        for i in range(10):
            listener.feed(_make_block(i), _ts(i))
        t0 = time.time()
        listener.stop(timeout=2.0)
        elapsed = time.time() - t0
        assert elapsed < 1.0, f"stop() took {elapsed:.2f}s"

    def test_flush_emits_in_progress_utterance(
        self, loop_thread: AsyncLoopThread, collected_utterances: list
    ) -> None:
        # Speech starts, then we flush mid-utterance.
        script = [True] * 5 + [True] * 100  # all speech
        vad = ScriptedVAD(script)
        listener = _make_listener(
            loop_thread,
            collected_utterances,
            vad=vad,
            silence_timeout_ms=60_000,
            min_utterance_ms=0,
            max_utterance_ms=60_000,
        )
        listener.start()
        try:
            for i in range(5):
                listener.feed(_make_block(i), _ts(i))
            time.sleep(0.05)  # let the worker process
            listener.flush()
            _wait_for_count(listener, 1)
        finally:
            listener.stop()

        assert len(collected_utterances) == 1
        audio, _, _ = collected_utterances[0]
        assert len(audio) == 5 * _BYTES_PER_BLOCK

    def test_stop_emits_in_progress_utterance(
        self, loop_thread: AsyncLoopThread, collected_utterances: list
    ) -> None:
        # Same shape as flush, but via stop(). The worker must emit the
        # in-progress utterance before exiting.
        vad = ScriptedVAD([True] * 5)
        listener = _make_listener(
            loop_thread,
            collected_utterances,
            vad=vad,
            silence_timeout_ms=60_000,
            min_utterance_ms=0,
            max_utterance_ms=60_000,
        )
        listener.start()
        for i in range(5):
            listener.feed(_make_block(i), _ts(i))
        time.sleep(0.05)
        listener.stop()
        assert len(collected_utterances) == 1

    def test_start_idempotent(
        self, loop_thread: AsyncLoopThread, collected_utterances: list
    ) -> None:
        vad = ScriptedVAD([True] * 3 + [False] * 16)
        listener = _make_listener(loop_thread, collected_utterances, vad=vad)
        listener.start()
        first = listener._thread
        listener.start()  # idempotent
        assert listener._thread is first
        listener.stop()
