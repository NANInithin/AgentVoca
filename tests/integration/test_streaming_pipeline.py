"""Integration tests for the streaming dictation pipeline.

Tests cover:
- Mock streaming ASR provider yields partials + final.
- Orchestrator consumes partials and produces PartialTranscriptEvent.
- Final segment proceeds through vocab → cleanup → insertion.
- v1 batch path works when streaming is disabled.
- Streaming enabled but no partials produced still works.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

import pytest

from agentvoca.asr.base import ASRProvider
from agentvoca.cleanup.base import CleanupProvider
from agentvoca.config.schema import ASRConfig, CleanupConfig, FullConfig, InsertionConfig
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import (
    AudioChunkEvent,
    InsertionCompleteEvent,
    PartialTranscriptEvent,
    RecordingStoppedEvent,
    TranscriptEvent,
)
from agentvoca.core.orchestrator import Orchestrator
from agentvoca.core.registry import ProviderRegistry
from agentvoca.core.types import ASRContext, CleanupContext, InsertionResult, TranscriptSegment
from agentvoca.insertion.base import InsertionStrategy

# ── Mock Providers ──────────────────────────────────────────────────


class MockStreamingASR(ASRProvider):
    """Mock ASR that yields partials and a final segment."""

    def __init__(self, config: ASRConfig) -> None:
        self.config = config
        self.available = True

    def get_name(self) -> str:
        return "mock_streaming_asr"

    def is_available(self) -> bool:
        return self.available

    def supports_streaming(self) -> bool:
        return True

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> TranscriptSegment:
        return TranscriptSegment(text="batch fallback transcript", is_final=True)

    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> AsyncIterator[TranscriptSegment]:
        """Yield 3 partials then a final, simulating a streaming ASR."""
        # Simulate processing delay
        partials = [
            "hello",
            "hello world",
            "hello world this",
        ]
        for partial in partials:
            await asyncio.sleep(0.01)
            yield TranscriptSegment(text=partial, is_final=False)

        await asyncio.sleep(0.01)
        yield TranscriptSegment(text="hello world this is a test", is_final=True)


class MockNonStreamingASR(ASRProvider):
    """Mock ASR that does NOT support streaming (v1 behavior)."""

    def __init__(self, config: ASRConfig) -> None:
        self.config = config
        self.available = True

    def get_name(self) -> str:
        return "mock_non_streaming_asr"

    def is_available(self) -> bool:
        return self.available

    def supports_streaming(self) -> bool:
        return False

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> TranscriptSegment:
        return TranscriptSegment(text="non-streaming transcript", is_final=True)

    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> AsyncIterator[TranscriptSegment]:
        buffer = b""
        async for chunk in audio_stream:
            buffer += chunk
        yield TranscriptSegment(text="non-streaming transcript", is_final=True)


class MockCleanup(CleanupProvider):
    """Simple mock cleanup that uppercases text."""

    def __init__(self, config: CleanupConfig) -> None:
        self.config = config
        self.available = True

    def get_name(self) -> str:
        return "mock_cleanup"

    def is_available(self) -> bool:
        return self.available

    async def rewrite(
        self,
        transcript: str,
        context: Optional[CleanupContext] = None,
    ) -> str:
        return transcript.upper()


class MockInsertion(InsertionStrategy):
    """Mock insertion that always succeeds."""

    def __init__(self, config: InsertionConfig) -> None:
        self.config = config
        self.insert_count = 0

    def get_name(self) -> str:
        return "mock_insert"

    def is_available(self) -> bool:
        return True

    async def insert(self, text: str) -> InsertionResult:
        self.insert_count += 1
        return InsertionResult(success=True, method_used="keyboard")

    async def undo_last(self) -> bool:
        return True


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def streaming_config() -> FullConfig:
    return FullConfig(
        asr=ASRConfig(provider="mock_streaming_asr", streaming=True),
        cleanup=CleanupConfig(provider="mock_cleanup"),
        insertion=InsertionConfig(strategy="keyboard"),
    )


@pytest.fixture
def non_streaming_config() -> FullConfig:
    return FullConfig(
        asr=ASRConfig(provider="mock_non_streaming_asr", streaming=False),
        cleanup=CleanupConfig(provider="mock_cleanup"),
        insertion=InsertionConfig(strategy="keyboard"),
    )


@pytest.fixture
def streaming_registry() -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register_asr("mock_streaming_asr", MockStreamingASR)
    reg.register_asr("mock_non_streaming_asr", MockNonStreamingASR)
    reg.register_cleanup("mock_cleanup", MockCleanup)
    reg.register_insertion("keyboard", MockInsertion)
    return reg


# ── Event Collector ─────────────────────────────────────────────────


class EventCollector:
    def __init__(self, bus: EventBus, event_type: type) -> None:
        self.events: list = []
        bus.subscribe(event_type, self._collect)

    def _collect(self, event: object) -> None:
        self.events.append(event)

    def clear(self) -> None:
        self.events.clear()


# ── Tests ───────────────────────────────────────────────────────────


class TestStreamingPipeline:
    """Tests for the streaming pipeline path."""

    async def test_streaming_provider_supports_streaming(
        self, streaming_config: FullConfig, streaming_registry: ProviderRegistry
    ) -> None:
        asr = streaming_registry.get_asr(streaming_config.asr)
        assert asr.supports_streaming() is True

    async def test_non_streaming_provider_supports_streaming_false(
        self, non_streaming_config: FullConfig, streaming_registry: ProviderRegistry
    ) -> None:
        asr = streaming_registry.get_asr(non_streaming_config.asr)
        assert asr.supports_streaming() is False

    async def test_streaming_yields_partials_then_final(
        self, streaming_config: FullConfig, streaming_registry: ProviderRegistry
    ) -> None:
        """Verify the mock streaming provider yields partials + final."""
        asr = streaming_registry.get_asr(streaming_config.asr)

        async def audio_stream() -> AsyncIterator[bytes]:
            yield b"\x00\x00\x00\x00" * 1600  # 100 ms
            yield b"\x00\x00\x00\x00" * 1600
            yield b"\x00\x00\x00\x00" * 1600

        segments = []
        async for segment in asr.stream_transcribe(audio_stream(), sample_rate=16000):
            segments.append(segment)

        assert len(segments) >= 4  # 3 partials + 1 final
        assert segments[-1].is_final is True
        assert segments[-1].text == "hello world this is a test"
        assert any(not s.is_final for s in segments)

    async def test_streaming_pipeline_emits_partials_and_final(
        self,
        streaming_config: FullConfig,
        streaming_registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        """The full pipeline with a streaming ASR should emit partials
        via PartialTranscriptEvent and then proceed through the pipeline."""
        orch = Orchestrator(
            config=streaming_config,
            registry=streaming_registry,
            event_bus=event_bus,
        )
        await orch.start()

        partial_collector = EventCollector(event_bus, PartialTranscriptEvent)
        transcript_collector = EventCollector(event_bus, TranscriptEvent)

        # Simulate audio chunks arriving during recording
        for _ in range(5):
            event_bus.publish(
                AudioChunkEvent(
                    data=b"\x00\x00\x00\x00" * 1600,
                    sample_rate=16000,
                    timestamp_ms=0,
                    is_flush=False,
                )
            )
            await asyncio.sleep(0.01)

        # Signal end of recording via AudioChunkEvent flush
        event_bus.publish(
            AudioChunkEvent(
                data=b"",
                sample_rate=16000,
                timestamp_ms=0,
                is_flush=True,
            )
        )

        # Also publish RecordingStoppedEvent to trigger the pipeline
        event_bus.publish(
            RecordingStoppedEvent(
                audio_bytes=b"\x00" * 64000,
                duration_ms=1000,
                sample_rate=16000,
            )
        )

        # Wait for pipeline to complete
        await asyncio.sleep(0.5)

        # Should have received partials
        assert len(partial_collector.events) > 0, (
            f"Expected partials, got {len(partial_collector.events)}"
        )
        assert any("hello" in e.text for e in partial_collector.events)

        # Should have received the final transcript
        assert len(transcript_collector.events) >= 1
        final_transcript = transcript_collector.events[-1]
        assert final_transcript.is_final is True

        await orch.stop()

    async def test_streaming_pipeline_completes_to_idle(
        self,
        streaming_config: FullConfig,
        streaming_registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        """The pipeline should complete and return to idle after streaming."""
        orch = Orchestrator(
            config=streaming_config,
            registry=streaming_registry,
            event_bus=event_bus,
        )
        await orch.start()

        insert_collector = EventCollector(event_bus, InsertionCompleteEvent)

        for _ in range(3):
            event_bus.publish(
                AudioChunkEvent(
                    data=b"\x00\x00\x00\x00" * 1600,
                    sample_rate=16000,
                    timestamp_ms=0,
                    is_flush=False,
                )
            )
            await asyncio.sleep(0.01)

        event_bus.publish(
            AudioChunkEvent(
                data=b"",
                sample_rate=16000,
                timestamp_ms=0,
                is_flush=True,
            )
        )

        event_bus.publish(
            RecordingStoppedEvent(
                audio_bytes=b"\x00" * 64000,
                duration_ms=1000,
                sample_rate=16000,
            )
        )

        await asyncio.sleep(1.0)

        # Should have completed insertion
        assert len(insert_collector.events) >= 1
        assert insert_collector.events[-1].success is True
        assert orch.get_state() == "idle"

        await orch.stop()

    async def test_v1_batch_path_still_works_without_streaming(
        self,
        non_streaming_config: FullConfig,
        streaming_registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        """When streaming is disabled, the v1 batch path should be used."""
        orch = Orchestrator(
            config=non_streaming_config,
            registry=streaming_registry,
            event_bus=event_bus,
        )
        await orch.start()

        transcript_collector = EventCollector(event_bus, TranscriptEvent)
        partial_collector = EventCollector(event_bus, PartialTranscriptEvent)

        # Publish recording stopped without any audio chunks
        event_bus.publish(
            RecordingStoppedEvent(
                audio_bytes=b"\x00" * 64000,
                duration_ms=1000,
                sample_rate=16000,
            )
        )

        await asyncio.sleep(0.3)

        # Should have gotten a transcript via the v1 batch path
        assert len(transcript_collector.events) >= 1
        assert transcript_collector.events[-1].text == "non-streaming transcript"
        # Should NOT have gotten any partials
        assert len(partial_collector.events) == 0

        await orch.stop()

    async def test_streaming_with_no_partials_still_works(
        self, streaming_registry: ProviderRegistry, event_bus: EventBus
    ) -> None:
        """If the ASR supports streaming but produces no partials,
        the pipeline should still work using the v1 fallback."""

        class NoPartialASR(MockStreamingASR):
            async def stream_transcribe(
                self,
                audio_stream: AsyncIterator[bytes],
                sample_rate: int,
                context: Optional[ASRContext] = None,
            ) -> AsyncIterator[TranscriptSegment]:
                # Buffer all and yield only a final (like v1)
                async for _ in audio_stream:
                    pass
                yield TranscriptSegment(text="no partials transcript", is_final=True)

        config = FullConfig(
            asr=ASRConfig(provider="mock_streaming_asr", streaming=True),
            cleanup=CleanupConfig(provider="mock_cleanup"),
            insertion=InsertionConfig(strategy="keyboard"),
        )
        streaming_registry.register_asr("mock_streaming_asr", NoPartialASR)

        orch = Orchestrator(
            config=config,
            registry=streaming_registry,
            event_bus=event_bus,
        )
        await orch.start()

        transcript_collector = EventCollector(event_bus, TranscriptEvent)
        partial_collector = EventCollector(event_bus, PartialTranscriptEvent)

        # Signal end of streaming first
        event_bus.publish(
            AudioChunkEvent(
                data=b"",
                sample_rate=16000,
                timestamp_ms=0,
                is_flush=True,
            )
        )

        event_bus.publish(
            RecordingStoppedEvent(
                audio_bytes=b"\x00" * 64000,
                duration_ms=1000,
                sample_rate=16000,
            )
        )

        await asyncio.sleep(0.5)

        # Should have a final transcript but no partials
        assert len(transcript_collector.events) >= 1
        assert len(partial_collector.events) == 0

        await orch.stop()
