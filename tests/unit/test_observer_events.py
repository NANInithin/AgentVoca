"""OBS-4: Observer bus events.

All six Observer events and the two new hotkey actions are declared in
``core/events.py`` so Tracks 2 and 3 never need to edit that file. These
tests assert that every new event constructs with its required fields
and that the two new hotkey actions are accepted in the Literal.
"""

from __future__ import annotations

import typing

import pytest

from agentvoca.core.events import (
    HotkeyEvent,
    ObserverCompiledEvent,
    ObserverKeyframeEvent,
    ObserverPausedEvent,
    ObserverSessionEndedEvent,
    ObserverSessionStartedEvent,
    ObserverUtteranceEvent,
)


def _all_literal_values(literal_type: typing.Any) -> frozenset[str]:
    return frozenset(typing.get_args(literal_type))


class TestHotkeyActions:
    def test_toggle_observer_in_literal(self) -> None:
        action_type = HotkeyEvent.__annotations__["action"]
        assert "toggle_observer" in _all_literal_values(action_type)
        assert "pause_observer" in _all_literal_values(action_type)
        # Existing actions are still there — additive change, not a removal.
        assert "toggle_recording" in _all_literal_values(action_type)

    def test_hotkey_event_with_toggle_observer(self) -> None:
        ev = HotkeyEvent(action="toggle_observer")
        assert ev.action == "toggle_observer"

    def test_hotkey_event_with_pause_observer(self) -> None:
        ev = HotkeyEvent(action="pause_observer")
        assert ev.action == "pause_observer"


class TestObserverSessionStartedEvent:
    def test_constructs_with_required_fields(self) -> None:
        ev = ObserverSessionStartedEvent(
            session_uuid="abc-123",
            session_id=42,
            started_at_ms=1_700_000_000_000,
        )
        assert ev.session_uuid == "abc-123"
        assert ev.session_id == 42
        assert ev.started_at_ms == 1_700_000_000_000


class TestObserverSessionEndedEvent:
    def test_constructs_with_required_fields(self) -> None:
        ev = ObserverSessionEndedEvent(
            session_uuid="abc-123",
            session_id=42,
            duration_ms=600_000,
            event_count=1234,
        )
        assert ev.session_uuid == "abc-123"
        assert ev.session_id == 42
        assert ev.duration_ms == 600_000
        assert ev.event_count == 1234


class TestObserverPausedEvent:
    @pytest.mark.parametrize(
        "paused,reason",
        [
            (True, "hotkey"),
            (False, "hotkey"),
            (True, "excluded_app"),
            (True, "disk_cap"),
        ],
    )
    def test_constructs(self, paused: bool, reason: str) -> None:
        ev = ObserverPausedEvent(paused=paused, reason=reason)
        assert ev.paused is paused
        assert ev.reason == reason


class TestObserverKeyframeEvent:
    def test_constructs_with_required_fields(self) -> None:
        ev = ObserverKeyframeEvent(event_id=99, trigger="window_change")
        assert ev.event_id == 99
        assert ev.trigger == "window_change"
        assert ev.app_name is None
        assert ev.deduped is False

    def test_constructs_with_all_fields(self) -> None:
        ev = ObserverKeyframeEvent(
            event_id=99,
            trigger="scroll_settle",
            app_name="chrome.exe",
            deduped=True,
        )
        assert ev.app_name == "chrome.exe"
        assert ev.deduped is True


class TestObserverUtteranceEvent:
    def test_ambient(self) -> None:
        ev = ObserverUtteranceEvent(text="hello world", source="ambient", duration_ms=2000)
        assert ev.text == "hello world"
        assert ev.source == "ambient"
        assert ev.duration_ms == 2000

    def test_dictated(self) -> None:
        ev = ObserverUtteranceEvent(
            text="this is a dictated line", source="dictated", duration_ms=1500
        )
        assert ev.source == "dictated"


class TestObserverCompiledEvent:
    def test_constructs_with_markdown_and_json(self) -> None:
        ev = ObserverCompiledEvent(
            session_uuid="abc",
            markdown_path="exports/abc/session.md",
            json_path="exports/abc/session.json",
            degraded=False,
            latency_ms=4200,
        )
        assert ev.markdown_path == "exports/abc/session.md"
        assert ev.json_path == "exports/abc/session.json"
        assert ev.degraded is False
        assert ev.latency_ms == 4200

    def test_constructs_with_no_json(self) -> None:
        """When 'json' is not in compile.formats, json_path is None."""
        ev = ObserverCompiledEvent(
            session_uuid="abc",
            markdown_path="exports/abc/session.md",
            json_path=None,
            degraded=True,
            latency_ms=1000,
        )
        assert ev.json_path is None
        assert ev.degraded is True


class TestAllEventsAreDataclasses:
    @pytest.mark.parametrize(
        "cls",
        [
            ObserverSessionStartedEvent,
            ObserverSessionEndedEvent,
            ObserverPausedEvent,
            ObserverKeyframeEvent,
            ObserverUtteranceEvent,
            ObserverCompiledEvent,
        ],
    )
    def test_is_dataclass(self, cls: type) -> None:
        import dataclasses

        assert dataclasses.is_dataclass(cls)
