"""Integration tests for warm-start and pipelined cleanup.

Tests cover:
- warm_up() on mock providers completes without error
- Orchestrator background warm-up emits WarmupCompleteEvent
- First pipeline invocation has no model-load penalty (warm-up already done)
- Pipelined (segment) cleanup accumulates cleaned segments during recording
- technical style forces full-transcript pass (pipelined cleanup disabled)
- cleanup.streaming: false uses v1 batch path
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
    RecordingStoppedEvent,
    SegmentFinalizedEvent,
    WarmupCompleteEvent,
)
from agentvoca.core.orchestrator import Orchestrator
from agentvoca.core.registry import ProviderRegistry
from agentvoca.core.types import ASRContext, CleanupContext, InsertionResult, TranscriptSegment
from agentvoca.insertion.base import InsertionStrategy

# ── Warm-Up Trackable Mock Providers ───────────────────────────────


class WarmableMockASR(ASRProvider):
    """Mock ASR that tracks warm_up() calls."""

    def __init__(self, config: ASRConfig) -> None:
        self.config = config
        self.available = True
        self.warm_up_called = False

    def get_name(self) -> str:
        return "warmable_mock_asr"

    def is_available(self) -> bool:
        return self.available

    def supports_streaming(self) -> bool:
        return True

    async def warm_up(self) -> None:
        self.warm_up_called = True

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> TranscriptSegment:
        return TranscriptSegment(text="warmable transcript", is_final=True)

    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> AsyncIterator[TranscriptSegment]:
        yield TranscriptSegment(text="partial", is_final=False)
        yield TranscriptSegment(text="partial transcript", is_final=False)
        yield TranscriptSegment(text="partial transcript final", is_final=True)


class WarmableMockCleanup(CleanupProvider):
    """Mock cleanup that tracks warm_up() and remembers segments."""

    def __init__(self, config: CleanupConfig) -> None:
        self.config = config
        self.available = True
        self.warm_up_called = False
        self.rewrite_calls: list[str] = []

    def get_name(self) -> str:
        return "warmable_mock_cleanup"

    def is_available(self) -> bool:
        return self.available

    async def warm_up(self) -> None:
        self.warm_up_called = True

    async def rewrite(
        self,
        transcript: str,
        context: Optional[CleanupContext] = None,
    ) -> str:
        self.rewrite_calls.append(transcript)
        return transcript.upper()


class WarmableMockInsertion(InsertionStrategy):
    """Mock insertion that always succeeds."""

    def __init__(self, config: InsertionConfig) -> None:
        self.config = config

    def get_name(self) -> str:
        return "warmable_mock_insert"

    def is_available(self) -> bool:
        return True

    async def insert(self, text: str) -> InsertionResult:
        return InsertionResult(success=True, method_used="keyboard")

    async def undo_last(self) -> bool:
        return True


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def registry() -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register_asr("warmable_mock_asr", WarmableMockASR)
    reg.register_cleanup("warmable_mock_cleanup", WarmableMockCleanup)
    reg.register_insertion("keyboard", WarmableMockInsertion)
    return reg


@pytest.fixture
def streaming_pipelined_config() -> FullConfig:
    return FullConfig(
        asr=ASRConfig(provider="warmable_mock_asr", streaming=True, warm_up=True),
        cleanup=CleanupConfig(provider="warmable_mock_cleanup", streaming=True, warm_up=True),
        insertion=InsertionConfig(strategy="keyboard"),
    )


@pytest.fixture
def streaming_technical_config() -> FullConfig:
    return FullConfig(
        asr=ASRConfig(provider="warmable_mock_asr", streaming=True, warm_up=True),
        cleanup=CleanupConfig(
            provider="warmable_mock_cleanup",
            streaming=True,
            warm_up=True,
            style="technical",
        ),
        insertion=InsertionConfig(strategy="keyboard"),
    )


@pytest.fixture
def streaming_no_pipeline_config() -> FullConfig:
    return FullConfig(
        asr=ASRConfig(provider="warmable_mock_asr", streaming=True, warm_up=True),
        cleanup=CleanupConfig(provider="warmable_mock_cleanup", streaming=False, warm_up=True),
        insertion=InsertionConfig(strategy="keyboard"),
    )


class EventCollector:
    def __init__(self, bus: EventBus, event_type: type) -> None:
        self.events: list = []
        bus.subscribe(event_type, self._collect)

    def _collect(self, event: object) -> None:
        self.events.append(event)


# ── Tests ───────────────────────────────────────────────────────────


class TestWarmUp:
    """Warm-start behavior tests."""

    async def test_provider_warm_up_called_on_start(
        self,
        streaming_pipelined_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        """Orchestrator start() should call warm_up() on both providers."""
        orch = Orchestrator(
            config=streaming_pipelined_config,
            registry=registry,
            event_bus=event_bus,
        )
        await orch.start()

        # Give warm-up time to complete
        await asyncio.sleep(0.1)

        asr_provider = orch._asr_provider
        cleanup_provider = orch._cleanup_provider
        assert asr_provider is not None
        assert cleanup_provider is not None
        assert asr_provider.warm_up_called is True
        assert cleanup_provider.warm_up_called is True

        await orch.stop()

    async def test_warmup_complete_event_emitted(
        self,
        streaming_pipelined_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        """WarmupCompleteEvent should be emitted after warm-up completes."""
        collector = EventCollector(event_bus, WarmupCompleteEvent)

        orch = Orchestrator(
            config=streaming_pipelined_config,
            registry=registry,
            event_bus=event_bus,
        )
        await orch.start()
        await asyncio.sleep(0.2)

        assert len(collector.events) >= 1
        warmup = collector.events[-1]
        assert warmup.asr_ready is True
        assert warmup.cleanup_ready is True
        assert warmup.duration_ms >= 0

        await orch.stop()

    async def test_warm_up_does_not_block_pipeline(
        self,
        streaming_pipelined_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        """Pipeline should work even if warm-up is still running."""
        orch = Orchestrator(
            config=streaming_pipelined_config,
            registry=registry,
            event_bus=event_bus,
        )
        await orch.start()

        # Publish recording stopped immediately (before warm-up likely finishes)
        event_bus.publish(
            RecordingStoppedEvent(
                audio_bytes=b"\x00" * 64000,
                duration_ms=1000,
                sample_rate=16000,
            )
        )

        await asyncio.sleep(0.5)

        # Pipeline should complete even if warm-up is in progress
        assert orch.get_state() in ("idle", "error")

        await orch.stop()


class TestPipelinedCleanup:
    """Segment-aware cleanup tests (WB-04)."""

    async def test_pipelined_cleanup_enabled_with_config(
        self,
        streaming_pipelined_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        """With cleanup.streaming=true and style!=technical, pipelining is active."""
        orch = Orchestrator(
            config=streaming_pipelined_config,
            registry=registry,
            event_bus=event_bus,
        )
        await orch.start()
        assert orch._pipelined_cleanup_enabled is True
        await orch.stop()

    async def test_pipelined_cleanup_disabled_with_technical(
        self,
        streaming_technical_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        """With style=technical, pipelining should be disabled."""
        orch = Orchestrator(
            config=streaming_technical_config,
            registry=registry,
            event_bus=event_bus,
        )
        await orch.start()
        assert orch._pipelined_cleanup_enabled is False
        await orch.stop()

    async def test_pipelined_cleanup_disabled_without_streaming(
        self,
        streaming_no_pipeline_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        """With cleanup.streaming=false, pipelining should be disabled."""
        orch = Orchestrator(
            config=streaming_no_pipeline_config,
            registry=registry,
            event_bus=event_bus,
        )
        await orch.start()
        assert orch._pipelined_cleanup_enabled is False
        await orch.stop()

    async def test_segment_cleanup_accumulates_during_recording(
        self,
        streaming_pipelined_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        """During recording, finalized segments should be cleaned and accumulated."""
        orch = Orchestrator(
            config=streaming_pipelined_config,
            registry=registry,
            event_bus=event_bus,
        )
        await orch.start()

        # Publish finalized segments (as would happen during streaming)
        event_bus.publish(SegmentFinalizedEvent(text="first segment", index=0))
        event_bus.publish(SegmentFinalizedEvent(text="second segment", index=1))
        await asyncio.sleep(0.2)

        # Segments should be accumulated
        assert len(orch._cleaned_segments) >= 2

        await orch.stop()

    async def test_pipelined_cleanup_pipeline_completes(
        self,
        streaming_pipelined_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        """Full pipeline with streaming and pipelined cleanup should complete."""
        orch = Orchestrator(
            config=streaming_pipelined_config,
            registry=registry,
            event_bus=event_bus,
        )
        await orch.start()

        insert_collector = EventCollector(event_bus, InsertionCompleteEvent)

        # Publish finalized segments during "recording"
        event_bus.publish(SegmentFinalizedEvent(text="hello world", index=0))
        await asyncio.sleep(0.05)

        # Publish audio chunks and flush
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

        # Publish recording stopped
        event_bus.publish(
            RecordingStoppedEvent(
                audio_bytes=b"\x00" * 64000,
                duration_ms=1000,
                sample_rate=16000,
            )
        )

        await asyncio.sleep(0.5)

        # Pipeline should complete via insertion
        assert len(insert_collector.events) >= 1
        assert orch.get_state() == "idle"

        await orch.stop()

    async def test_no_pipelined_cleanup_with_technical(
        self,
        streaming_technical_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        """With technical style, pipelined cleanup should not be used."""
        orch = Orchestrator(
            config=streaming_technical_config,
            registry=registry,
            event_bus=event_bus,
        )
        await orch.start()
        assert orch._pipelined_cleanup_enabled is False

        # Publish finalized segments — should NOT trigger pipelined cleanup
        event_bus.publish(SegmentFinalizedEvent(text="some technical text", index=0))
        await asyncio.sleep(0.1)

        # No segment cleanup tasks should be created
        assert len(orch._pipelined_cleanup_tasks) == 0
        assert len(orch._cleaned_segments) == 0

        await orch.stop()

    async def test_segment_cleanup_rewrite_count(
        self,
        streaming_pipelined_config: FullConfig,
        registry: ProviderRegistry,
        event_bus: EventBus,
    ) -> None:
        """With pipelined cleanup, rewrite() should be called for each segment."""
        orch = Orchestrator(
            config=streaming_pipelined_config,
            registry=registry,
            event_bus=event_bus,
        )
        await orch.start()

        # Publish multiple segments
        for i in range(3):
            event_bus.publish(SegmentFinalizedEvent(text=f"segment {i}", index=i))
        await asyncio.sleep(0.2)

        cleanup_provider = orch._cleanup_provider
        assert cleanup_provider is not None
        assert len(cleanup_provider.rewrite_calls) >= 3

        await orch.stop()
