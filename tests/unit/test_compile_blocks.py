"""Tests for ``observer/compile/base.py`` — the shared blocking algorithm.

Track 3, OBS-20. Verifies the contract from
``docs/proposals/v0.4.0-contracts.md`` §5.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Sequence

import pytest

from agentvoca.observer.compile.base import block_window, split_blocks
from agentvoca.observer.models import ObserverEvent, ObserverSession, SessionBundle
from agentvoca.observer.store import ObserverStore

# ── helpers ────────────────────────────────────────────────────────────


def _session() -> ObserverSession:
    """Build a minimal ObserverSession for use in bundles."""
    return ObserverSession(
        id=1,
        uuid=str(uuid.uuid4()),
        started_at_ms=1_000_000,
        ended_at_ms=2_000_000,
        status="closed",
        app_version="0.4.0",
        schema_version=1,
    )


def _evt(
    ts_ms: int,
    kind: str,
    app_name: str = "chrome.exe",
    window_title: str = "Doc",
    text: str | None = None,
) -> ObserverEvent:
    """Build a no-frills ObserverEvent."""
    return ObserverEvent(
        id=int(ts_ms),  # unique-ish per timestamp
        session_id=1,
        ts_ms=ts_ms,
        kind=kind,  # type: ignore[arg-type]
        app_name=app_name,
        window_title=window_title,
        text=text,
    )


def _bundle(events: Sequence[ObserverEvent]) -> SessionBundle:
    return SessionBundle(session=_session(), events=list(events))


# ── the tests ──────────────────────────────────────────────────────────


def test_focus_change_starts_a_block() -> None:
    """A ``focus_change`` event must open a new block."""
    events = [
        _evt(1000, "focus_change", app_name="chrome.exe"),
        _evt(2000, "utterance_ambient", text="hello"),
        _evt(3000, "focus_change", app_name="Code.exe"),
        _evt(4000, "utterance_ambient", text="world"),
    ]
    result = split_blocks(_bundle(events))
    assert len(result) == 2
    assert result[0][0].kind == "focus_change"
    assert result[0][0].app_name == "chrome.exe"
    assert result[1][0].app_name == "Code.exe"


def test_six_minute_same_app_gap_starts_new_block() -> None:
    """6 minutes between same-app events (>5 min) starts a new block."""
    events = [
        _evt(0, "utterance_ambient", text="a"),
        _evt(60_000, "utterance_ambient", text="b"),
        _evt(60_000 + 6 * 60_000, "utterance_ambient", text="c"),
    ]
    result = split_blocks(_bundle(events))
    assert len(result) == 2
    assert result[0][-1].text == "b"
    assert result[1][0].text == "c"


def test_four_minute_gap_does_not_split() -> None:
    """A same-app gap of 4 minutes stays in one block."""
    events = [
        _evt(0, "utterance_ambient", text="a"),
        _evt(4 * 60_000, "utterance_ambient", text="b"),
    ]
    result = split_blocks(_bundle(events))
    assert len(result) == 1
    assert len(result[0]) == 2


def test_pause_start_and_end_do_not_split() -> None:
    """A pause stretch inside one block does not fragment the block."""
    events = [
        _evt(0, "utterance_ambient", text="before"),
        _evt(1000, "pause_start"),
        _evt(2000, "gap"),
        _evt(3000, "pause_end"),
        _evt(4000, "utterance_ambient", text="after"),
    ]
    result = split_blocks(_bundle(events))
    assert len(result) == 1
    kinds = [e.kind for e in result[0]]
    assert kinds == [
        "utterance_ambient",
        "pause_start",
        "gap",
        "pause_end",
        "utterance_ambient",
    ]


def test_empty_session_returns_empty_list() -> None:
    """An empty session produces zero blocks."""
    assert split_blocks(_bundle([])) == []


def test_first_event_not_focus_change_opens_implicit_block() -> None:
    """If the session does not start with a focus_change, an implicit
    block is opened containing the first event."""
    events = [
        _evt(0, "utterance_ambient", text="hello"),
        _evt(1000, "utterance_ambient", text="world"),
    ]
    result = split_blocks(_bundle(events))
    assert len(result) == 1
    assert len(result[0]) == 2
    assert result[0][0].kind == "utterance_ambient"


def test_all_pauses_session_is_one_block() -> None:
    """A session of only pause_* events is a single block."""
    events = [
        _evt(0, "pause_start"),
        _evt(1000, "gap"),
        _evt(2000, "pause_end"),
    ]
    result = split_blocks(_bundle(events))
    assert len(result) == 1
    assert len(result[0]) == 3


def test_split_blocks_is_pure() -> None:
    """Calling split_blocks twice on the same bundle yields equal output."""
    events = [
        _evt(0, "focus_change", app_name="a"),
        _evt(1000, "utterance_ambient"),
        _evt(2000, "focus_change", app_name="b"),
        _evt(3000, "utterance_ambient"),
    ]
    bundle = _bundle(events)
    once = split_blocks(bundle)
    twice = split_blocks(bundle)
    assert once == twice


def test_block_window_helper() -> None:
    """block_window returns first and last timestamps."""
    assert block_window([]) == (0, 0)
    events = [_evt(100, "utterance_ambient"), _evt(500, "utterance_ambient")]
    assert block_window(events) == (100, 500)


def test_fixture_session_block_count_is_three(tmp_path: Path) -> None:
    """The OBS-9 fixture (3 blocks) must split into three blocks.

    The fixture writes a session with three hard-coded blocks separated
    by 7 minutes each, so the split-rules exercise focus_change, the
    time-based split (well over 5 min), and an implicit first
    utterance_ambient within block 1.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.fixtures.observer_fixture import build_fixture_session  # noqa: PLC0415

    store_root = tmp_path / "store"
    store = ObserverStore(root=store_root)
    store.start()
    try:
        session = build_fixture_session(store)
        bundle = store.load_bundle(session_id=session.id)
        blocks = split_blocks(bundle)
        # The fixture writes a focus_change at the start of each block,
        # so we expect three focus_change-separated blocks.
        assert len(blocks) == 3
        for block in blocks:
            assert block[0].kind == "focus_change"
    finally:
        store.stop()


@pytest.fixture
def temp_store_root(tmp_path: Path) -> Path:
    return tmp_path / "observer_split"
