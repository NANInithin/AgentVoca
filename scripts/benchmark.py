"""Pipeline latency benchmark harness (Phase E, PE-01).

Replays audio through the full orchestrator pipeline and records the per-stage
``TimingEvent`` durations the orchestrator already emits, plus an end-to-end
"recording-stopped -> text-inserted" wall-clock measurement.

Two modes:

* ``--mode mock`` (default): mock ASR / cleanup / insertion providers with a
  configurable simulated latency. No models, no GPU, fully deterministic. This
  exercises the *real* orchestration code path (state machine, event bus,
  vocab/snippet/command stages) while isolating it from model variance, so it
  is suitable for CI regression gating of orchestration overhead.

* ``--mode real``: real local ``faster_whisper`` + ``rules`` providers over WAV
  fixtures in ``tests/fixtures/audio/``. Requires the models to be present and
  is sensitive to hardware, so run it manually / nightly (CI has no GPU).

Output: a human-readable per-stage summary (mean / p50 / p95) and, with
``--json PATH``, a machine-readable JSON report.

Exit code: non-zero if any *enforced* budget is exceeded. Budgets are enforced
automatically in ``mock`` mode (use ``--no-enforce`` to disable) and only when
``--enforce`` is passed in ``real`` mode. This lets CI run::

    uv run python scripts/benchmark.py --mode mock

and fail the build on an orchestration-overhead regression.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import AsyncIterator, Optional

# Make ``agentvoca`` importable when run as a plain script (not via the
# installed console entry point).
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agentvoca.asr.base import ASRProvider  # noqa: E402
from agentvoca.cleanup.base import CleanupProvider  # noqa: E402
from agentvoca.config.schema import FullConfig  # noqa: E402
from agentvoca.core.event_bus import EventBus  # noqa: E402
from agentvoca.core.events import (  # noqa: E402
    InsertionCompleteEvent,
    RecordingStoppedEvent,
    TimingEvent,
)
from agentvoca.core.orchestrator import Orchestrator  # noqa: E402
from agentvoca.core.registry import ProviderRegistry  # noqa: E402
from agentvoca.core.types import ASRContext, InsertionResult, TranscriptSegment  # noqa: E402

# ── Budgets ─────────────────────────────────────────────────────────────
# Mock-mode budgets are p95 ceilings on *orchestration overhead* (simulated
# provider latency is ~0). They are intentionally generous: their job is to
# catch gross regressions (an accidental blocking call, an O(n^2) loop), not
# to micro-benchmark. Tune only with a deliberate reason.
MOCK_BUDGETS_MS: dict[str, float] = {
    "asr": 75.0,
    "cleanup": 75.0,
    "insertion": 75.0,
    "end_to_end": 250.0,
}


# ── Mock providers ──────────────────────────────────────────────────────


class _MockASR(ASRProvider):
    """ASR provider that returns fixed text after an optional simulated delay."""

    def __init__(self, latency_s: float = 0.0, text: str = "hello world") -> None:
        self._latency_s = latency_s
        self._text = text

    def get_name(self) -> str:
        return "mock_asr"

    def is_available(self) -> bool:
        return True

    async def warm_up(self) -> None:
        return None

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> TranscriptSegment:
        if self._latency_s:
            await asyncio.sleep(self._latency_s)
        return TranscriptSegment(text=self._text, is_final=True)

    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> AsyncIterator[TranscriptSegment]:
        async for _ in audio_stream:
            pass
        yield TranscriptSegment(text=self._text, is_final=True)


class _MockCleanup(CleanupProvider):
    """Cleanup provider that returns the transcript unchanged after a delay."""

    def __init__(self, latency_s: float = 0.0) -> None:
        self._latency_s = latency_s

    def get_name(self) -> str:
        return "mock_cleanup"

    def is_available(self) -> bool:
        return True

    async def warm_up(self) -> None:
        return None

    async def rewrite(self, transcript: str, context=None) -> str:
        if self._latency_s:
            await asyncio.sleep(self._latency_s)
        return transcript


class _MockInsertion:
    """Insertion strategy that always succeeds instantly."""

    def __init__(self, latency_s: float = 0.0) -> None:
        self._latency_s = latency_s

    def get_name(self) -> str:
        return "mock_insertion"

    def is_available(self) -> bool:
        return True

    async def insert(self, text: str) -> InsertionResult:
        if self._latency_s:
            await asyncio.sleep(self._latency_s)
        return InsertionResult(success=True, method_used="keyboard")

    async def undo_last(self) -> bool:
        return True


# ── Harness ─────────────────────────────────────────────────────────────


def _build_mock_config() -> FullConfig:
    """A minimal valid config for the mock pipeline (all v2 features off)."""
    return FullConfig.model_validate({"asr": {"provider": "mock_asr"}})


def _make_orchestrator(
    config: FullConfig,
    event_bus: EventBus,
    asr: ASRProvider,
    cleanup: CleanupProvider,
    insertion: object,
) -> Orchestrator:
    """Wire an orchestrator with pre-built provider instances.

    A registry with builtins disabled is used and its factory methods are
    overridden, so no heavy real provider (faster-whisper, etc.) is imported.
    """
    registry = ProviderRegistry(register_builtins=False)
    registry.get_asr = lambda cfg: asr  # type: ignore[assignment]
    registry.get_cleanup = lambda cfg: cleanup  # type: ignore[assignment]
    registry.get_insertion = lambda cfg: insertion  # type: ignore[assignment]
    return Orchestrator(config, registry, event_bus)


async def _run_iteration(
    orchestrator: Orchestrator,
    event_bus: EventBus,
    stage_samples: dict[str, list[float]],
    timeout_s: float = 10.0,
) -> None:
    """Drive one full dictation cycle and record stage + end-to-end timings."""
    done = asyncio.Event()
    collected: dict[str, int] = {}

    def on_timing(ev: TimingEvent) -> None:
        collected[ev.stage] = ev.duration_ms

    def on_complete(ev: InsertionCompleteEvent) -> None:
        if ev.success:
            done.set()

    event_bus.subscribe(TimingEvent, on_timing)
    event_bus.subscribe(InsertionCompleteEvent, on_complete)
    try:
        t0 = time.perf_counter()
        event_bus.publish(
            RecordingStoppedEvent(audio_bytes=b"benchmark", duration_ms=1000, sample_rate=16000)
        )
        await asyncio.wait_for(done.wait(), timeout=timeout_s)
        end_to_end_ms = (time.perf_counter() - t0) * 1000.0
    finally:
        event_bus.unsubscribe(TimingEvent, on_timing)
        event_bus.unsubscribe(InsertionCompleteEvent, on_complete)

    for stage, dur in collected.items():
        stage_samples.setdefault(stage, []).append(float(dur))
    stage_samples.setdefault("end_to_end", []).append(end_to_end_ms)


async def _run_mock(iterations: int, warmup: int, latency_ms: float) -> dict[str, list[float]]:
    """Run the mock pipeline ``iterations`` times, discarding ``warmup`` runs."""
    config = _build_mock_config()
    event_bus = EventBus()
    latency_s = latency_ms / 1000.0
    asr = _MockASR(latency_s=latency_s)
    cleanup = _MockCleanup(latency_s=latency_s)
    insertion = _MockInsertion(latency_s=latency_s)

    orchestrator = _make_orchestrator(config, event_bus, asr, cleanup, insertion)
    await orchestrator.start()

    stage_samples: dict[str, list[float]] = {}
    total = iterations + warmup
    for i in range(total):
        samples = stage_samples if i >= warmup else {}
        await _run_iteration(orchestrator, event_bus, samples)
    await orchestrator.stop()
    return stage_samples


async def _run_real(iterations: int, warmup: int) -> dict[str, list[float]]:
    """Run the real local pipeline (faster-whisper + rules) over WAV fixtures."""
    import wave

    fixtures_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "audio"
    wavs = sorted(fixtures_dir.glob("*.wav"))
    if not wavs:
        raise SystemExit(f"No WAV fixtures found in {fixtures_dir} for --mode real.")

    import numpy as np

    from agentvoca.asr.faster_whisper import FasterWhisperProvider
    from agentvoca.cleanup.rules import RulesCleanupProvider

    config = FullConfig.model_validate(
        {
            "asr": {"provider": "faster_whisper", "model": "base.en"},
            "cleanup": {"provider": "rules", "style": "standard"},
        }
    )
    event_bus = EventBus()
    asr = FasterWhisperProvider(config.asr)
    cleanup = RulesCleanupProvider(config.cleanup)
    insertion = _MockInsertion()  # never actually type during a benchmark

    orchestrator = _make_orchestrator(config, event_bus, asr, cleanup, insertion)
    await orchestrator.start()
    await asr.warm_up()

    def _load_pcm(path: Path) -> bytes:
        with wave.open(str(path), "rb") as wf:
            frames = wf.readframes(wf.getnframes())
        pcm16 = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        return pcm16.tobytes()

    audio = [_load_pcm(p) for p in wavs]

    stage_samples: dict[str, list[float]] = {}
    total = iterations + warmup
    for i in range(total):
        pcm = audio[i % len(audio)]
        samples = stage_samples if i >= warmup else {}

        done = asyncio.Event()
        collected: dict[str, int] = {}

        def on_timing(ev: TimingEvent, _c=collected) -> None:
            _c[ev.stage] = ev.duration_ms

        def on_complete(ev: InsertionCompleteEvent, _d=done) -> None:
            if ev.success:
                _d.set()

        event_bus.subscribe(TimingEvent, on_timing)
        event_bus.subscribe(InsertionCompleteEvent, on_complete)
        try:
            t0 = time.perf_counter()
            event_bus.publish(
                RecordingStoppedEvent(audio_bytes=pcm, duration_ms=2000, sample_rate=16000)
            )
            await asyncio.wait_for(done.wait(), timeout=120.0)
            e2e = (time.perf_counter() - t0) * 1000.0
        finally:
            event_bus.unsubscribe(TimingEvent, on_timing)
            event_bus.unsubscribe(InsertionCompleteEvent, on_complete)

        for stage, dur in collected.items():
            samples.setdefault(stage, []).append(float(dur))
        samples.setdefault("end_to_end", []).append(e2e)

    await orchestrator.stop()
    return stage_samples


# ── Reporting ───────────────────────────────────────────────────────────


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (pct in 0..100)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, round((pct / 100.0) * len(ordered) + 0.5) - 1))
    return ordered[k]


def _summarize(stage_samples: dict[str, list[float]]) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for stage, values in stage_samples.items():
        if not values:
            continue
        summary[stage] = {
            "count": len(values),
            "mean_ms": round(statistics.mean(values), 2),
            "p50_ms": round(_percentile(values, 50), 2),
            "p95_ms": round(_percentile(values, 95), 2),
            "max_ms": round(max(values), 2),
        }
    return summary


def _print_summary(
    summary: dict[str, dict[str, float]], budgets: dict[str, float], enforce: bool
) -> list[str]:
    """Print a table and return the list of budget breaches (stage names)."""
    order = ["asr", "cleanup", "insertion", "clipboard_fallback", "end_to_end"]
    stages = [s for s in order if s in summary] + [s for s in summary if s not in order]

    print(f"\n{'stage':<20}{'mean':>10}{'p50':>10}{'p95':>10}{'max':>10}{'budget':>10}  status")
    print("-" * 82)
    breaches: list[str] = []
    for stage in stages:
        m = summary[stage]
        budget = budgets.get(stage)
        status = ""
        if budget is not None:
            over = m["p95_ms"] > budget
            status = "OVER" if over else "ok"
            if over:
                breaches.append(stage)
        budget_str = f"{budget:.0f}" if budget is not None else "-"
        print(
            f"{stage:<20}{m['mean_ms']:>10.2f}{m['p50_ms']:>10.2f}"
            f"{m['p95_ms']:>10.2f}{m['max_ms']:>10.2f}{budget_str:>10}  {status}"
        )
    print("-" * 82)
    if enforce and breaches:
        print(f"\nFAIL: {len(breaches)} stage(s) exceeded budget (p95): {', '.join(breaches)}")
    elif enforce:
        print("\nPASS: all enforced stage budgets met.")
    return breaches


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AgentVoca pipeline latency benchmark.")
    parser.add_argument("--mode", choices=["mock", "real"], default="mock")
    parser.add_argument("--iterations", type=int, default=30, help="Measured iterations.")
    parser.add_argument("--warmup", type=int, default=3, help="Discarded warm-up iterations.")
    parser.add_argument(
        "--latency-ms",
        type=float,
        default=0.0,
        help="Simulated per-stage provider latency (mock mode only).",
    )
    parser.add_argument("--json", type=str, default=None, help="Write a JSON report to this path.")
    parser.add_argument(
        "--enforce",
        dest="enforce",
        action="store_true",
        default=None,
        help="Fail (non-zero exit) on budget breach. Default: on for mock mode.",
    )
    parser.add_argument(
        "--no-enforce",
        dest="enforce",
        action="store_false",
        help="Never fail on budget breach (report only).",
    )
    args = parser.parse_args(argv)

    enforce = args.enforce
    if enforce is None:
        enforce = args.mode == "mock"

    if args.mode == "mock":
        stage_samples = asyncio.run(_run_mock(args.iterations, args.warmup, args.latency_ms))
        budgets = MOCK_BUDGETS_MS
    else:
        stage_samples = asyncio.run(_run_real(args.iterations, args.warmup))
        budgets = {}  # real-mode budgets are hardware-bound; report only

    summary = _summarize(stage_samples)
    print(f"AgentVoca benchmark - mode={args.mode}, iterations={args.iterations}")
    breaches = _print_summary(summary, budgets, enforce)

    if args.json:
        report = {
            "mode": args.mode,
            "iterations": args.iterations,
            "budgets_ms": budgets,
            "summary": summary,
            "breaches": breaches,
        }
        Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nJSON report written to {args.json}")

    return 1 if (enforce and breaches) else 0


if __name__ == "__main__":
    raise SystemExit(main())
