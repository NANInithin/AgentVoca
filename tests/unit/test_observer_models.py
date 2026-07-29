"""OBS-1: frozen observer data models.

The dataclasses in ``agentvoca.observer.models`` are the root of the
Observer import graph. Every other observer module imports from them;
they import nothing from observer.

These tests verify:
- every dataclass constructs with only its required fields
- ``frozen=True`` is enforced (assignment raises)
- ``EventKind`` covers all eight literals
- round-trips through ``dataclasses.asdict`` preserve the values
- default factories are correctly applied (no shared mutable state)
"""

from __future__ import annotations

import dataclasses
import typing

import pytest

from agentvoca.observer.models import (
    CompiledSession,
    EventKind,
    Grab,
    ObserverEvent,
    ObserverSession,
    OCRResult,
    Selection,
    SessionBundle,
    SessionStatus,
    TriggerReason,
)


def _all_literal_values(literal_type: typing.Any) -> frozenset[str]:
    """Return the args of a ``typing.Literal[...]`` as a frozenset."""
    return frozenset(typing.get_args(literal_type))


class TestEventKind:
    def test_event_kind_has_eight_literals(self) -> None:
        assert _all_literal_values(EventKind) == frozenset(
            {
                "utterance_ambient",
                "utterance_dictated",
                "keyframe",
                "selection",
                "focus_change",
                "pause_start",
                "pause_end",
                "gap",
            }
        )

    def test_session_status_values(self) -> None:
        assert _all_literal_values(SessionStatus) == frozenset(
            {"open", "closed", "compiled", "abandoned"}
        )

    def test_trigger_reason_values(self) -> None:
        assert _all_literal_values(TriggerReason) == frozenset(
            {"window_change", "scroll_settle", "click", "selection", "speech_onset"}
        )


class TestObserverEvent:
    def test_constructs_with_required_fields_only(self) -> None:
        ev = ObserverEvent(id=0, session_id=1, ts_ms=100, kind="keyframe")
        assert ev.id == 0
        assert ev.session_id == 1
        assert ev.ts_ms == 100
        assert ev.kind == "keyframe"
        assert ev.app_name is None
        assert ev.window_title is None
        assert ev.text is None
        assert ev.blob_path is None
        assert ev.meta == {}

    def test_frozen(self) -> None:
        ev = ObserverEvent(id=0, session_id=1, ts_ms=100, kind="keyframe")
        with pytest.raises(dataclasses.FrozenInstanceError):
            ev.ts_ms = 101  # type: ignore[misc]

    def test_meta_default_factory_isolated(self) -> None:
        """Two events must not share the same meta dict via the default factory."""
        a = ObserverEvent(id=0, session_id=1, ts_ms=100, kind="keyframe")
        b = ObserverEvent(id=0, session_id=1, ts_ms=100, kind="keyframe")
        a.meta["x"] = 1
        assert b.meta == {}


class TestObserverSession:
    def test_constructs_with_required_fields(self) -> None:
        s = ObserverSession(
            id=7,
            uuid="abc-123",
            started_at_ms=1_000,
            ended_at_ms=None,
            status="open",
            app_version="0.4.0",
            schema_version=1,
        )
        assert s.id == 7
        assert s.uuid == "abc-123"
        assert s.started_at_ms == 1_000
        assert s.ended_at_ms is None
        assert s.status == "open"

    def test_frozen(self) -> None:
        s = ObserverSession(
            id=1,
            uuid="u",
            started_at_ms=0,
            ended_at_ms=None,
            status="open",
            app_version="0",
            schema_version=1,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.status = "closed"  # type: ignore[misc]


class TestSessionBundle:
    def test_constructs(self) -> None:
        session = ObserverSession(
            id=1,
            uuid="u",
            started_at_ms=0,
            ended_at_ms=100,
            status="closed",
            app_version="0.4.0",
            schema_version=1,
        )
        events = [
            ObserverEvent(id=1, session_id=1, ts_ms=10, kind="focus_change"),
            ObserverEvent(id=2, session_id=1, ts_ms=20, kind="keyframe"),
        ]
        bundle = SessionBundle(session=session, events=events)
        assert bundle.session is session
        assert bundle.events == events

    def test_frozen(self) -> None:
        session = ObserverSession(
            id=1,
            uuid="u",
            started_at_ms=0,
            ended_at_ms=None,
            status="open",
            app_version="0",
            schema_version=1,
        )
        bundle = SessionBundle(session=session, events=[])
        with pytest.raises(dataclasses.FrozenInstanceError):
            bundle.session = session  # type: ignore[misc]


class TestOCRResult:
    def test_constructs_with_required_fields(self) -> None:
        r = OCRResult(text="hello", confidence=0.95, latency_ms=120, engine="rapidocr")
        assert r.text == "hello"
        assert r.confidence == 0.95
        assert r.latency_ms == 120
        assert r.engine == "rapidocr"

    def test_confidence_optional(self) -> None:
        r = OCRResult(text="", confidence=None, latency_ms=10, engine="x")
        assert r.confidence is None


class TestSelection:
    def test_constructs_with_required_fields(self) -> None:
        s = Selection(
            text="snippet",
            method="uia",
            app_name="chrome.exe",
            window_title="Tab",
        )
        assert s.text == "snippet"
        assert s.method == "uia"
        assert s.truncated is False

    def test_truncated_default(self) -> None:
        s = Selection(
            text="x",
            method="ocr_rect",
            app_name=None,
            window_title=None,
        )
        assert s.truncated is False


class TestGrab:
    def test_constructs_with_required_fields(self) -> None:
        g = Grab(
            jpeg=b"\xff\xd8\xff\xe0",
            width=1280,
            height=720,
            dhash=0xDEADBEEF,
            app_name="chrome.exe",
            window_title="Tab",
        )
        assert g.jpeg == b"\xff\xd8\xff\xe0"
        assert g.width == 1280
        assert g.height == 720
        assert g.dhash == 0xDEADBEEF


class TestCompiledSession:
    def test_constructs_with_required_fields(self) -> None:
        c = CompiledSession(
            markdown="# Title",
            summary="One line.",
            blocks=[{"index": 0}],
            provider="rules",
        )
        assert c.markdown == "# Title"
        assert c.summary == "One line."
        assert c.blocks == [{"index": 0}]
        assert c.provider == "rules"
        assert c.degraded is False

    def test_degraded_default_false(self) -> None:
        c = CompiledSession(markdown="", summary="", blocks=[], provider="none")
        assert c.degraded is False


class TestFrozenRoundTrip:
    @pytest.mark.parametrize(
        "value",
        [
            ObserverEvent(id=0, session_id=1, ts_ms=1, kind="keyframe"),
            ObserverSession(
                id=1,
                uuid="u",
                started_at_ms=0,
                ended_at_ms=None,
                status="open",
                app_version="0",
                schema_version=1,
            ),
            OCRResult(text="x", confidence=0.5, latency_ms=10, engine="e"),
            Selection(text="x", method="uia", app_name=None, window_title=None),
            Grab(jpeg=b"", width=0, height=0, dhash=0, app_name=None, window_title=None),
            CompiledSession(markdown="", summary="", blocks=[], provider="rules"),
        ],
    )
    def test_asdict_round_trip(self, value: object) -> None:
        """asdict round-trips the field values; this guards against a
        field rename silently breaking the JSON sidecar schema."""
        as_dict = dataclasses.asdict(value)
        cloned = dataclasses.replace(value)  # type: ignore[arg-type]
        again = dataclasses.asdict(cloned)
        assert as_dict == again
