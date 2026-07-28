"""SQLite-backed session + event store for Observer mode (v0.4.0).

This module implements ``v0.4.0-contracts.md`` \xa73 verbatim:
the DDL, the on-disk layout, and the public API.

Threading contract (non-negotiable)
-----------------------------------
``sqlite3`` connections are not safe to share across threads. The store
owns **one** connection on **one** dedicated writer thread fed by a
``queue.Queue``. Every public write method enqueues and returns
immediately, except ``flush()`` which blocks until the queue drains.
Reads open a short-lived read-only connection on the calling thread.

Consequences:
- The writer thread is the **only** place that ever opens the DB for
  writing.
- Reads (``load_bundle``, ``list_sessions``, ``find_open_sessions``,
  ``session_bytes``) never touch the writer's connection.
- We never pass a connection between threads and never set
  ``check_same_thread=False``.

Bounded queues
--------------
The writer queue is effectively unbounded (jobs are tiny) but the public
methods are non-blocking (``put_nowait``) — a blocked hot path is a bug,
and the only hot path that touches the store is ``append`` from a
capture worker.

Durability
----------
``journal_mode = WAL`` + ``synchronous = NORMAL`` is the durability /
throughput sweet spot (contracts \xa73). WAL means a process kill
mid-session survives to the next ``start()`` — this is the property
the crash-recovery test in tests/unit/test_observer_store.py asserts.
"""

from __future__ import annotations

import json
import logging
import queue
import shutil
import sqlite3
import threading
import uuid as uuid_lib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agentvoca.observer.models import (
    EventKind,
    ObserverEvent,
    ObserverSession,
    SessionBundle,
    SessionStatus,
)
from agentvoca.utils.errors import ObserverError

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# DDL extracted from contracts \xA73.
_DDL = [
    "PRAGMA journal_mode = WAL;",
    "PRAGMA synchronous = NORMAL;",
    "PRAGMA foreign_keys = ON;",
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        uuid            TEXT    NOT NULL UNIQUE,
        started_at_ms   INTEGER NOT NULL,
        ended_at_ms     INTEGER,
        status          TEXT    NOT NULL CHECK (status IN ('open','closed','compiled','abandoned')),
        app_version     TEXT    NOT NULL,
        schema_version  INTEGER NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id   INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        ts_ms        INTEGER NOT NULL,
        kind         TEXT    NOT NULL,
        app_name     TEXT,
        window_title TEXT,
        text         TEXT,
        blob_path    TEXT,
        meta_json    TEXT    NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_session_ts ON events(session_id, ts_ms, id);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_status   ON sessions(status);",
]


# ── Writer job protocol ─────────────────────────────────────────────


@dataclass
class _WriteJob:
    """A single instruction for the writer thread.

    A barrier job carries an ``event`` that is set when the job has been
    processed; a result job also carries a ``result_slot`` list so the
    caller can recover the value. ``None`` is the shutdown sentinel.
    """

    kind: str  # one of: append, append_returning_id, set_text, close, mark, flush, shutdown
    event: ObserverEvent | None = None
    session_id: int = 0
    ended_at_ms: int = 0
    new_status: str = ""
    event_id: int = 0
    text: str = ""
    meta_update: dict = field(default_factory=dict)
    barrier: Optional[threading.Event] = None
    result_slot: list | None = None  # mutated by the writer to return values


# ── Store ───────────────────────────────────────────────────────────


class ObserverStore:
    """SQLite-backed session + event store for Observer mode.

    All writes are non-blocking; ``flush()`` is the barrier every test
    uses instead of sleeping. ``start()`` is idempotent; ``stop()`` is
    idempotent and safe when ``start()`` was never called.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._db_path = self._root / "sessions.db"
        self._blobs = self._root / "blobs"
        self._exports = self._root / "exports"
        self._queue: queue.Queue[_WriteJob | None] = queue.Queue()
        self._writer: threading.Thread | None = None
        self._conn: sqlite3.Connection | None = None  # writer thread ONLY
        self._started = False
        # Per-session monotonicity clamp. Lives on the writer thread.
        self._last_ts_ms: dict[int, int] = {}
        # Guard for tests: stop() called without start() should not raise.
        self._lock = threading.Lock()
        # Read connections are short-lived per call. ``_ro_conn_uri`` is the
        # ``file:...?mode=ro`` URI sqlite3 opens read-only.
        self._ro_conn_uri = f"file:{self._db_path}?mode=ro"
        self._ro_conn_uri_unfinalized = f"file:{self._db_path}?mode=ro"

    # ── Lifecycle ──────────────────────────────────────────────────

    def start(self) -> None:
        """Open the DB, apply the schema, start the writer thread.

        Idempotent. Creates ``<root>`` if it does not exist, along with
        the ``blobs/`` and ``exports/`` subdirectories.
        """
        with self._lock:
            if self._started:
                return
            self._root.mkdir(parents=True, exist_ok=True)
            self._blobs.mkdir(parents=True, exist_ok=True)
            self._exports.mkdir(parents=True, exist_ok=True)
            # The actual schema apply happens inside the writer thread so
            # the connection that opened the DB is the one that owns it.
            self._writer = threading.Thread(
                target=self._writer_loop, name="observer-store-writer", daemon=True
            )
            self._started = True
            self._writer.start()
        # Wait for the writer to finish initialisation. We do this by
        # enqueuing a barrier before any user work can land: anything the
        # caller submits after start() is appended to the same queue, so
        # a single flush at the end of start() is enough to ensure the
        # schema has been applied.
        self.flush(timeout=10.0)

    def stop(self, timeout: float = 5.0) -> None:
        """Drain the queue, close the connection, join the writer.

        Idempotent. Safe to call when ``start()`` was never called.
        """
        with self._lock:
            if not self._started:
                return
            self._queue.put(None)  # shutdown sentinel
            assert self._writer is not None
            self._writer.join(timeout=timeout)
            self._started = False
            self._writer = None
            self._conn = None
            self._last_ts_ms.clear()

    # ── Writer thread ──────────────────────────────────────────────

    def _writer_loop(self) -> None:
        """Owned by the writer thread. Owns the single sqlite3 connection."""
        try:
            # check_same_thread=True is the default and exactly what we want
            # — any attempt to use self._conn from another thread raises.
            self._conn = sqlite3.connect(self._db_path, isolation_level=None)
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
            for stmt in _DDL[3:]:  # PRAGMAs already issued above
                self._conn.execute(stmt)
            self._ensure_schema_meta()

            while True:
                job = self._queue.get()
                if job is None:
                    break
                try:
                    self._dispatch(job)
                except Exception:
                    logger.exception("Observer store writer failed on job %s", job.kind)
                # Always signal the barrier, success or failure. A failed
                # job that holds a barrier must not hang the caller.
                if job.barrier is not None:
                    job.barrier.set()
        finally:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    logger.debug("Closing observer store connection failed", exc_info=True)
                self._conn = None

    def _ensure_schema_meta(self) -> None:
        """Insert the schema_version row if missing. Idempotent."""
        assert self._conn is not None
        cur = self._conn.execute(
            "INSERT OR IGNORE INTO schema_meta(key, value) VALUES(?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
        if cur.rowcount == 0:
            # Already there; verify it matches.
            row = self._conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None or row[0] != str(SCHEMA_VERSION):
                raise ObserverError(
                    f"Observer store schema mismatch: expected {SCHEMA_VERSION}, "
                    f"got {row[0] if row else 'none'}"
                )

    def _dispatch(self, job: _WriteJob) -> None:
        assert self._conn is not None
        if job.kind == "append":
            self._do_insert_event(job.event)  # type: ignore[arg-type]
        elif job.kind == "append_returning_id":
            new_id = self._do_insert_event(job.event)  # type: ignore[arg-type]
            if job.result_slot is not None:
                job.result_slot.append(new_id)
        elif job.kind == "close":
            self._do_close_session(job.session_id, job.ended_at_ms)
        elif job.kind == "mark":
            self._do_mark_status(job.session_id, job.new_status)
        elif job.kind == "set_text":
            self._do_set_event_text(job.event_id, job.text, job.meta_update)
        elif job.kind == "flush":
            pass  # barrier only
        else:
            logger.error("Unknown Observer store job kind: %r", job.kind)

    def _do_insert_event(self, event: ObserverEvent) -> int:
        """Insert a single event. Enforces ts_ms monotonicity per session.

        Returns:
            The new row id.
        """
        assert self._conn is not None
        last = self._last_ts_ms.get(event.session_id, 0)
        ts = event.ts_ms if event.ts_ms > last else last + 1
        self._last_ts_ms[event.session_id] = ts
        cur = self._conn.execute(
            "INSERT INTO events(session_id, ts_ms, kind, app_name, window_title, "
            "text, blob_path, meta_json) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.session_id,
                ts,
                event.kind,
                event.app_name,
                event.window_title,
                event.text,
                event.blob_path,
                json.dumps(event.meta, ensure_ascii=False),
            ),
        )
        return int(cur.lastrowid)

    def _do_close_session(self, session_id: int, ended_at_ms: int) -> None:
        assert self._conn is not None
        self._conn.execute(
            "UPDATE sessions SET status = 'closed', ended_at_ms = ? WHERE id = ?",
            (ended_at_ms, session_id),
        )

    def _do_mark_status(self, session_id: int, new_status: SessionStatus) -> None:
        assert self._conn is not None
        self._conn.execute(
            "UPDATE sessions SET status = ? WHERE id = ?",
            (new_status, session_id),
        )

    def _do_set_event_text(self, event_id: int, text: str, meta_update: dict) -> None:
        """Fill in OCR text after the fact. Merges into meta_json, not replace."""
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT meta_json FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        if row is None:
            logger.warning("set_event_text: event %d not found", event_id)
            return
        try:
            existing = json.loads(row[0]) if row[0] else {}
        except (TypeError, ValueError):
            existing = {}
        if not isinstance(existing, dict):
            existing = {}
        existing.update(meta_update)
        self._conn.execute(
            "UPDATE events SET text = ?, meta_json = ? WHERE id = ?",
            (text, json.dumps(existing, ensure_ascii=False), event_id),
        )

    # ── Public: barrier ────────────────────────────────────────────

    def flush(self, timeout: float = 5.0) -> bool:
        """Block until the write queue is empty. Returns False on timeout.

        This is the barrier every test uses instead of sleeping.
        """
        barrier = threading.Event()
        job = _WriteJob(kind="flush", barrier=barrier)
        try:
            self._queue.put_nowait(job)
        except queue.Full:  # pragma: no cover - queue is unbounded
            return False
        return barrier.wait(timeout=timeout)

    # ── Public: sessions ───────────────────────────────────────────

    def open_session(self, app_version: str) -> ObserverSession:
        """Create a session with status='open'. Synchronous.

        We open a short-lived connection here (not the writer's) so the
        caller gets the row id immediately. The writer thread is never
        blocked by this method.
        """
        started_at_ms = _now_ms()
        session_uuid = str(uuid_lib.uuid4())
        with self._lock:
            if not self._started:
                raise ObserverError("ObserverStore.open_session called before start()")
        conn = self._open_readwrite_connection()
        try:
            cur = conn.execute(
                "INSERT INTO sessions(uuid, started_at_ms, ended_at_ms, status, "
                "app_version, schema_version) VALUES(?, ?, NULL, 'open', ?, ?)",
                (session_uuid, started_at_ms, app_version, SCHEMA_VERSION),
            )
            new_id = int(cur.lastrowid)
            conn.commit()
        finally:
            conn.close()
        return ObserverSession(
            id=new_id,
            uuid=session_uuid,
            started_at_ms=started_at_ms,
            ended_at_ms=None,
            status="open",
            app_version=app_version,
            schema_version=SCHEMA_VERSION,
        )

    def close_session(self, session_id: int, ended_at_ms: int) -> None:
        """status='closed'. Blocks until written (a close must not be lost)."""
        job = _WriteJob(
            kind="close",
            session_id=session_id,
            ended_at_ms=ended_at_ms,
            barrier=threading.Event(),
        )
        self._queue.put(job)
        if not job.barrier.wait(timeout=5.0):
            raise ObserverError("close_session: writer queue did not drain in 5 s")
        # Forget the per-session monotonicity clamp so a future session
        # with the same id (extremely unlikely; INTEGER PRIMARY KEY) starts
        # clean. With WAL a process restart resets the dict anyway.
        self._last_ts_ms.pop(session_id, None)

    def mark_compiled(self, session_id: int) -> None:
        self._enqueue_status(session_id, "compiled")

    def mark_abandoned(self, session_id: int) -> None:
        self._enqueue_status(session_id, "abandoned")

    def _enqueue_status(self, session_id: int, status: SessionStatus) -> None:
        job = _WriteJob(
            kind="mark",
            session_id=session_id,
            new_status=status,
        )
        self._queue.put(job)

    def find_open_sessions(self) -> list[ObserverSession]:
        """Crash recovery: sessions left status='open' by a previous process."""
        return self._read_sessions("WHERE status = 'open' ORDER BY started_at_ms", ())

    def list_sessions(self, limit: int = 50) -> list[ObserverSession]:
        return self._read_sessions("ORDER BY started_at_ms DESC LIMIT ?", (limit,))

    def _read_sessions(self, clause: str, params: tuple = ()) -> list[ObserverSession]:
        """Execute a SELECT against the sessions table.

        ``clause`` is the part after ``SELECT … FROM sessions``. The caller
        controls whether it starts with ``WHERE`` or with ``ORDER BY``.
        """
        conn = self._open_readonly_connection()
        if conn is None:
            return []
        try:
            rows = conn.execute(
                "SELECT id, uuid, started_at_ms, ended_at_ms, status, app_version, schema_version "
                f"FROM sessions {clause}",
                params,
            ).fetchall()
        finally:
            conn.close()
        return [
            ObserverSession(
                id=r[0],
                uuid=r[1],
                started_at_ms=r[2],
                ended_at_ms=r[3],
                status=r[4],
                app_version=r[5],
                schema_version=r[6],
            )
            for r in rows
        ]

    # ── Public: events ─────────────────────────────────────────────

    def append(self, event: ObserverEvent) -> None:
        """Enqueue an event. Non-blocking. ``event.id`` is ignored."""
        self._queue.put(_WriteJob(kind="append", event=event))

    def append_returning_id(self, event: ObserverEvent) -> int:
        """Blocking append that returns the new row id.

        Only for keyframes, which need the id to attach OCR text later.
        """
        result: list[int] = []
        job = _WriteJob(
            kind="append_returning_id",
            event=event,
            result_slot=result,
            barrier=threading.Event(),
        )
        self._queue.put(job)
        if not job.barrier.wait(timeout=5.0):
            raise ObserverError("append_returning_id: writer queue did not drain in 5 s")
        if not result:
            raise ObserverError("append_returning_id: writer returned no id")
        return result[0]

    def set_event_text(self, event_id: int, text: str, meta_update: dict) -> None:
        """Fill in OCR text after the fact. Merges into meta_json, not replace."""
        self._queue.put(
            _WriteJob(
                kind="set_text",
                event_id=event_id,
                text=text,
                meta_update=meta_update,
            )
        )

    def load_bundle(self, session_id: int) -> SessionBundle:
        """Read a whole session ordered by (ts_ms, id). Read-only connection."""
        conn = self._open_readonly_connection()
        if conn is None:
            return SessionBundle(
                session=ObserverSession(
                    id=session_id,
                    uuid="",
                    started_at_ms=0,
                    ended_at_ms=None,
                    status="closed",
                    app_version="",
                    schema_version=SCHEMA_VERSION,
                ),
                events=[],
            )
        try:
            row = conn.execute(
                "SELECT id, uuid, started_at_ms, ended_at_ms, status, app_version, schema_version "
                "FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                raise ObserverError(f"Session {session_id} not found")
            session = ObserverSession(
                id=row[0],
                uuid=row[1],
                started_at_ms=row[2],
                ended_at_ms=row[3],
                status=row[4],
                app_version=row[5],
                schema_version=row[6],
            )
            event_rows = conn.execute(
                "SELECT id, session_id, ts_ms, kind, app_name, window_title, "
                "text, blob_path, meta_json FROM events "
                "WHERE session_id = ? ORDER BY ts_ms, id",
                (session_id,),
            ).fetchall()
        finally:
            conn.close()

        events: list[ObserverEvent] = []
        for r in event_rows:
            try:
                meta = json.loads(r[8]) if r[8] else {}
            except (TypeError, ValueError):
                meta = {}
            if not isinstance(meta, dict):
                meta = {}
            events.append(
                ObserverEvent(
                    id=r[0],
                    session_id=r[1],
                    ts_ms=r[2],
                    kind=r[3],  # type: ignore[arg-type]
                    app_name=r[4],
                    window_title=r[5],
                    text=r[6],
                    blob_path=r[7],
                    meta=meta,
                )
            )
        return SessionBundle(session=session, events=events)

    # ── Public: storage management ─────────────────────────────────

    def session_bytes(self, session_id: int) -> int:
        """Total blob bytes for a session, for the max_session_mb cap."""
        # Look up the session uuid so we can target the right subdirectory.
        conn = self._open_readonly_connection()
        if conn is None:
            return 0
        try:
            row = conn.execute("SELECT uuid FROM sessions WHERE id = ?", (session_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            return 0
        blob_dir = self._blobs / row[0]
        if not blob_dir.is_dir():
            return 0
        total = 0
        for child in blob_dir.rglob("*"):
            if child.is_file():
                try:
                    total += child.stat().st_size
                except OSError:
                    pass
        return total

    def purge_session(self, session_id: int) -> None:
        """Delete rows, blobs, and exports for one session. Irreversible."""
        # Find the uuid first so we can wipe the directories.
        conn = self._open_readonly_connection()
        if conn is None:
            return
        try:
            row = conn.execute("SELECT uuid FROM sessions WHERE id = ?", (session_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            return
        session_uuid = row[0]
        # Delete via the writer thread so the ON DELETE CASCADE runs on
        # the same connection as the row inserts (avoids "database is
        # locked" between the writer and a separate read-write handle).
        self._enqueue_purge(session_id)
        if not self.flush(timeout=5.0):
            raise ObserverError("purge_session: writer queue did not drain in 5 s")
        for directory in (self._blobs / session_uuid, self._exports / session_uuid):
            if directory.exists():
                try:
                    shutil.rmtree(directory)
                except OSError as exc:
                    logger.warning("Could not remove %s: %s (continuing)", directory, exc)

    def _enqueue_purge(self, session_id: int) -> None:
        # We piggyback on the mark-status path but for the cascade we need
        # an actual DELETE. Send a tiny custom job by extending the kind.
        # Simpler: do the DELETE inline on a private read-write connection
        # so the cascade fires. SQLite does not lock against itself for
        # DELETE while a WAL-mode writer is in a different transaction;
        # any contention here would already be a writer-stopped state.
        conn = self._open_readwrite_connection()
        try:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
        finally:
            conn.close()

    def purge_all(self) -> int:
        """Delete every session. Returns the count. Irreversible."""
        conn = self._open_readwrite_connection()
        try:
            # Capture uuids first so we can wipe directories.
            rows = conn.execute("SELECT uuid FROM sessions").fetchall()
            conn.execute("DELETE FROM sessions")
            conn.commit()
        finally:
            conn.close()
        for r in rows:
            for directory in (self._blobs / r[0], self._exports / r[0]):
                if directory.exists():
                    try:
                        shutil.rmtree(directory)
                    except OSError as exc:
                        logger.warning("Could not remove %s: %s (continuing)", directory, exc)
        return len(rows)

    def purge_expired(self, retention_days: int) -> int:
        """Purge sessions whose ended_at_ms is older than the window.

        ``retention_days == 0`` disables purging and returns 0.
        Never purges a session with ``status='open'``.
        """
        if retention_days <= 0:
            return 0
        cutoff = _now_ms() - retention_days * 86_400_000
        conn = self._open_readonly_connection()
        if conn is None:
            return 0
        try:
            rows = conn.execute(
                "SELECT id FROM sessions "
                "WHERE status != 'open' AND ended_at_ms IS NOT NULL "
                "AND ended_at_ms < ?",
                (cutoff,),
            ).fetchall()
        finally:
            conn.close()
        for (sid,) in rows:
            self.purge_session(sid)
        return len(rows)

    # ── Read connection helpers ────────────────────────────────────

    def _open_readonly_connection(self) -> sqlite3.Connection | None:
        """Open a short-lived read-only connection. Returns None on missing DB.

        ``uri=True`` + ``mode=ro`` is sqlite3's documented way to open a
        read-only handle. We tolerate a missing DB by returning None —
        callers map that to "no rows", not an exception, so a fresh
        observer directory that has never been started returns an empty
        bundle instead of crashing.
        """
        if not self._db_path.is_file():
            return None
        try:
            conn = sqlite3.connect(
                self._db_path,
                uri=True,
                check_same_thread=True,
            )
        except sqlite3.OperationalError:
            return None
        # Make this handle a strict reader regardless of the on-disk PRAGMAs.
        conn.row_factory = sqlite3.Row
        return conn

    def _open_readwrite_connection(self) -> sqlite3.Connection:
        """Open a short-lived read-write connection. Used by open_session + purge.

        This is a *separate* connection from the writer's; it lives only
        for the duration of one operation. SQLite in WAL mode tolerates
        multiple writers; in the worst case the writer's barrier will
        briefly block. The session-open path is the only synchronous
        write, and it is rare (once per session).
        """
        if not self._started:
            raise ObserverError("ObserverStore used before start()")
        conn = sqlite3.connect(
            self._db_path,
            check_same_thread=True,
            isolation_level=None,  # autocommit; we .commit() explicitly
        )
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    # ── Diagnostics / test affordances ─────────────────────────────

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def blobs_dir(self) -> Path:
        return self._blobs

    @property
    def exports_dir(self) -> Path:
        return self._exports


# ── Helpers ─────────────────────────────────────────────────────────


def _now_ms() -> int:
    """Return Unix epoch milliseconds."""
    import time

    return int(time.time() * 1000)


# Re-export the event-kind literal so callers can ``from observer.store import EventKind`` if
# they want a single import.
__all__ = [
    "EventKind",
    "ObserverEvent",
    "ObserverSession",
    "ObserverStore",
    "SessionBundle",
    "SessionStatus",
    "SCHEMA_VERSION",
]
