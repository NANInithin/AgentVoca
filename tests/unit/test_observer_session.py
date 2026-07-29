"""OBS-8: SessionManager and ObserverController tests.

The session manager is pure coordination over the store (no threads, no
capture, no UI). The controller is the integration seam — it owns the
session lifecycle, publishes bus events, and (when Track 3 attaches a
compiler) schedules compilation on the loop.

These tests verify the contracts the plan specifies:

SessionManager:
- open -> record 3 events -> close: status='closed', all 3 stored
- record() while paused drops a keyframe but stores a gap
- pause() twice returns False the second time; same for resume()
- record() with no open session is a silent no-op, not an exception

Controller:
- with nothing attached: start_session() -> stop_session() completes
  and publishes both events (proves Tracks 2/3 are optional)
- shutdown() with a session open marks it closed, not abandoned
- shutdown() twice does not raise
- toggle_session() alternates
- start_session() returns False when observer.enabled is False
- pause()/resume() publish ObserverPausedEvent
- recover_sessions() returns store.find_open_sessions()
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agentvoca.config.schema import ASRConfig, FullConfig
from agentvoca.core.async_loop import AsyncLoopThread
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import (
    ObserverPausedEvent,
    ObserverSessionEndedEvent,
    ObserverSessionStartedEvent,
)
from agentvoca.observer.controller import ObserverController
from agentvoca.observer.session import SessionManager
from agentvoca.observer.store import ObserverStore

# ── Helpers ────────────────────────────────────────────────────────


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def loop_thread():
    t = AsyncLoopThread()
    t.start()
    yield t
    t.stop()


@pytest.fixture
def store(tmp_path: Path) -> ObserverStore:
    s = ObserverStore(root=tmp_path)
    s.start()
    yield s
    s.stop()


@pytest.fixture
def enabled_config() -> FullConfig:
    return FullConfig(
        asr=ASRConfig(provider="faster_whisper", model="base"),
        observer={
            "enabled": True,
            "storage": {"dir": str(Path("test_obs").resolve())},
        },
    )


@pytest.fixture
def disabled_config() -> FullConfig:
    return FullConfig(
        asr=ASRConfig(provider="faster_whisper", model="base"),
    )


# ── SessionManager ────────────────────────────────────────────────


class TestSessionManagerOpenClose:
    def test_open_record_close_round_trip(self, store: ObserverStore) -> None:
        mgr = SessionManager(store=store)
        session = mgr.open(app_version="0.4.0")
        assert mgr.current is session
        mgr.record(kind="focus_change", app_name="chrome.exe")
        mgr.record(kind="focus_change", app_name="Code.exe")
        mgr.record(kind="selection", text="hello")
        assert store.flush(timeout=2.0)
        closed = mgr.close()
        assert closed is not None
        assert closed.status == "closed"
        assert mgr.current is None
        bundle = store.load_bundle(session_id=session.id)
        assert len(bundle.events) == 3
        assert bundle.events[0].app_name == "chrome.exe"

    def test_open_twice_raises(self, store: ObserverStore) -> None:
        mgr = SessionManager(store=store)
        mgr.open(app_version="0.4.0")
        with pytest.raises(RuntimeError):
            mgr.open(app_version="0.4.0")

    def test_close_with_no_session_returns_none(self, store: ObserverStore) -> None:
        mgr = SessionManager(store=store)
        assert mgr.close() is None


class TestSessionManagerPause:
    def test_pause_drops_keyframe_but_stores_gap(self, store: ObserverStore) -> None:
        mgr = SessionManager(store=store)
        mgr.open(app_version="0.4.0")
        mgr.pause(reason="hotkey")
        # While paused, a keyframe is dropped.
        mgr.record(kind="keyframe", text="frame-text", meta={"trigger": "click"})
        # But pause_start/pause_end/gap are always written through.
        mgr.record(kind="pause_start", meta={"reason": "hotkey"})
        mgr.record(kind="gap", meta={"reason": "asr_queue_full", "dropped": 1})
        mgr.record(kind="pause_end", meta={"reason": "hotkey"})
        assert store.flush(timeout=2.0)
        session = mgr.current
        mgr.close()
        bundle = store.load_bundle(session_id=session.id)  # type: ignore[arg-type]
        kinds = [e.kind for e in bundle.events]
        assert "keyframe" not in kinds
        assert kinds == ["pause_start", "gap", "pause_end"]

    def test_pause_twice_returns_false(self, store: ObserverStore) -> None:
        mgr = SessionManager(store=store)
        mgr.open(app_version="0.4.0")
        assert mgr.pause(reason="hotkey") is True
        assert mgr.pause(reason="hotkey") is False
        mgr.close()

    def test_resume_twice_returns_false(self, store: ObserverStore) -> None:
        mgr = SessionManager(store=store)
        mgr.open(app_version="0.4.0")
        mgr.pause(reason="hotkey")
        assert mgr.resume(reason="hotkey") is True
        assert mgr.resume(reason="hotkey") is False
        mgr.close()

    def test_record_with_no_open_session_is_silent(self, store: ObserverStore) -> None:
        mgr = SessionManager(store=store)
        # No open session.
        result = mgr.record(kind="focus_change")
        assert result is None
        assert store.flush(timeout=2.0)


# ── ObserverController ────────────────────────────────────────────


class TestObserverControllerLifecycle:
    def test_start_stop_publishes_events(
        self,
        event_bus: EventBus,
        store: ObserverStore,
        loop_thread: AsyncLoopThread,
        enabled_config: FullConfig,
    ) -> None:
        started: list = []
        ended: list = []
        event_bus.subscribe(ObserverSessionStartedEvent, lambda e: started.append(e))
        event_bus.subscribe(ObserverSessionEndedEvent, lambda e: ended.append(e))

        ctrl = ObserverController(
            config=enabled_config, event_bus=event_bus, store=store, loop=loop_thread.loop
        )
        assert ctrl.start_session() is True
        # Second start returns False (already open).
        assert ctrl.start_session() is False
        assert ctrl.is_active
        assert store.flush(timeout=2.0)
        ctrl.stop_session()
        assert not ctrl.is_active
        assert ctrl.sessions.current is None
        assert store.flush(timeout=2.0)
        assert len(started) == 1
        assert started[0].session_id == 1
        assert len(ended) == 1

    def test_disabled_observer_start_returns_false(
        self,
        event_bus: EventBus,
        store: ObserverStore,
        loop_thread: AsyncLoopThread,
        disabled_config: FullConfig,
    ) -> None:
        ctrl = ObserverController(
            config=disabled_config, event_bus=event_bus, store=store, loop=loop_thread.loop
        )
        assert ctrl.start_session() is False
        assert not ctrl.is_active

    def test_toggle_session_alternates(
        self,
        event_bus: EventBus,
        store: ObserverStore,
        loop_thread: AsyncLoopThread,
        enabled_config: FullConfig,
    ) -> None:
        ctrl = ObserverController(
            config=enabled_config, event_bus=event_bus, store=store, loop=loop_thread.loop
        )
        assert not ctrl.is_active
        ctrl.toggle_session()
        assert ctrl.is_active
        ctrl.toggle_session()
        assert not ctrl.is_active
        assert store.flush(timeout=2.0)


class TestObserverControllerPause:
    def test_pause_resume_publishes_events(
        self,
        event_bus: EventBus,
        store: ObserverStore,
        loop_thread: AsyncLoopThread,
        enabled_config: FullConfig,
    ) -> None:
        paused: list = []
        event_bus.subscribe(ObserverPausedEvent, lambda e: paused.append(e))
        ctrl = ObserverController(
            config=enabled_config, event_bus=event_bus, store=store, loop=loop_thread.loop
        )
        ctrl.start_session()
        assert not ctrl.is_paused
        ctrl.pause(reason="hotkey")
        assert ctrl.is_paused
        ctrl.resume(reason="hotkey")
        assert not ctrl.is_paused
        ctrl.stop_session()
        assert store.flush(timeout=2.0)
        # Two events: paused=True, paused=False.
        assert len(paused) == 2
        assert paused[0].paused is True
        assert paused[0].reason == "hotkey"
        assert paused[1].paused is False
        assert paused[1].reason == "hotkey"

    def test_pause_without_session_is_noop(
        self,
        event_bus: EventBus,
        store: ObserverStore,
        loop_thread: AsyncLoopThread,
        enabled_config: FullConfig,
    ) -> None:
        ctrl = ObserverController(
            config=enabled_config, event_bus=event_bus, store=store, loop=loop_thread.loop
        )
        # No session open; pause and resume are no-ops.
        ctrl.pause(reason="hotkey")
        assert not ctrl.is_paused
        ctrl.resume(reason="hotkey")
        assert not ctrl.is_paused


class TestObserverControllerShutdown:
    def test_shutdown_with_open_session_marks_closed_not_abandoned(
        self,
        event_bus: EventBus,
        store: ObserverStore,
        loop_thread: AsyncLoopThread,
        enabled_config: FullConfig,
    ) -> None:
        ctrl = ObserverController(
            config=enabled_config, event_bus=event_bus, store=store, loop=loop_thread.loop
        )
        ctrl.start_session()
        session_id = ctrl.sessions.current.id  # type: ignore[union-attr]
        ctrl.shutdown()
        bundle = store.load_bundle(session_id=session_id)
        assert bundle.session.status == "closed", (
            f"Expected status='closed' (a clean exit is not a crash), got {bundle.session.status!r}"
        )

    def test_shutdown_twice_does_not_raise(
        self,
        event_bus: EventBus,
        store: ObserverStore,
        loop_thread: AsyncLoopThread,
        enabled_config: FullConfig,
    ) -> None:
        ctrl = ObserverController(
            config=enabled_config, event_bus=event_bus, store=store, loop=loop_thread.loop
        )
        ctrl.shutdown()  # safe when no session was opened
        ctrl.shutdown()

    def test_shutdown_without_session_is_safe(
        self,
        event_bus: EventBus,
        store: ObserverStore,
        loop_thread: AsyncLoopThread,
        enabled_config: FullConfig,
    ) -> None:
        ctrl = ObserverController(
            config=enabled_config, event_bus=event_bus, store=store, loop=loop_thread.loop
        )
        # No start_session; shutdown is still safe.
        ctrl.shutdown()


class TestObserverControllerAttach:
    def test_attach_capture_stores_references(
        self,
        event_bus: EventBus,
        store: ObserverStore,
        loop_thread: AsyncLoopThread,
        enabled_config: FullConfig,
    ) -> None:
        ctrl = ObserverController(
            config=enabled_config, event_bus=event_bus, store=store, loop=loop_thread.loop
        )
        ambient = object()
        triggers = object()
        grabber = object()
        ocr = object()
        selection = object()
        ctrl.attach_capture(ambient, triggers, grabber, ocr, selection)
        # The references are stored; start_session() will call .start() on each.
        # Use getattr to peek without breaking encapsulation.
        assert ctrl._ambient is ambient  # noqa: SLF001
        assert ctrl._triggers is triggers  # noqa: SLF001
        assert ctrl._grabber is grabber  # noqa: SLF001
        assert ctrl._ocr is ocr  # noqa: SLF001
        assert ctrl._selection is selection  # noqa: SLF001

    def test_attach_capture_start_calls_start_on_each(
        self,
        event_bus: EventBus,
        store: ObserverStore,
        loop_thread: AsyncLoopThread,
        enabled_config: FullConfig,
    ) -> None:
        """start_session() must call .start() on each attached capture object.

        Missing start() methods (e.g. Track 2 not landed yet) are
        tolerated via getattr — the soft-contract pattern.
        """
        ctrl = ObserverController(
            config=enabled_config, event_bus=event_bus, store=store, loop=loop_thread.loop
        )
        ambient = MagicMock()
        triggers = MagicMock()
        grabber = MagicMock()
        ocr = MagicMock()
        selection = MagicMock()
        ctrl.attach_capture(ambient, triggers, grabber, ocr, selection)
        ctrl.start_session()
        ambient.start.assert_called_once()
        triggers.start.assert_called_once()
        grabber.start.assert_called_once()
        ocr.start.assert_called_once()
        selection.start.assert_called_once()
        ctrl.stop_session()
        ambient.stop.assert_called_once()
        triggers.stop.assert_called_once()
        grabber.stop.assert_called_once()
        ocr.stop.assert_called_once()
        selection.stop.assert_called_once()
        assert store.flush(timeout=2.0)

    def test_attach_surface_stores_references(
        self,
        event_bus: EventBus,
        store: ObserverStore,
        loop_thread: AsyncLoopThread,
        enabled_config: FullConfig,
    ) -> None:
        ctrl = ObserverController(
            config=enabled_config, event_bus=event_bus, store=store, loop=loop_thread.loop
        )
        compiler = object()
        exporters = [object(), object()]
        indicator = object()
        ctrl.attach_surface(compiler, exporters, indicator)
        assert ctrl._compiler is compiler  # noqa: SLF001
        assert ctrl._exporters == exporters  # noqa: SLF001
        assert ctrl._indicator is indicator  # noqa: SLF001


class TestObserverControllerRecoverSessions:
    def test_recover_sessions_returns_open_ones(
        self,
        event_bus: EventBus,
        store: ObserverStore,
        loop_thread: AsyncLoopThread,
        enabled_config: FullConfig,
    ) -> None:
        ctrl = ObserverController(
            config=enabled_config, event_bus=event_bus, store=store, loop=loop_thread.loop
        )
        # Simulate a previous crash: a session left status='open' on disk.
        crashed = store.open_session(app_version="0.4.0")
        # The current process did not own this; the controller just sees it.
        recovered = ctrl.recover_sessions()
        assert any(s.id == crashed.id for s in recovered)
        # And find_open_sessions agrees.
        assert any(s.id == crashed.id for s in store.find_open_sessions())
        assert store.flush(timeout=2.0)


# ── main.py integration: existing test_main_startup extensions ─────


class TestMainStartupWithObserver:
    def test_existing_config_without_observer_block_loads(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An existing v0.3.6 config without an observer: block still
        builds the pipeline with observer_controller=None and a working
        app."""
        pytest.importorskip("PySide6", reason="PySide6 (Qt) not available")
        import agentvoca.main as m  # noqa: PLC0415

        order: list[str] = []

        class FakeApp:
            def __init__(self, *_a, **_k) -> None:
                pass

            def setQuitOnLastWindowClosed(self, _v: bool) -> None:
                pass

            def exec(self) -> int:
                order.append("app.exec")
                return 0

            def quit(self) -> None:
                pass

        class FakeWizard:
            def __init__(self, *_a, **_k) -> None:
                self.config_saved = MagicMock()

            def show(self) -> None:
                pass

            def raise_(self) -> None:
                pass

            def activateWindow(self) -> None:
                pass

            def close(self) -> None:
                pass

        class FakeOrchestrator:
            def __init__(self, *, config, **_k) -> None:
                pass

            async def start(self) -> None:
                order.append("orchestrator.start")

            async def stop(self) -> None:
                pass

        class FakeAudio:
            def __init__(self, *_a, **kw) -> None:
                self.is_recording = False

            def start(self) -> None:
                pass

            def stop(self) -> None:
                pass

        class FakeHotkeys:
            def __init__(self, *_a, **_k) -> None:
                pass

            def register(self, *_a, **_k) -> None:
                pass

            def unregister_all(self) -> None:
                pass

            def start(self) -> None:
                pass

            def stop(self) -> None:
                pass

        fake_tray = SimpleNamespace(
            open_settings_action=SimpleNamespace(triggered=MagicMock()),
            open_wizard_action=SimpleNamespace(triggered=MagicMock()),
            quit_action=SimpleNamespace(triggered=MagicMock()),
            show_message=lambda *a, **k: None,
        )

        from agentvoca.setup.first_run import AppState

        monkeypatch.setattr(m, "load_state", lambda: AppState(wizard_auto_open=False))
        monkeypatch.setattr(m, "QtWidgets", SimpleNamespace(QApplication=FakeApp))
        monkeypatch.setattr(m, "SetupWizard", FakeWizard)
        monkeypatch.setattr(m, "SettingsWindow", MagicMock())
        monkeypatch.setattr(m, "Orchestrator", FakeOrchestrator)
        monkeypatch.setattr(m, "AudioCapture", FakeAudio)
        monkeypatch.setattr(m, "HotkeyManager", FakeHotkeys)
        monkeypatch.setattr(m, "StatusOverlay", lambda *a, **k: SimpleNamespace(stop=lambda: None))
        monkeypatch.setattr(m, "TrayApp", lambda *a, **k: fake_tray)
        # VAD is constructed in the pipeline; with the model not loaded
        # it returns is_available=False, so the controller's VAD call
        # produces vad=None — no failure.

        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "asr:\n  provider: faster_whisper\n  model: base\n",
            encoding="utf-8",
        )

        rc = m.main(["--config", str(config_path)])
        assert rc == 0
        # The pipeline started; the observer wiring block was skipped
        # because observer.enabled is False.
        assert "orchestrator.start" in order

    def test_observer_enabled_builds_storage_and_shuts_down(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With observer.enabled: true the storage dir is created and
        the controller is constructed; a clean shutdown completes."""
        pytest.importorskip("PySide6", reason="PySide6 (Qt) not available")
        import agentvoca.main as m  # noqa: PLC0415

        order: list[str] = []
        fake_tray = SimpleNamespace(
            open_settings_action=SimpleNamespace(triggered=MagicMock()),
            open_wizard_action=SimpleNamespace(triggered=MagicMock()),
            quit_action=SimpleNamespace(triggered=MagicMock()),
            show_message=lambda *a, **k: None,
        )

        class FakeApp:
            def __init__(self, *_a, **_k) -> None:
                pass

            def setQuitOnLastWindowClosed(self, _v: bool) -> None:
                pass

            def exec(self) -> int:
                order.append("app.exec")
                return 0

            def quit(self) -> None:
                pass

        class FakeWizard:
            def __init__(self, *_a, **_k) -> None:
                self.config_saved = MagicMock()

            def show(self) -> None:
                pass

            def raise_(self) -> None:
                pass

            def activateWindow(self) -> None:
                pass

            def close(self) -> None:
                pass

        class FakeOrchestrator:
            def __init__(self, *, config, **_k) -> None:
                pass

            async def start(self) -> None:
                order.append("orchestrator.start")

            async def stop(self) -> None:
                pass

        class FakeAudio:
            def __init__(self, *_a, **kw) -> None:
                self.is_recording = False

            def start(self) -> None:
                pass

            def stop(self) -> None:
                pass

        class FakeHotkeys:
            def __init__(self, *_a, **_k) -> None:
                pass

            def register(self, *_a, **_k) -> None:
                pass

            def unregister_all(self) -> None:
                pass

            def start(self) -> None:
                pass

            def stop(self) -> None:
                pass

        from agentvoca.setup.first_run import AppState

        monkeypatch.setattr(m, "load_state", lambda: AppState(wizard_auto_open=False))
        monkeypatch.setattr(m, "QtWidgets", SimpleNamespace(QApplication=FakeApp))
        monkeypatch.setattr(m, "SetupWizard", FakeWizard)
        monkeypatch.setattr(m, "SettingsWindow", MagicMock())
        monkeypatch.setattr(m, "Orchestrator", FakeOrchestrator)
        monkeypatch.setattr(m, "AudioCapture", FakeAudio)
        monkeypatch.setattr(m, "HotkeyManager", FakeHotkeys)
        monkeypatch.setattr(m, "StatusOverlay", lambda *a, **k: SimpleNamespace(stop=lambda: None))
        monkeypatch.setattr(m, "TrayApp", lambda *a, **k: fake_tray)

        # Use a storage dir under tmp_path so we can verify it was created.
        storage_dir = tmp_path / "obs_storage"
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "asr:\n  provider: faster_whisper\n  model: base\n"
            "observer:\n"
            "  enabled: true\n"
            f"  storage:\n    dir: {storage_dir.as_posix()}\n",
            encoding="utf-8",
        )

        rc = m.main(["--config", str(config_path)])
        assert rc == 0
        # The storage dir was created.
        assert storage_dir.is_dir()
        assert (storage_dir / "sessions.db").is_file()
