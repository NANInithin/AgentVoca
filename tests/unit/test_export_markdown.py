"""Tests for ``observer/export/markdown.py`` (OBS-24, markdown exporter)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agentvoca.config.schema import ObserverCompileConfig
from agentvoca.observer.compile.rules import RulesCompiler
from agentvoca.observer.export.markdown import MarkdownExporter
from agentvoca.observer.models import CompiledSession, ObserverSession, SessionBundle
from agentvoca.observer.store import ObserverStore


async def _build(tmp_path: Path) -> tuple[SessionBundle, CompiledSession]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.fixtures.observer_fixture import build_fixture_session  # noqa: PLC0415

    store = ObserverStore(root=tmp_path / "store")
    store.start()
    try:
        session = build_fixture_session(store)
        bundle = store.load_bundle(session_id=session.id)
    finally:
        store.stop()
    compiled = await RulesCompiler(ObserverCompileConfig(provider="rules")).compile(bundle)
    return bundle, compiled


@pytest.mark.asyncio
async def test_markdown_writes_to_expected_path(tmp_path: Path) -> None:
    bundle, compiled = await _build(tmp_path)
    out_dir = tmp_path / "exports"
    exporter = MarkdownExporter(bundle, out_dir)
    result = await exporter.export(compiled)
    expected = out_dir / bundle.session.uuid / "session.md"
    assert Path(result) == expected
    assert expected.is_file()
    # Content round-trips.
    on_disk = expected.read_text(encoding="utf-8")
    assert on_disk == compiled.markdown


@pytest.mark.asyncio
async def test_markdown_creates_parent_dirs(tmp_path: Path) -> None:
    bundle, compiled = await _build(tmp_path)
    out_dir = tmp_path / "exports" / "nested" / "deeper"
    exporter = MarkdownExporter(bundle, out_dir)
    result = await exporter.export(compiled)
    assert Path(result).is_file()


@pytest.mark.asyncio
async def test_markdown_atomic_no_tmp_remains(tmp_path: Path) -> None:
    """A successful export leaves no ``.tmp`` file behind."""
    bundle, compiled = await _build(tmp_path)
    out_dir = tmp_path / "exports"
    exporter = MarkdownExporter(bundle, out_dir)
    await exporter.export(compiled)
    target = out_dir / bundle.session.uuid / "session.md"
    assert not target.with_name(target.name + ".tmp").exists()


@pytest.mark.asyncio
async def test_markdown_overwrites_existing(tmp_path: Path) -> None:
    """A re-export overwrites the previous file atomically."""
    bundle, compiled = await _build(tmp_path)
    out_dir = tmp_path / "exports"
    exporter = MarkdownExporter(bundle, out_dir)
    first = await exporter.export(compiled)
    second = await exporter.export(compiled)
    assert first == second
    assert Path(second).read_text(encoding="utf-8") == compiled.markdown


@pytest.mark.asyncio
async def test_markdown_non_ascii_preserved(tmp_path: Path) -> None:
    """Non-ASCII characters survive the round-trip."""
    bundle = SessionBundle(
        session=ObserverSession(
            id=1,
            uuid="u",
            started_at_ms=1_768_466_400_000,
            ended_at_ms=1_768_466_500_000,
            status="closed",
            app_version="0.4.0",
            schema_version=1,
        ),
        events=[],
    )
    exporter = MarkdownExporter(bundle, tmp_path / "exports")
    # Build a CompiledSession with non-ASCII content.
    compiled = CompiledSession(
        markdown="# \u4f60\u597d \U0001f44b\n\nCJK \u4e2d\u6587 + emoji",
        summary="summary with \u00e9 and \U0001f31f",
        blocks=[],
        provider="rules",
        degraded=False,
    )
    path = await exporter.export(compiled)
    on_disk = Path(path).read_text(encoding="utf-8")
    assert "\u4f60\u597d" in on_disk
    assert "\U0001f44b" in on_disk
    assert "\u4e2d\u6587" in on_disk
