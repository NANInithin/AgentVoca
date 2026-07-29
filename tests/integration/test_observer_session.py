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


@pytest.mark.asyncio
async def test_compile_exports_the_requested_session_not_the_newest(tmp_path: Path) -> None:
    """Regression: compiling session A must not export under session B's uuid.

    ``ExporterCoordinator`` used to locate the session itself with
    ``store.list_sessions(limit=1)``, which orders by ``started_at_ms
    DESC`` — i.e. the *newest* session. Whenever a new session was
    opened between closing A and compiling A (autosave, a quick
    restart, or the user simply starting the next session), the
    exporters were built for B and wrote A's compiled markdown into
    B's directory under B's uuid.

    The failure is silent: a file is produced, the event carries a
    path, and the suite stays green. Only the uuid and the block
    contents are wrong. This test pins the bundle-passing contract.
    """
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

        session_a = build_fixture_session(store)
        # A newer session exists and is still open — this is what the
        # old lookup would have picked up.
        session_b = store.open_session(app_version="0.4.0")
        store.flush(timeout=2.0)
        assert store.list_sessions(limit=1)[0].id == session_b.id, (
            "precondition: B must be the newest session for this test to be meaningful"
        )

        await controller._run_compile(session_id=session_a.id)

        # Outputs land under A, and B has no directory at all.
        assert (output_dir / session_a.uuid / "session.md").is_file()
        assert (output_dir / session_a.uuid / "session.json").is_file()
        assert not (output_dir / session_b.uuid).exists()

        # And the JSON really carries A's events, not an empty B.
        import json  # noqa: PLC0415

        payload = json.loads((output_dir / session_a.uuid / "session.json").read_text("utf-8"))
        assert payload["session"]["uuid"] == session_a.uuid
        assert payload["blocks"], "A's blocks must be present; B would have produced none"
    finally:
        store.stop()


def test_compiler_shutdown_coroutine_is_awaited(tmp_path: Path) -> None:
    """Regression: a soft ``shutdown()`` coroutine must actually be awaited.

    ``ObserverController.shutdown()`` used to log "deferring to garbage
    collection" and drop the coroutine, which leaks the compiler's
    persistent ``httpx.AsyncClient`` (the R8 contract) and raises
    "coroutine was never awaited" at interpreter exit.

    Runs against a real background loop thread, which is the
    production arrangement: ``main.py`` calls ``shutdown()`` from the
    Qt thread while the loop runs elsewhere.
    """
    from agentvoca.core.async_loop import AsyncLoopThread  # noqa: PLC0415
    from agentvoca.observer.compile.base import SessionCompiler  # noqa: PLC0415
    from agentvoca.observer.models import SessionBundle  # noqa: PLC0415

    class _RecordingCompiler(SessionCompiler):
        def __init__(self, cfg: ObserverCompileConfig) -> None:
            super().__init__(cfg)
            self.shutdown_ran = False

        async def compile(self, bundle: SessionBundle) -> object:  # type: ignore[override]
            raise AssertionError("compile must not be called by this test")

        async def shutdown(self) -> None:
            self.shutdown_ran = True

    loop_thread = AsyncLoopThread()
    loop_thread.start()
    store = ObserverStore(root=tmp_path / "store")
    store.start()
    try:
        cfg = ObserverCompileConfig(provider="rules", formats=["markdown"])
        compiler = _RecordingCompiler(cfg)
        controller = ObserverController(
            config=_make_full_config(cfg),
            event_bus=EventBus(),
            store=store,
            loop=loop_thread.loop,
        )
        controller.attach_surface(compiler, [], _NoopIndicator())

        controller.shutdown()

        assert compiler.shutdown_ran is True, (
            "compiler.shutdown() coroutine was dropped instead of awaited"
        )
        # Idempotent: a second shutdown must not raise even though the
        # store is already stopped.
        controller.shutdown()
    finally:
        store.stop()
        loop_thread.stop()


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
