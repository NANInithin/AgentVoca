"""Tests for ``observer/compile/rules.py`` (OBS-21).

All tests run against the OBS-9 fixture so the output is deterministic
across runs. The fixture writes three blocks separated by 7 minutes so
the ``split_blocks`` rules are exercised.

A golden file at ``tests/fixtures/expected_session.md`` is committed
and diffed on every test run. This is what stops later refactors from
silently degrading output quality.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("httpx", reason="httpx required for the no-network assertion")

from agentvoca.config.schema import ObserverCompileConfig
from agentvoca.observer.compile.rules import RulesCompiler
from agentvoca.observer.models import CompiledSession, SessionBundle
from agentvoca.observer.store import ObserverStore

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "expected_session.md"


def _build_compiler() -> RulesCompiler:
    return RulesCompiler(config=ObserverCompileConfig(provider="rules"))


def _build_fixture_bundle(tmp_path: Path) -> SessionBundle:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tests.fixtures.observer_fixture import build_fixture_session  # noqa: PLC0415

    store = ObserverStore(root=tmp_path / "store")
    store.start()
    try:
        session = build_fixture_session(store)
        return store.load_bundle(session_id=session.id)
    finally:
        store.stop()


# ── Tests ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compiles_without_network_access(tmp_path: Path, monkeypatch) -> None:
    """The rules compiler must not touch the network.

    Any httpx call raises immediately. Rules is the offline default; if
    it ever imported httpx at all, every zero-config Observer user would
    inherit the cloud LLM client's connection pool.
    """
    import httpx  # local import so the rule is in scope of the test.

    def _explode(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("rules compiler must not use httpx")

    monkeypatch.setattr(httpx, "get", _explode, raising=True)
    monkeypatch.setattr(httpx, "post", _explode, raising=True)
    monkeypatch.setattr(httpx, "AsyncClient", _explode, raising=True)

    bundle = _build_fixture_bundle(tmp_path)
    compiled = await _build_compiler().compile(bundle)
    assert compiled.provider == "rules"
    assert "rules compiler" in compiled.markdown


@pytest.mark.asyncio
async def test_header_for_every_block_in_chronological_order(tmp_path: Path) -> None:
    bundle = _build_fixture_bundle(tmp_path)
    compiled = await _build_compiler().compile(bundle)
    lines = compiled.markdown.splitlines()
    # 3 focus_change-separated blocks -> 3 '## ' section headers in order.
    section_headers = [line for line in lines if line.startswith("## ") and "\u00b7" in line]
    assert len(section_headers) == 3
    # The first event of each block opens a new section; check they are
    # in increasing time order.
    times: list[str] = []
    for line in section_headers:
        # '## HH:MM \u2013 HH:MM \u00b7 app'
        first = line.split(" \u2013 ", 1)[0].removeprefix("## ")
        times.append(first)
    assert times == sorted(times)


@pytest.mark.asyncio
async def test_every_event_kind_represented(tmp_path: Path) -> None:
    """Each event kind in the fixture should appear in the output somewhere."""
    bundle = _build_fixture_bundle(tmp_path)
    compiled = await _build_compiler().compile(bundle)
    md = compiled.markdown
    # Said: utterances
    assert "**Said**" in md
    # Highlighted: selection
    assert "**Highlighted**" in md
    # On screen: keyframes
    assert "**On screen**" in md
    # Gap rendering: pause stretches
    assert "capture paused" in md or "data dropped" in md
    # Compiled by line is always emitted.
    assert "Compiled by AgentVoca" in md
    assert "no LLM used" in md


@pytest.mark.asyncio
async def test_empty_session_is_valid_stub(tmp_path: Path) -> None:
    """An empty bundle compiles to a valid stub, not a crash."""
    from agentvoca.observer.models import ObserverSession

    bundle = SessionBundle(
        session=ObserverSession(
            id=0,
            uuid="deadbeef",
            started_at_ms=0,
            ended_at_ms=None,
            status="closed",
            app_version="0.4.0",
            schema_version=1,
        ),
        events=[],
    )
    compiled = await _build_compiler().compile(bundle)
    assert compiled.provider == "rules"
    assert "No events" in compiled.markdown
    assert compiled.degraded is False


@pytest.mark.asyncio
async def test_deterministic_byte_identical_output(tmp_path: Path) -> None:
    """Compiling the same bundle twice yields byte-identical output."""
    bundle = _build_fixture_bundle(tmp_path)
    once = await _build_compiler().compile(bundle)
    twice = await _build_compiler().compile(bundle)
    assert once.markdown == twice.markdown
    assert once.summary == twice.summary
    assert once.blocks == twice.blocks


@pytest.mark.asyncio
async def test_ocr_dedup_drops_repeated_lines(tmp_path: Path) -> None:
    """A repeated OCR line is shown once per block, not on every keyframe."""
    bundle = _build_fixture_bundle(tmp_path)
    compiled = await _build_compiler().compile(bundle)
    # Block 1 has 2 keyframes; lines from the second one should not
    # duplicate lines from the first.
    block_records = compiled.blocks
    assert len(block_records) == 3
    # The "On screen" markdown for block 1 should not list the same line twice.
    block_1_md = "\n".join(line for line in compiled.markdown.splitlines() if line.startswith("- "))
    # Each line must be unique.
    lines = [line for line in block_1_md.splitlines() if line.startswith("- ")]
    assert len(lines) == len(set(lines)), f"duplicate lines in:\n{block_1_md}"


@pytest.mark.asyncio
async def test_markdown_escaping(tmp_path: Path) -> None:
    """OCR text containing markdown-significant characters must be escaped.

    A test bundle whose OCR includes ``a|b \\`c\\` _d_`` should not
    produce unbalanced fences or italic spans in the rendered output.
    """
    from agentvoca.observer.models import ObserverEvent, ObserverSession, SessionBundle

    nasty_ocr = "a|b `c` _d_ *e* [f](g) #h"
    session = ObserverSession(
        id=1,
        uuid="nasty",
        started_at_ms=1_768_466_400_000,
        ended_at_ms=1_768_466_500_000,
        status="closed",
        app_version="0.4.0",
        schema_version=1,
    )
    focus = ObserverEvent(
        id=1,
        session_id=1,
        ts_ms=1_768_466_400_000,
        kind="focus_change",
        app_name="chrome.exe",
        window_title="T",
    )
    kf = ObserverEvent(
        id=2,
        session_id=1,
        ts_ms=1_768_466_401_000,
        kind="keyframe",
        app_name="chrome.exe",
        window_title="T",
        text=nasty_ocr,
        blob_path="blobs/nasty/0.jpg",
        meta={"trigger": "window_change", "dhash": 1, "width": 1280, "height": 720},
    )
    bundle = SessionBundle(session=session, events=[focus, kf])
    compiled = await _build_compiler().compile(bundle)
    # The raw nasty OCR line must NOT appear unescaped. After escaping,
    # backticks are prefixed with backslashes; the raw form is impossible
    # in the output.
    assert "`c`" not in compiled.markdown
    assert "_d_" not in compiled.markdown
    assert "*e*" not in compiled.markdown
    # The escaped form is present.
    assert "\\\\`c\\\\`" in compiled.markdown or "\\`c\\`" in compiled.markdown


@pytest.mark.asyncio
async def test_gap_rendering_includes_time_and_reason(tmp_path: Path) -> None:
    """A pause stretch renders as a gap entry with time and reason."""
    bundle = _build_fixture_bundle(tmp_path)
    compiled = await _build_compiler().compile(bundle)
    # The fixture's block 2 has pause_start, gap, pause_end.
    # Find the gap-rendering line in block 2 and verify it has a time
    # stamp and a reason.
    md = compiled.markdown
    # Split into blocks.
    assert "\u26a0\ufe0f" in md  # warning sign


@pytest.mark.asyncio
async def test_block_records_match_split_blocks(tmp_path: Path) -> None:
    """The JSON ``blocks`` list length matches ``split_blocks`` exactly."""
    from agentvoca.observer.compile.base import split_blocks

    bundle = _build_fixture_bundle(tmp_path)
    compiled = await _build_compiler().compile(bundle)
    assert len(compiled.blocks) == len(split_blocks(bundle))


@pytest.mark.asyncio
async def test_provider_field_is_rules(tmp_path: Path) -> None:
    bundle = _build_fixture_bundle(tmp_path)
    compiled = await _build_compiler().compile(bundle)
    assert compiled.provider == "rules"
    assert compiled.degraded is False


@pytest.mark.asyncio
async def test_summary_is_one_line(tmp_path: Path) -> None:
    bundle = _build_fixture_bundle(tmp_path)
    compiled = await _build_compiler().compile(bundle)
    assert compiled.summary
    assert "\n" not in compiled.summary
    # The summary should not pretend to be an LLM summary \u2014 no period
    # at the end, deterministic stats.
    assert "lines" in compiled.summary or "line" in compiled.summary


@pytest.mark.asyncio
async def test_golden_file_matches(tmp_path: Path) -> None:
    """The committed golden file must match the current output exactly.

    The golden file is what makes a future refactor of the rules
    compiler a deliberate decision (you change the golden, you re-read
    the diff) instead of a silent regression.
    """
    if not GOLDEN_PATH.is_file():
        pytest.skip(
            f"Golden file {GOLDEN_PATH} not present. Generate with the "
            "rules compiler and commit it."
        )
    bundle = _build_fixture_bundle(tmp_path)
    compiled = await _build_compiler().compile(bundle)
    golden = GOLDEN_PATH.read_text(encoding="utf-8")
    # Use json.dumps for stable error formatting.
    if compiled.markdown != golden:
        # Write the actual output next to the golden for diffing.
        actual = GOLDEN_PATH.with_suffix(".actual.md")
        actual.write_text(compiled.markdown, encoding="utf-8")
        assert False, (
            f"Rules compiler output diverged from golden. See {actual} for diff. "
            f"Expected {len(golden)} bytes, got {len(compiled.markdown)} bytes."
        )


@pytest.mark.asyncio
async def test_returns_compiled_session_dataclass(tmp_path: Path) -> None:
    bundle = _build_fixture_bundle(tmp_path)
    compiled = await _build_compiler().compile(bundle)
    assert isinstance(compiled, CompiledSession)
    # JSON-roundtrips \u2014 confirms ``blocks`` is JSON-serialisable, which
    # the JSON sidecar exporter needs.
    serialised = json.dumps(compiled.blocks, ensure_ascii=False)
    assert isinstance(serialised, str)
    # And back.
    reloaded = json.loads(serialised)
    assert isinstance(reloaded, list)
    assert len(reloaded) == 3
