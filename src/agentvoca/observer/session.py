"""Pure session-lifecycle state machine for Observer mode (v0.4.0).

Owns the currently-open session and the paused state. No threads, no
capture, no UI. Deliberately separated from ``ObserverController`` so
the state transitions can be unit-tested without constructing any of
the subsystems.
"""

from __future__ import annotations

import logging
from typing import Optional

from agentvoca.observer.models import (
    EventKind,
    ObserverEvent,
    ObserverSession,
)
from agentvoca.observer.store import ObserverStore

logger = logging.getLogger(__name__)


# Event kinds that are always written through, even when paused. The
# timeline must show its own gaps honestly: a ``pause_start`` during a
# pause is nonsense, but a ``pause_start`` that *opens* the pause window
# is the row that records when the pause began.
_ALWAYS_WRITE_KINDS: frozenset[EventKind] = frozenset({"pause_start", "pause_end", "gap"})


class SessionManager:
    """Owns the currently-open session and its paused state.

    Pure coordination over ``ObserverStore``. No threads, no capture, no
    UI. The state machine is intentionally simple — three states (no
    session / open-not-paused / open-paused) — so it can be unit-tested
    without constructing any of the capture/surface subsystems.

    Pause carve-out: ``record()`` while paused is a silent no-op for
    every kind except ``pause_start``, ``pause_end``, and ``gap``. The
    timeline must show its own gaps, and a pause event during a pause
    is the row that ends it.
    """

    def __init__(self, store: ObserverStore) -> None:
        self._store = store
        self._current: Optional[ObserverSession] = None
        self._is_paused: bool = False
        self._pause_reason: str = ""

    @property
    def current(self) -> Optional[ObserverSession]:
        """The currently open session, or None."""
        return self._current

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def pause_reason(self) -> str:
        """Reason the session is currently paused. Empty when not paused."""
        return self._pause_reason

    def open(self, app_version: str) -> ObserverSession:
        """Open a new session. Fails if one is already open."""
        if self._current is not None:
            raise RuntimeError(
                "SessionManager.open: a session is already open "
                f"(session_id={self._current.id}); close it first"
            )
        self._current = self._store.open_session(app_version=app_version)
        self._is_paused = False
        self._pause_reason = ""
        return self._current

    def close(self) -> Optional[ObserverSession]:
        """Close the current session. Returns the closed session, or None."""
        if self._current is None:
            return None
        import time as _time

        ended_at_ms = int(_time.time() * 1000)
        self._store.close_session(self._current.id, ended_at_ms=ended_at_ms)
        closed = ObserverSession(
            id=self._current.id,
            uuid=self._current.uuid,
            started_at_ms=self._current.started_at_ms,
            ended_at_ms=ended_at_ms,
            status="closed",
            app_version=self._current.app_version,
            schema_version=self._current.schema_version,
        )
        self._current = None
        self._is_paused = False
        self._pause_reason = ""
        return closed

    def pause(self, reason: str) -> bool:
        """Pause the open session. False if already paused or no session."""
        if self._current is None or self._is_paused:
            return False
        self._is_paused = True
        self._pause_reason = reason
        return True

    def resume(self, reason: str) -> bool:
        """Resume a paused session. False if not paused or no session."""
        if self._current is None or not self._is_paused:
            return False
        self._is_paused = False
        self._pause_reason = ""
        return True

    def record(
        self,
        kind: EventKind,
        *,
        app_name: Optional[str] = None,
        window_title: Optional[str] = None,
        text: Optional[str] = None,
        blob_path: Optional[str] = None,
        meta: Optional[dict] = None,
        ts_ms: Optional[int] = None,
    ) -> Optional[ObserverEvent]:
        """Append an event to the open session.

        No-op (returns None) when closed. When paused, every kind except
        ``pause_start``, ``pause_end``, and ``gap`` is dropped — a
        faithful timeline is the priority.

        Returns the in-memory event (with id=0 if the store has not
        assigned one yet) on success, or None on drop / no session.
        """
        if self._current is None:
            return None
        if self._is_paused and kind not in _ALWAYS_WRITE_KINDS:
            return None
        if ts_ms is None:
            import time as _time

            ts_ms = int(_time.time() * 1000)
        event = ObserverEvent(
            id=0,
            session_id=self._current.id,
            ts_ms=ts_ms,
            kind=kind,
            app_name=app_name,
            window_title=window_title,
            text=text,
            blob_path=blob_path,
            meta=meta or {},
        )
        self._store.append(event)
        return event
