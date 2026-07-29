"""Integration tests for the Observer compile-on-stop and recovery flow (OBS-28).

Drives the controller + a real fixture session through the full
loop. Uses the rules compiler (no network) and the
``ExporterCoordinator`` so the test exercises the same code path the
app uses.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="PySide6 (Qt) not available")

from agentvoca.config.schema import ObserverCompileConfig  # noqa: E402
from agentvoca.core.event_bus import EventBus  # noqa: E402
from agentvoca.observer.compile.rules import RulesCompiler  # noqa: E402
from agentvoca.observer.controller import ObserverController  # noqa: E402
from agentvoca.observer.export.coordinator import ExporterCoordinator  # noqa: E402
from agentvoca.observer.store import ObserverStore  # noqa: E402


def _make_full_config(compile_cfg: ObserverCompileConfig) -> object:
    """Build a minimal ``FullConfig`` carrying only the observer.compile block.

    The controller does not validate the rest of the config against
    the schema in the tests we run, so a lightweight stand-in is
    enough.
    """
    from agentvoca.config.schema import (
        ASRConfig,
        FullConfig,
        ObserverConfig,
        ObserverStorageConfig,
    )

    return FullConfig(
        asr=ASRConfig(provider="faster_whisper", model="base"),
        observer=ObserverConfig(
            enabled=True,
            storage=ObserverStorageConfig(),
            compile=compile_cfg,
        ),
    )


class _NoopIndicator:
    """Stand-in for ``ObserverIndicator`` that has no Qt side effects."""

    def shutdown(self) -> None:  # noqa: D401
        return None


def _attach(
    controller: ObserverController,
    store: ObserverStore,
    cfg: ObserverCompileConfig,
    output_dir: Path,
) -> None:
    compiler = RulesCompiler(cfg)
    coordinator = ExporterCoordinator(store=store, formats=list(cfg.formats), out_dir=output_dir)
    controller.attach_surface(compiler, [coordinator], _NoopIndicator())


@pytest.mark.asyncio
async def test_fixture_session_compile_emits_outputs(tmp_path: Path) -> None:
    """Fixture session -> compile -> session.md and session.json exist."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.fixtures.observer_fixture import build_fixture_session  # noqa: PLC0415

    output_dir = tmp_path / "exports"
    store = ObserverStore(root=tmp_path / "store")
    store.start()
    try:
        bus = EventBus()
        bus.set_loop(asyncio.get_running_loop())
        cfg = ObserverCompileConfig(provider="rules", formats=["markdown", "json"])
        controller = ObserverController(
            config=_make_full_config(cfg),
            event_bus=bus,
            store=store,
            loop=asyncio.get_running_loop(),
        )
        _attach(controller, store, cfg, output_dir)

        session = build_fixture_session(store)
        # The controller's _run_compile is a coroutine. Awaiting it
        # runs the compile on this loop, so the test can assert
        # after it finishes.
        await controller._run_compile(session_id=session.id)

        md = output_dir / session.uuid / "session.md"
        js = output_dir / session.uuid / "session.json"
        assert md.is_file(), f"Missing {md}"
        assert js.is_file(), f"Missing {js}"
        assert md.stat().st_size > 0
        assert js.stat().st_size > 0
        rows = store.list_sessions(limit=10)
        rows_by_id = {r.id: r for r in rows}
        assert rows_by_id[session.id].status == "compiled"
    finally:
        store.stop()


@pytest.mark.asyncio
async def test_compile_publishes_event(tmp_path: Path) -> None:
    from agentvoca.core.events import ObserverCompiledEvent  # noqa: E402

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.fixtures.observer_fixture import build_fixture_session  # noqa: PLC0415

    bus = EventBus()
    bus.set_loop(asyncio.get_running_loop())
    captured: list[object] = []

    def _on(event: object) -> None:
        captured.append(event)

    bus.subscribe(ObserverCompiledEvent, _on)

    output_dir = tmp_path / "exports"
    store = ObserverStore(root=tmp_path / "store")
    store.start()
    try:
        cfg = ObserverCompileConfig(provider="rules", formats=["markdown", "json"])
        controller = ObserverController(
            config=_make_full_config(cfg),
            event_bus=bus,
            store=store,
            loop=asyncio.get_running_loop(),
        )
        _attach(controller, store, cfg, output_dir)

        session = build_fixture_session(store)
        await controller._run_compile(session_id=session.id)

        assert len(captured) == 1
        event = captured[0]
        assert event.markdown_path
        assert event.json_path
    finally:
        store.stop()


@pytest.mark.asyncio
async def test_formats_markdown_only_writes_no_json(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.fixtures.observer_fixture import build_fixture_session  # noqa: PLC0415

    store = ObserverStore(root=tmp_path / "store")
    store.start()
    try:
        bus = EventBus()
        bus.set_loop(asyncio.get_running_loop())
        cfg = ObserverCompileConfig(provider="rules", formats=["markdown"])
        controller = ObserverController(
            config=_make_full_config(cfg),
            event_bus=bus,
            store=store,
            loop=asyncio.get_running_loop(),
        )
        output_dir = tmp_path / "exports"
        _attach(controller, store, cfg, output_dir)
        session = build_fixture_session(store)
        await controller._run_compile(session_id=session.id)
        md = output_dir / session.uuid / "session.md"
        js = output_dir / session.uuid / "session.json"
        assert md.is_file()
        assert not js.exists()
    finally:
        store.stop()


@pytest.mark.asyncio
async def test_raising_compiler_leaves_session_closed(tmp_path: Path) -> None:
    """A compiler that raises does not crash and does not mark 'compiled'."""
    from agentvoca.observer.compile.base import SessionCompiler  # noqa: E402
    from agentvoca.observer.models import SessionBundle  # noqa: E402

    class _BoomCompiler(SessionCompiler):
        async def compile(self, bundle: SessionBundle) -> object:  # type: ignore[override]
            raise RuntimeError("boom")

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.fixtures.observer_fixture import build_fixture_session  # noqa: PLC0415

    store = ObserverStore(root=tmp_path / "store")
    store.start()
    try:
        bus = EventBus()
        bus.set_loop(asyncio.get_running_loop())
        cfg = ObserverCompileConfig(provider="rules", formats=["markdown", "json"])
        controller = ObserverController(
            config=_make_full_config(cfg),
            event_bus=bus,
            store=store,
            loop=asyncio.get_running_loop(),
        )
        # No exporters (the boom never reaches them). Empty list.
        controller.attach_surface(_BoomCompiler(cfg), [], _NoopIndicator())
        session = build_fixture_session(store)
        # ``_run_compile`` catches the exception internally and
        # publishes a degraded event; it never raises.
        await controller._run_compile(session_id=session.id)
        # Session should still be 'closed', not 'compiled'.
        rows = store.list_sessions(limit=10)
        rows_by_id = {r.id: r for r in rows}
        assert rows_by_id[session.id].status == "closed"
    finally:
        store.stop()


def test_recover_sessions_finds_open_session(tmp_path: Path) -> None:
    """``recover_sessions`` returns sessions left 'open' by a prior process."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    store = ObserverStore(root=tmp_path / "store")
    store.start()
    try:
        # The fixture always closes the session, so to simulate a
        # crash-recovery scenario we open a fresh session and leave
        # it open.
        fresh = store.open_session(app_version="0.4.0")
        bus = EventBus()
        controller = ObserverController(
            config=_make_full_config(ObserverCompileConfig()),
            event_bus=bus,
            store=store,
            loop=asyncio.new_event_loop(),
        )
        recoverable = controller.recover_sessions()
        ids = {s.id for s in recoverable}
        assert fresh.id in ids
    finally:
        store.stop()


def test_purge_session_removes_everything(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.fixtures.observer_fixture import build_fixture_session  # noqa: PLC0415

    store = ObserverStore(root=tmp_path / "store")
    store.start()
    try:
        session = build_fixture_session(store)
        # Blob files exist for this session.
        assert any((store.blobs_dir / session.uuid).iterdir())
        store.purge_session(session.id)
        # Session is gone, blobs are gone.
        assert not (store.blobs_dir / session.uuid).exists()
        rows = store.list_sessions(limit=10)
        assert session.id not in {r.id for r in rows}
    finally:
        store.stop()
