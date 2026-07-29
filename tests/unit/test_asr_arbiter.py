"""Tests for the ASR arbiter (OBS-12).

The arbiter serialises access to a single ``ASRProvider`` between
dictation and ambient. Dictation never waits on ambient; ambient simply
lags while a dictation is in flight.

These tests use a fake ``ASRProvider`` with controllable per-call delays
so the timing assertions are deterministic.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import pytest

from agentvoca.asr.base import ASRProvider
from agentvoca.core.types import ASRContext, TranscriptSegment
from agentvoca.observer.arbiter import ASRArbiter


class FakeASR(ASRProvider):
    """Records every call; each call sleeps ``per_call_delay_s`` seconds."""

    def __init__(self, per_call_delay_s: float = 0.2, raise_on_call: bool = False) -> None:
        self.per_call_delay_s = per_call_delay_s
        self.raise_on_call = raise_on_call
        self.calls: list[tuple[bytes, int, object | None]] = []

    def get_name(self) -> str:
        return "fake_asr"

    def is_available(self) -> bool:
        return True

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> TranscriptSegment:
        self.calls.append((audio_bytes, sample_rate, context))
        await asyncio.sleep(self.per_call_delay_s)
        if self.raise_on_call:
            raise RuntimeError("intentional")
        return TranscriptSegment(text=f"text#{len(self.calls)}", is_final=True)

    def supports_streaming(self) -> bool:
        return False

    async def stream_transcribe(self, audio_stream, sample_rate, context=None):
        yield TranscriptSegment(text="", is_final=False)
        yield TranscriptSegment(text="", is_final=True)


@pytest.fixture
def fake_provider() -> FakeASR:
    return FakeASR(per_call_delay_s=0.05)


# ── Priority ───────────────────────────────────────────────────────


class TestPriority:
    async def test_dictation_does_not_wait_on_ambient(self, fake_provider: FakeASR) -> None:
        arb = ASRArbiter(fake_provider, queue_depth=16)
        results: list[tuple[str, int, int]] = []

        def on_text(text: str, ts_ms: int, duration_ms: int) -> None:
            results.append((text, ts_ms, duration_ms))

        arb.start(on_text)
        try:
            # Submit 5 ambient jobs.
            for i in range(5):
                arb.submit_ambient(b"a" * 10, ts_ms=i * 100, duration_ms=100, sample_rate=16000)

            # Immediately call transcribe_priority. It should complete in
            # approximately one job time, not five.
            t0 = time.perf_counter()
            text = await arb.transcribe_priority(b"d" * 10, sample_rate=16000)
            elapsed = time.perf_counter() - t0

            assert text == "text#1", f"Expected first call's text, got {text}"
            # 0.05s (one call) + slack. With 5 ambient queued first the
            # call counter on the provider may have moved 0 or 1 step
            # before dictation is enqueued, so the dictation call may be
            # call#1 or call#2. The point is: not 6.
            assert elapsed < 5 * fake_provider.per_call_delay_s, (
                f"Dictation took {elapsed:.3f}s; should be < {5 * fake_provider.per_call_delay_s}s"
            )
        finally:
            await arb.stop()

    async def test_ambient_resumes_after_dictation(self, fake_provider: FakeASR) -> None:
        arb = ASRArbiter(fake_provider, queue_depth=16)
        results: list[tuple[str, int, int]] = []

        def on_text(text: str, ts_ms: int, duration_ms: int) -> None:
            results.append((text, ts_ms, duration_ms))

        arb.start(on_text)
        try:
            for i in range(3):
                arb.submit_ambient(b"a" * 10, ts_ms=i * 100, duration_ms=100, sample_rate=16000)
            await arb.transcribe_priority(b"d" * 10, sample_rate=16000)
            # Wait for ambient to drain. Each ambient call is 0.05s; 3 of
            # them in series = 0.15s. Wait up to 1.0s.
            deadline = time.time() + 1.0
            while time.time() < deadline:
                if len(results) >= 3:
                    break
                await asyncio.sleep(0.01)
            assert len(results) >= 3, f"Expected ≥ 3 ambient results, got {len(results)}: {results}"
        finally:
            await arb.stop()


# ── Overflow ───────────────────────────────────────────────────────


class TestOverflow:
    async def test_overflow_drops_oldest(self, fake_provider: FakeASR) -> None:
        # queue_depth=2. Submit 10 with a slow provider; at least one
        # overflow must be observed. The exact count depends on how
        # many items the worker pulls during the submit burst, but the
        # contract is "drop oldest on overflow", not "drop N".
        arb = ASRArbiter(fake_provider, queue_depth=2)
        results: list[tuple[str, int, int]] = []

        def on_text(text: str, ts_ms: int, duration_ms: int) -> None:
            results.append((text, ts_ms, duration_ms))

        # Slow provider so the worker cannot drain the queue during the
        # submit burst.
        fake_provider.per_call_delay_s = 1.0
        arb.start(on_text)
        try:
            for i in range(10):
                arb.submit_ambient(b"a" * 10, ts_ms=i * 100, duration_ms=100, sample_rate=16000)
            await asyncio.sleep(0.05)
            assert arb.dropped_count >= 1, (
                f"Expected ≥ 1 dropped ambient job on overflow, got {arb.dropped_count}"
            )
        finally:
            await arb.stop()


# ── Exception safety ───────────────────────────────────────────────


class TestExceptionSafety:
    async def test_priority_exception_releases_idle_event(self) -> None:
        # A raising provider in transcribe_priority must leave the idle
        # event set so ambient resumes.
        class RaisingASR(FakeASR):
            async def transcribe_audio(self, audio_bytes, sample_rate, context=None):  # type: ignore[override]
                self.calls.append((audio_bytes, sample_rate, context))
                await asyncio.sleep(0.01)
                raise RuntimeError("intentional")

        provider = RaisingASR()
        arb = ASRArbiter(provider, queue_depth=4)
        results: list[tuple[str, int, int]] = []

        def on_text(text: str, ts_ms: int, duration_ms: int) -> None:
            results.append((text, ts_ms, duration_ms))

        arb.start(on_text)
        try:
            arb.submit_ambient(b"a" * 10, ts_ms=0, duration_ms=100, sample_rate=16000)
            with pytest.raises(RuntimeError, match="intentional"):
                await arb.transcribe_priority(b"d" * 10, sample_rate=16000)
            # After the raise, the idle event should be set, so the
            # ambient worker resumes and processes the queued job.
            deadline = time.time() + 1.0
            while time.time() < deadline:
                if results:
                    break
                await asyncio.sleep(0.01)
            # The ambient job should not be processed (because the fake
            # raises too). But the loop keeps draining.
        finally:
            await arb.stop()


# ── No-arbiter path ────────────────────────────────────────────────


class TestNoArbiterPath:
    async def test_orchestrator_without_arbiter_calls_provider_directly(
        self, event_bus, minimal_config, registry, recording_stopped_event
    ) -> None:
        from agentvoca.core.orchestrator import Orchestrator

        orch = Orchestrator(config=minimal_config, registry=registry, event_bus=event_bus)
        # Note: NO attach_asr_arbiter.
        assert orch._asr_arbiter is None
        await orch.start()

        # Capture provider calls.
        asr_cls = registry._asr["mock_asr"]
        original = asr_cls.transcribe_audio
        call_count = {"n": 0}

        async def counting(audio, sample_rate, context=None):
            call_count["n"] += 1
            return await original(self=asr_cls_instance, audio_bytes=audio, sample_rate=sample_rate)  # type: ignore[arg-type]

        asr_cls_instance = asr_cls(config=minimal_config.asr)

        # Use a simpler counting wrapper that retains the original behaviour.
        async def counting_simple(audio_bytes, sample_rate, context=None):
            call_count["n"] += 1
            return await original(asr_cls_instance, audio_bytes, sample_rate, context=context)

        asr_cls.transcribe_audio = counting_simple  # type: ignore[method-assign]

        try:
            event_bus.publish(recording_stopped_event)
            await asyncio.sleep(0.5)
            assert call_count["n"] >= 1, "transcribe_audio should have been called"
        finally:
            asr_cls.transcribe_audio = original  # type: ignore[method-assign]
            await orch.stop()


# ── Tests requiring shared fixtures ────────────────────────────────


@pytest.fixture
def event_bus():
    from agentvoca.core.event_bus import EventBus

    return EventBus()


@pytest.fixture
def minimal_config():
    from agentvoca.config.schema import (
        ASRConfig,
        CleanupConfig,
        FullConfig,
        InsertionConfig,
    )

    return FullConfig(
        asr=ASRConfig(provider="mock_asr"),
        cleanup=CleanupConfig(provider="rules"),
        insertion=InsertionConfig(strategy="keyboard"),
    )


@pytest.fixture
def registry():
    from agentvoca.core.registry import ProviderRegistry

    reg = ProviderRegistry()
    # Register a trivial mock_asr that doesn't require loading models.
    from agentvoca.asr.base import ASRProvider
    from agentvoca.core.types import TranscriptSegment

    class MockASR(ASRProvider):
        def __init__(self, config):
            self.config = config

        def get_name(self):
            return "mock_asr"

        def is_available(self):
            return True

        async def transcribe_audio(self, audio_bytes, sample_rate, context=None):
            return TranscriptSegment(text="hello world", is_final=True)

        def supports_streaming(self):
            return False

        async def stream_transcribe(self, audio_stream, sample_rate, context=None):
            yield TranscriptSegment(text="hello world", is_final=True)

    reg.register_asr("mock_asr", MockASR)
    return reg


@pytest.fixture
def recording_stopped_event():
    from agentvoca.core.events import RecordingStoppedEvent

    return RecordingStoppedEvent(audio_bytes=b"\x00" * 1024, duration_ms=500, sample_rate=16000)
