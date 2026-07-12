"""Tests for R10: parallel multi-screenshot vision extraction.

Verifies that ``_apply_vision`` runs per-shot ``extract()`` calls
concurrently (asyncio.gather), preserving per-shot error isolation and
input ordering for the anchor splicer.
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator

import pytest

from agentvoca.asr.base import ASRProvider
from agentvoca.cleanup.base import CleanupProvider
from agentvoca.config.schema import (
    ASRConfig,
    CleanupConfig,
    FullConfig,
    InsertionConfig,
    VisionConfig,
)
from agentvoca.core.event_bus import EventBus
from agentvoca.core.orchestrator import Orchestrator
from agentvoca.core.registry import ProviderRegistry
from agentvoca.core.types import (
    InsertionResult,
    TranscriptSegment,
)
from agentvoca.insertion.base import InsertionStrategy
from agentvoca.utils.errors import VisionError
from agentvoca.vision.base import VisionProvider

# ── Mocks ───────────────────────────────────────────────────────────


class _ASR(ASRProvider):
    def __init__(self, config: ASRConfig) -> None:
        self.config = config

    def get_name(self) -> str:
        return "asr"

    def is_available(self) -> bool:
        return True

    async def transcribe_audio(self, audio_bytes, sample_rate, context=None) -> TranscriptSegment:
        return TranscriptSegment(text="describe shot one and shot two", is_final=True)

    async def stream_transcribe(
        self, audio_stream, sample_rate, context=None
    ) -> AsyncIterator[TranscriptSegment]:
        yield TranscriptSegment(text="describe", is_final=True)


class _Cleanup(CleanupProvider):
    def __init__(self, config: CleanupConfig) -> None:
        self.config = config

    def get_name(self) -> str:
        return "cleanup"

    def is_available(self) -> bool:
        return True

    async def rewrite(self, transcript, context=None) -> str:
        return transcript


class _Insert(InsertionStrategy):
    def __init__(self, config: InsertionConfig) -> None:
        self.config = config

    def get_name(self) -> str:
        return "insert"

    def is_available(self) -> bool:
        return True

    async def insert(self, text):
        return InsertionResult(success=True, method_used="keyboard")

    async def undo_last(self) -> bool:
        return True


class _SleepyVision(VisionProvider):
    """Vision provider that sleeps per call, recording its call order."""

    def __init__(
        self, config: VisionConfig, sleep_s: float, fail_indices: set | None = None
    ) -> None:
        self.config = config
        self.sleep_s = sleep_s
        self.fail_indices = fail_indices or set()
        self.call_count = 0
        self.start_times: list[float] = []
        self.end_times: list[float] = []
        self.texts: list[str] = []

    def get_name(self) -> str:
        return "sleepy_vision"

    def is_available(self) -> bool:
        return True

    async def extract(self, image_data, instruction, context=None, mime_type="image/png") -> str:
        idx = self.call_count
        self.call_count += 1
        if idx in self.fail_indices:
            raise VisionError(f"simulated failure for shot {idx}")
        t0 = time.perf_counter()
        await asyncio.sleep(self.sleep_s)
        t1 = time.perf_counter()
        self.start_times.append(t0)
        self.end_times.append(t1)
        text = f"shot-{idx}"
        self.texts.append(text)
        return text


# ── Helpers ─────────────────────────────────────────────────────────


def _build_config() -> FullConfig:
    return FullConfig(
        asr=ASRConfig(provider="asr"),
        cleanup=CleanupConfig(provider="cleanup"),
        insertion=InsertionConfig(strategy="keyboard"),
        vision=VisionConfig(provider="sleepy_vision"),
    )


def _build_registry(vision_provider: VisionProvider) -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register_asr("asr", _ASR)
    reg.register_cleanup("cleanup", _Cleanup)
    reg.register_insertion("insert", _Insert)
    reg.register_vision("sleepy_vision", type(vision_provider))
    return reg


# ── Tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_runs_concurrently():
    """3 shots × 300ms must finish in well under 900ms (parallel)."""
    vision = _SleepyVision(VisionConfig(provider="sleepy_vision"), sleep_s=0.30)
    registry = _build_registry(vision)

    orch = Orchestrator(
        config=_build_config(),
        registry=registry,
        event_bus=EventBus(),
        screenshot_capturer=_FakeCapturer(shots=[b"\x89PNG"] * 3),
    )

    # Seed three pending captures directly on the orchestrator's vision
    # pipeline state. _apply_vision drains them and runs the parallel
    # gather.
    orch._vision_enabled = True
    orch._vision_provider = vision
    orch._anchor_splicer = _PassThroughSplicer()

    t0 = time.perf_counter()
    text, had_vision = await orch._apply_vision("describe")
    elapsed = time.perf_counter() - t0

    # Serial would be >= 900 ms; parallel should be < 600 ms with margin.
    assert had_vision is True
    assert elapsed < 0.6, f"elapsed {elapsed:.2f}s suggests serial execution"


@pytest.mark.asyncio
async def test_one_shot_failure_does_not_block_others():
    """If one of three shots raises VisionError, the other two still
    splice — and in original order."""
    vision = _SleepyVision(
        VisionConfig(provider="sleepy_vision"),
        sleep_s=0.05,
        fail_indices={1},  # middle shot fails
    )
    registry = _build_registry(vision)

    splicer = _PassThroughSplicer()
    orch = Orchestrator(
        config=_build_config(),
        registry=registry,
        event_bus=EventBus(),
        screenshot_capturer=_FakeCapturer(shots=[b"\x89PNG"] * 3),
    )
    orch._vision_enabled = True
    orch._vision_provider = vision
    orch._anchor_splicer = splicer

    text, had_vision = await orch._apply_vision("describe")

    # Two successful extractions (indices 0 and 2), in input order.
    assert vision.texts == ["shot-0", "shot-2"]
    assert had_vision is True
    # The splicer received them in input order.
    assert splicer.extractions == ["shot-0", "shot-2"]


@pytest.mark.asyncio
async def test_zero_extractions_returns_text_unchanged():
    """When no extraction yields text, (text, False) is returned."""
    vision = _SleepyVision(
        VisionConfig(provider="sleepy_vision"),
        sleep_s=0.01,
    )
    vision.extract = _empty_extract  # type: ignore[assignment]
    registry = _build_registry(vision)

    orch = Orchestrator(
        config=_build_config(),
        registry=registry,
        event_bus=EventBus(),
        screenshot_capturer=_FakeCapturer(shots=[b"\x89PNG"] * 2),
    )
    orch._vision_enabled = True
    orch._vision_provider = vision
    orch._anchor_splicer = _PassThroughSplicer()

    text, had_vision = await orch._apply_vision("describe")
    assert had_vision is False
    assert text == "describe"


async def _empty_extract(self, *args, **kwargs) -> str:
    return ""


# ── Stubs for screenshot capturer & splicer ────────────────────────


class _FakeCapturer:
    def __init__(self, shots: list[bytes]) -> None:
        self._shots = shots
        self._pending = bool(shots)

    def has_pending(self) -> bool:
        return self._pending

    def wait_idle(self, _timeout: float) -> None:
        self._pending = False

    def drain(self) -> list[bytes]:
        self._pending = False
        return list(self._shots)


class _PassThroughSplicer:
    """Records extractions and returns the input text concatenated with
    extractions — sufficient for asserting the order/contents that
    ``_apply_vision`` hands the splicer."""

    def __init__(self) -> None:
        self.extractions: list[str] = []

    def splice(self, text: str, extractions: list[str]) -> tuple[str, int]:
        self.extractions = list(extractions)
        return text + " " + " ".join(extractions), len(extractions)
