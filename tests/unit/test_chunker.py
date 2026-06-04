"""Unit tests for the AudioChunker.

Tests cover:
- Chunk emission cadence.
- Delta emission (only new audio since last emission, not rolling windows).
- Flush on stop.
- Buffer accumulation.
- Exact boundary cases (min/max chunk sizes).
"""

from __future__ import annotations

import asyncio

import pytest

from agentvoca.audio.chunker import AudioChunker
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import AudioChunkEvent


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def chunker(event_bus: EventBus) -> AudioChunker:
    return AudioChunker(
        event_bus=event_bus,
        chunk_ms=50,  # Fast for testing
        window_s=0,  # No rolling window for basic tests
        sample_rate=16000,
    )


class ChunkCollector:
    """Collects AudioChunkEvent emissions for assertions."""

    def __init__(self, bus: EventBus) -> None:
        self.chunks: list[AudioChunkEvent] = []
        bus.subscribe(AudioChunkEvent, self._collect)

    def _collect(self, event: AudioChunkEvent) -> None:
        self.chunks.append(event)

    @property
    def non_flush_chunks(self) -> list[AudioChunkEvent]:
        return [c for c in self.chunks if not c.is_flush]

    @property
    def flush_chunks(self) -> list[AudioChunkEvent]:
        return [c for c in self.chunks if c.is_flush]


class TestChunkerLifecycle:
    """Start/stop/reset behavior."""

    async def test_initial_state(self, chunker: AudioChunker) -> None:
        assert chunker.is_running is False

    async def test_start_sets_running(self, chunker: AudioChunker) -> None:
        chunker.start()
        assert chunker.is_running is True
        chunker.reset()

    async def test_stop_publishes_flush(self, chunker: AudioChunker, event_bus: EventBus) -> None:
        collector = ChunkCollector(event_bus)
        chunker.start()
        chunker.add_audio(b"\x00\x00\x00\x00" * 1600)
        await chunker.stop()

        assert len(collector.flush_chunks) >= 1
        flush = collector.flush_chunks[-1]
        assert flush.is_flush is True
        assert flush.sample_rate == 16000

    async def test_reset_clears_buffer(self, chunker: AudioChunker) -> None:
        chunker.start()
        chunker.add_audio(b"\x00" * 1000)
        chunker.reset()
        # After reset both the buffer and emit position are cleared.
        assert len(chunker._buffer) == 0
        assert chunker._last_emit_pos == 0

    async def test_stop_when_not_started(self, chunker: AudioChunker) -> None:
        await chunker.stop()


class TestChunkerAudioFeed:
    """Audio data feeding and buffer management."""

    async def test_add_audio_when_not_running(self, chunker: AudioChunker) -> None:
        chunker.add_audio(b"\x00" * 100)
        # Buffer stays empty when not running.
        assert len(chunker._buffer) == 0

    async def test_add_audio_accumulates(self, chunker: AudioChunker) -> None:
        chunker.start()
        chunker.add_audio(b"\x00" * 1000)
        chunker.add_audio(b"\x01" * 500)
        # Full buffer has all audio; delta starts at position 0.
        assert len(chunker._buffer) == 1500
        chunker.reset()

    async def test_add_audio_silence(self, chunker: AudioChunker) -> None:
        chunker.start()
        chunker.add_audio(b"")
        chunker.add_audio(b"\x00" * 100)
        assert len(chunker._buffer) == 100
        chunker.reset()


class TestChunkerDelta:
    """Delta emission — only new audio since the last emission."""

    async def test_delta_starts_empty(self, event_bus: EventBus) -> None:
        chunker = AudioChunker(event_bus=event_bus, chunk_ms=50, window_s=2, sample_rate=16000)
        chunker.start()
        # No audio added yet — delta should be empty.
        assert chunker._get_delta() == b""
        chunker.reset()

    async def test_delta_returns_all_audio_first_call(self, event_bus: EventBus) -> None:
        chunker = AudioChunker(event_bus=event_bus, chunk_ms=50, window_s=2, sample_rate=16000)
        chunker.start()
        audio = b"\x01\x02\x03\x04" * 100
        chunker.add_audio(audio)
        delta = chunker._get_delta()
        assert delta == audio
        chunker.reset()

    async def test_delta_only_new_audio_on_second_call(self, event_bus: EventBus) -> None:
        chunker = AudioChunker(event_bus=event_bus, chunk_ms=50, window_s=2, sample_rate=16000)
        chunker.start()
        first = b"\x01" * 200
        second = b"\x02" * 100
        chunker.add_audio(first)
        chunker._get_delta()  # consume first
        chunker.add_audio(second)
        delta2 = chunker._get_delta()
        assert delta2 == second  # only the new audio
        chunker.reset()

    async def test_delta_total_equals_full_buffer(self, event_bus: EventBus) -> None:
        """Sum of all deltas must equal the full recorded audio."""
        chunker = AudioChunker(event_bus=event_bus, chunk_ms=50, window_s=2, sample_rate=16000)
        chunker.start()
        audio = b"\xab\xcd\xef\x01" * 500
        chunker.add_audio(audio)
        d1 = chunker._get_delta()
        # Add more audio, then get next delta
        extra = b"\x10\x20" * 100
        chunker.add_audio(extra)
        d2 = chunker._get_delta()
        assert d1 + d2 == audio + extra
        chunker.reset()


class TestChunkerEmission:
    """Chunk emission correctness."""

    async def test_chunks_emitted_at_cadence(
        self, chunker: AudioChunker, event_bus: EventBus
    ) -> None:
        collector = ChunkCollector(event_bus)
        chunker.start()
        chunker.add_audio(b"\x00\x00\x00\x00" * 1600)
        await asyncio.sleep(0.12)
        chunker.add_audio(b"\x00\x00\x00\x00" * 1600)
        await asyncio.sleep(0.12)
        await chunker.stop()
        assert len(collector.non_flush_chunks) >= 1

    async def test_chunk_contains_audio_data(
        self, chunker: AudioChunker, event_bus: EventBus
    ) -> None:
        """Audio data should appear in either a non-flush chunk or the flush."""
        collector = ChunkCollector(event_bus)
        chunker.start()
        test_data = b"\x01\x02\x03\x04" * 400
        chunker.add_audio(test_data)
        # Wait longer than the chunk cadence to let the loop fire
        await asyncio.sleep(0.15)
        await chunker.stop()
        all_chunks = collector.chunks
        assert len(all_chunks) >= 1, "Expected at least one chunk event (flush)"
        assert any(len(c.data) > 0 for c in all_chunks), "All chunk events had empty data"

    async def test_flush_has_remaining_data(
        self, chunker: AudioChunker, event_bus: EventBus
    ) -> None:
        # With delta emission, flush carries only audio NOT yet sent in a
        # regular chunk.  We stop before any chunk fires (chunk_ms=50ms but
        # we call stop() immediately), so the flush carries the full audio.
        collector = ChunkCollector(event_bus)
        chunker.start()
        test_data = b"\x05" * 6400
        chunker.add_audio(test_data)
        await chunker.stop()
        flushes = collector.flush_chunks
        assert len(flushes) >= 1
        # Total data across all events must cover what we added.
        total = sum(len(c.data) for c in collector.chunks)
        assert total >= 6400


class TestChunkerEdgeCases:
    """Boundary and edge case behavior."""

    async def test_chunk_ms_clamping(self, event_bus: EventBus) -> None:
        chunker = AudioChunker(event_bus=event_bus, chunk_ms=10)
        assert chunker._chunk_ms == 100

        chunker2 = AudioChunker(event_bus=event_bus, chunk_ms=5000)
        assert chunker2._chunk_ms == 2000

    async def test_window_s_clamping(self, event_bus: EventBus) -> None:
        chunker = AudioChunker(event_bus=event_bus, window_s=-1)
        assert chunker._window_s == 0

    async def test_multiple_start_stop_cycles(
        self, chunker: AudioChunker, event_bus: EventBus
    ) -> None:
        collector = ChunkCollector(event_bus)
        chunker.start()
        chunker.add_audio(b"\x00" * 6400)
        await chunker.stop()
        assert len(collector.flush_chunks) >= 1

        chunker.start()
        chunker.add_audio(b"\x01" * 6400)
        await chunker.stop()
        assert len(collector.flush_chunks) >= 2

    async def test_concurrent_add_and_stop(
        self, chunker: AudioChunker, event_bus: EventBus
    ) -> None:
        chunker.start()

        async def add_continuously() -> None:
            for _ in range(100):
                chunker.add_audio(b"\x00" * 640)
                await asyncio.sleep(0.001)

        task = asyncio.create_task(add_continuously())
        await asyncio.sleep(0.01)
        await chunker.stop()
        await task
