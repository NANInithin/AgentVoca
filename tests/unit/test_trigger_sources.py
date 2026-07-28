"""Tests for the trigger sources (OBS-13).

The sources — window change, scroll settle, click/selection, speech
onset — live in ``TriggerEngine``. We test the source logic directly
through the engine's ``_on_scroll`` / ``_on_click`` / ``_poll_once``
hooks without involving real pynput or the platform. The pynput
listener thread itself is not exercised here; it is just a thin
adapter over the same handlers.
"""

from __future__ import annotations

from typing import Optional

from agentvoca.config.schema import ObserverTriggersConfig
from agentvoca.observer.models import ObserverSession
from agentvoca.observer.triggers import TriggerEngine, TriggerGate


class FakeActiveApp:
    """Active-app detector fake. ``set(app, title)`` then ``detect()`` returns it."""

    def __init__(self) -> None:
        self._app: Optional[str] = "chrome.exe"
        self._title: Optional[str] = "LinkedIn - Acme"
        self.detect_calls = 0

    def set(self, app: Optional[str], title: Optional[str]) -> None:
        self._app = app
        self._title = title

    def detect(self) -> tuple[Optional[str], Optional[str]]:
        self.detect_calls += 1
        return self._app, self._title

    def is_available(self) -> bool:
        return True


class FakeStore:
    """Minimal store stand-in. We never need the full ObserverStore here."""

    def open_session(self, app_version: str) -> ObserverSession:  # pragma: no cover
        raise NotImplementedError

    def close_session(self, session_id: int, ended_at_ms: int) -> None:  # pragma: no cover
        raise NotImplementedError


class FakeSession:
    """SessionManager substitute that records events into a list."""

    def __init__(self) -> None:
        self.events: list[tuple] = []

    def record(
        self,
        kind: str,
        *,
        app_name: Optional[str] = None,
        window_title: Optional[str] = None,
        text: Optional[str] = None,
        blob_path: Optional[str] = None,
        meta: Optional[dict] = None,
        ts_ms: Optional[int] = None,
    ):
        self.events.append((kind, app_name, window_title, meta or {}))


class FakeClock:
    def __init__(self, t: float = 1000.0) -> None:
        self._t = t

    def __call__(self) -> float:
        return self._t

    def advance(self, dt: float) -> None:
        self._t += dt


def _make_engine(
    gate: TriggerGate, app: FakeActiveApp, session=None, clock: Optional[FakeClock] = None
) -> TriggerEngine:
    if session is None:
        session = FakeSession()
    if clock is None:
        clock = FakeClock()
    cfg = ObserverTriggersConfig()
    return TriggerEngine(
        config=cfg,
        session=session,
        active_app=app,
        gate=gate,
        clock=clock,
    )


# ── Scroll ─────────────────────────────────────────────────────────


class TestScrollSettle:
    def test_200_scroll_events_yield_one_settle(self) -> None:
        accepted: list[str] = []
        gate = TriggerGate(min_interval_ms=0, enqueue=lambda r: accepted.append(r))
        app = FakeActiveApp()
        clock = FakeClock()
        engine = _make_engine(gate, app, clock=clock)
        # Pre-seed last_app so the poll's first check does not record
        # a spurious focus_change.
        engine._last_app = (app._app, app._title)

        for _ in range(200):
            engine.on_scroll_for_test()
        assert accepted == []
        clock.advance(1.0)
        engine.poll_once_for_test()
        assert accepted == ["scroll_settle"]
        accepted.clear()
        engine.poll_once_for_test()
        assert accepted == [], "settle must not fire twice without a new scroll"

    def test_scroll_settle_disabled_does_not_fire(self) -> None:
        accepted: list[str] = []
        gate = TriggerGate(min_interval_ms=0, enqueue=lambda r: accepted.append(r))
        app = FakeActiveApp()
        clock = FakeClock()
        engine = _make_engine(gate, app, clock=clock)
        engine._scroll_settle_enabled = False
        engine._last_app = (app._app, app._title)
        engine.on_scroll_for_test()
        clock.advance(1.0)
        engine.poll_once_for_test()
        assert accepted == []


# ── Click / drag-select ───────────────────────────────────────────


class TestClickAndSelection:
    def test_click_within_5px_is_click(self) -> None:
        accepted: list[str] = []
        gate = TriggerGate(min_interval_ms=0, enqueue=lambda r: accepted.append(r))
        app = FakeActiveApp()
        engine = _make_engine(gate, app)

        engine.on_click_down_for_test(100, 200)
        engine.on_click_up_for_test(102, 203)  # 2 px right, 3 px down
        assert accepted == ["click"]

    def test_drag_more_than_5px_is_selection(self) -> None:
        accepted: list[str] = []
        gate = TriggerGate(min_interval_ms=0, enqueue=lambda r: accepted.append(r))
        app = FakeActiveApp()
        engine = _make_engine(gate, app)

        engine.on_click_down_for_test(100, 200)
        engine.on_click_up_for_test(150, 200)  # 50 px right
        assert accepted == ["selection"]

    def test_drag_exactly_5px_is_click(self) -> None:
        # 5 px is the boundary. The spec says "more than 5 px" → drag.
        # Exactly 5 px is a click.
        accepted: list[str] = []
        gate = TriggerGate(min_interval_ms=0, enqueue=lambda r: accepted.append(r))
        app = FakeActiveApp()
        engine = _make_engine(gate, app)

        engine.on_click_down_for_test(100, 200)
        engine.on_click_up_for_test(105, 200)  # exactly 5 px
        assert accepted == ["click"]

    def test_up_without_down_does_nothing(self) -> None:
        accepted: list[str] = []
        gate = TriggerGate(min_interval_ms=0, enqueue=lambda r: accepted.append(r))
        app = FakeActiveApp()
        engine = _make_engine(gate, app)

        engine.on_click_up_for_test(100, 200)  # no down
        assert accepted == []


# ── Window change ─────────────────────────────────────────────────


class TestWindowChange:
    def test_poll_records_focus_change_on_app_change(self) -> None:
        accepted: list[str] = []
        session = FakeSession()
        gate = TriggerGate(min_interval_ms=0, enqueue=lambda r: accepted.append(r))
        app = FakeActiveApp()
        engine = _make_engine(gate, app, session=session)
        # Pre-seed last_app so the first poll does not record a
        # spurious focus_change for the initial state.
        engine._last_app = (app._app, app._title)

        engine.poll_once_for_test()  # chrome.exe / LinkedIn
        # No change → no event, no request.
        assert session.events == []
        assert accepted == []

        app.set("Code.exe", "main.py - agentvoca")
        engine.poll_once_for_test()
        # A focus_change event was recorded.
        assert len(session.events) == 1
        kind, app_name, title, meta = session.events[0]
        assert kind == "focus_change"
        assert app_name == "Code.exe"
        assert title == "main.py - agentvoca"
        assert meta.get("previous_app") == "chrome.exe"
        # And a keyframe request was made.
        assert accepted == ["window_change"]

    def test_poll_does_not_re_fire_on_no_change(self) -> None:
        accepted: list[str] = []
        session = FakeSession()
        gate = TriggerGate(min_interval_ms=0, enqueue=lambda r: accepted.append(r))
        app = FakeActiveApp()
        engine = _make_engine(gate, app, session=session)
        engine._last_app = (app._app, app._title)

        engine.poll_once_for_test()
        engine.poll_once_for_test()
        engine.poll_once_for_test()
        assert len(accepted) == 0
        assert len(session.events) == 0


# ── Speech onset ─────────────────────────────────────────────────


class TestSpeechOnset:
    def test_speech_onset_fires_when_enabled(self) -> None:
        accepted: list[str] = []
        gate = TriggerGate(min_interval_ms=0, enqueue=lambda r: accepted.append(r))
        app = FakeActiveApp()
        engine = _make_engine(gate, app)

        engine.on_speech_onset()
        engine.on_speech_onset()
        engine.on_speech_onset()
        # min_interval=0 but the bucket caps at 4, so 3 calls all pass.
        assert accepted == ["speech_onset"] * 3

    def test_speech_onset_ignored_when_disabled(self) -> None:
        accepted: list[str] = []
        gate = TriggerGate(min_interval_ms=0, enqueue=lambda r: accepted.append(r))
        app = FakeActiveApp()
        engine = _make_engine(gate, app)
        engine._speech_onset_enabled = False
        engine.on_speech_onset()
        assert accepted == []


# ── Each disabled trigger flag drops that source only ─────────────


class TestDisabledSourceFlags:
    def test_window_change_disabled_does_not_fire(self) -> None:
        accepted: list[str] = []
        session = FakeSession()
        gate = TriggerGate(min_interval_ms=0, enqueue=lambda r: accepted.append(r))
        app = FakeActiveApp()
        engine = _make_engine(gate, app, session=session)
        engine._window_change_enabled = False
        app.set("Code.exe", "main.py")
        engine.poll_once_for_test()
        assert session.events == []
        assert accepted == []

    def test_click_selection_disabled_does_not_fire(self) -> None:
        accepted: list[str] = []
        gate = TriggerGate(min_interval_ms=0, enqueue=lambda r: accepted.append(r))
        app = FakeActiveApp()
        engine = _make_engine(gate, app)
        engine._click_selection_enabled = False
        engine.on_click_down_for_test(100, 200)
        engine.on_click_up_for_test(150, 200)
        assert accepted == []
