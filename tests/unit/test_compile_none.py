"""Tests for the ``none`` session compiler and registry wiring (OBS-23)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from agentvoca.config.schema import ObserverCompileConfig
from agentvoca.core.registry import ProviderRegistry
from agentvoca.observer.compile.none import NoneCompiler
from agentvoca.observer.models import CompiledSession, ObserverSession, SessionBundle


def _build_bundle(tmp_path: Path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from agentvoca.observer.store import ObserverStore  # noqa: PLC0415
    from tests.fixtures.observer_fixture import build_fixture_session  # noqa: PLC0415

    store = ObserverStore(root=tmp_path / "store")
    store.start()
    try:
        session = build_fixture_session(store)
        return store.load_bundle(session_id=session.id)
    finally:
        store.stop()


@pytest.mark.asyncio
async def test_none_compiler_one_line_per_event(tmp_path: Path) -> None:
    bundle = _build_bundle(tmp_path)
    compiled = await NoneCompiler(ObserverCompileConfig(provider="none")).compile(bundle)
    assert compiled.provider == "none"
    assert compiled.degraded is False
    assert compiled.summary == ""
    # Header + 3 sections of events. The fixture writes
    # 1 focus + 3 utterances + 2 keyframes + 1 selection = 7 in block 1;
    # similar for blocks 2 and 3 with extras in block 2.
    md_lines = compiled.markdown.splitlines()
    non_empty = [line for line in md_lines if line]
    # At least: title + N event lines.
    assert len(non_empty) >= 8
    # Every non-header line is a single event.
    for line in non_empty[2:]:
        assert "[" in line and "]" in line


@pytest.mark.asyncio
async def test_none_compiler_empty_bundle(tmp_path: Path) -> None:
    bundle = SessionBundle(
        session=ObserverSession(
            id=0,
            uuid="x",
            started_at_ms=0,
            ended_at_ms=None,
            status="closed",
            app_version="0.4.0",
            schema_version=1,
        ),
        events=[],
    )
    compiled = await NoneCompiler(ObserverCompileConfig(provider="none")).compile(bundle)
    assert compiled.provider == "none"
    assert compiled.degraded is False
    # No blocks for an empty bundle.
    assert compiled.blocks == []


def test_all_three_compilers_registered() -> None:
    """The registry's built-ins include all three Observer compilers."""
    reg = ProviderRegistry()
    names = set(reg.list_compiler())
    assert names == {"rules", "openai_compatible", "none"}


def test_get_compiler_returns_constructed_instance() -> None:
    """``get_compiler`` returns a constructed instance of the registered class."""
    reg = ProviderRegistry()
    for name in ("rules", "openai_compatible", "none"):
        instance = reg.get_compiler(ObserverCompileConfig(provider=name))
        # The base ABC is the only common ancestor we can assert on
        # without coupling tests to each provider's class identity.
        assert hasattr(instance, "compile")
        assert hasattr(instance, "shutdown")


def test_get_compiler_unknown_raises() -> None:
    from agentvoca.utils.errors import ProviderNotFoundError

    reg = ProviderRegistry()
    with pytest.raises(ProviderNotFoundError):
        reg.get_compiler(ObserverCompileConfig(provider="nonexistent"))


@pytest.mark.asyncio
async def test_none_compiler_returns_compiled_session(tmp_path: Path) -> None:
    """Return type is a ``CompiledSession`` dataclass."""
    bundle = _build_bundle(tmp_path)
    compiled = await NoneCompiler(ObserverCompileConfig(provider="none")).compile(bundle)
    assert isinstance(compiled, CompiledSession)
