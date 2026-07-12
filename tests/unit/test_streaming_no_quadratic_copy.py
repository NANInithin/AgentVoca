"""Tests for the streaming-ASR O(N) memory fix (R4).

Covers:
- Churn bound: peak allocation stays linear, not quadratic, over ~60 s of audio.
- BufferError regression: ``_window_snapshot`` correctly releases the bytearray
  export so the caller can immediately ``extend`` it.
- Equivalence: ``_window_snapshot`` is byte-identical to the old
  ``np.frombuffer(bytes(buf))`` path.
"""

from __future__ import annotations

import struct
import tracemalloc

import numpy as np
import pytest

from agentvoca.asr.faster_whisper import FasterWhisperProvider
from agentvoca.config.schema import ASRConfig


def _audio_bytes(seconds: float, sample_rate: int = 16000) -> bytes:
    """Generate ``seconds`` of float32 zeros (little-endian)."""
    n = max(1, int(seconds * sample_rate))
    return struct.pack(f"<{n}f", *([0.0] * n))


# ── 1. Churn bound ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_churn_bound_remains_linear(monkeypatch) -> None:
    """Drive the streaming loop with ~60 s of audio and bound allocation.

    The old O(N²) code would peak at `len(total_audio) * O(chunks)`; the
    new code peaks near `len(window) * small_constant`. We use a generous
    ceiling of `len(total_audio) * 3` to tolerate the snapshot copies.
    """
    sample_rate = 16000
    audio = _audio_bytes(60.0, sample_rate=sample_rate)  # ~3.8 MB

    # Build a fake streaming model that completes instantly.
    class FakeStreamingModel:
        def transcribe(self, arr, language, beam_size, vad_filter):
            text = "x"  # tiny text — we don't care about content here
            return iter([type("S", (), {"text": text})()]), None

    class FakeAccurateModel:
        def transcribe(self, arr, language, beam_size, vad_filter):
            return iter([]), type("I", (), {"language": "en", "language_probability": 1.0})()

    cfg = ASRConfig(provider="faster_whisper", streaming=True, streaming_window_s=8)
    provider = FasterWhisperProvider(cfg)
    provider._streaming_model = FakeStreamingModel()  # type: ignore[assignment]
    provider._model = FakeAccurateModel()  # type: ignore[assignment]

    # Drive the iterator like the orchestrator does: a chunk every ~500 ms.
    chunk_samples = int(0.5 * sample_rate)
    chunk_bytes = struct.pack(f"<{chunk_samples}f", *([0.0] * chunk_samples))

    async def chunk_stream():
        for _ in range(len(audio) // len(chunk_bytes)):
            yield chunk_bytes
        # End-of-stream marker equivalent — the stream ends naturally.

    tracemalloc.start()
    peak_before = tracemalloc.get_traced_memory()[1]

    async def collect() -> list:
        out: list = []
        async for seg in provider.stream_transcribe(chunk_stream(), sample_rate=sample_rate):
            out.append(seg)
        return out

    await collect()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    allocated = peak - peak_before
    ceiling = len(audio) * 3
    assert allocated < ceiling, (
        f"Peak allocation {allocated} bytes exceeds O(N) ceiling "
        f"{ceiling} bytes (len(audio)={len(audio)})"
    )


# ── 2. BufferError regression ─────────────────────────────────────────


def test_window_snapshot_releases_export_for_immediate_extend() -> None:
    """Snapshot must NOT leave a buffer export alive after returning.

    Without the del+release, the caller's next ``buffer.extend(...)`` would
    raise BufferError because bytearray cannot grow while exported.
    """
    sample_rate = 16000
    buf = bytearray(_audio_bytes(2.0, sample_rate=sample_rate))

    snapshot = FasterWhisperProvider._window_snapshot(buf, window_s=1, sample_rate=sample_rate)
    assert isinstance(snapshot, np.ndarray)
    assert snapshot.dtype == np.float32

    # The crucial assertion: extending after snapshot must not raise.
    buf.extend(b"\x00\x00\x00\x00" * 4096)  # 16 KB worth of float32 zeros
    assert len(buf) == 2 * sample_rate * 4 + 4096 * 4


# ── 3. Equivalence ─────────────────────────────────────────────────────


def test_window_snapshot_matches_legacy_path() -> None:
    """The new snapshot must be byte-identical to the old implementation."""
    sample_rate = 16000
    rng = np.random.default_rng(0)
    arr = rng.standard_normal(4 * sample_rate).astype(np.float32)  # 4 seconds of noise
    buf = bytearray(arr.tobytes())

    for window_s in (0, 1, 2, 8):
        snapshot = FasterWhisperProvider._window_snapshot(buf, window_s, sample_rate)

        # Old code: np.frombuffer(bytes(buf))[-window_s*sr:] (when window_s>0).
        old = np.frombuffer(bytes(buf), dtype=np.float32)
        if window_s > 0:
            window_samples = window_s * sample_rate
            if len(old) > window_samples:
                old = old[-window_samples:]

        np.testing.assert_array_equal(
            snapshot,
            old,
            err_msg=f"window_s={window_s}: snapshot differs from legacy path",
        )


def test_window_snapshot_when_buffer_shorter_than_window() -> None:
    """Buffer < window must return the entire buffer, not error."""
    buf = bytearray(_audio_bytes(0.5, sample_rate=16000))
    snapshot = FasterWhisperProvider._window_snapshot(buf, window_s=8, sample_rate=16000)
    expected = np.frombuffer(bytes(buf), dtype=np.float32)
    np.testing.assert_array_equal(snapshot, expected)
