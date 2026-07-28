"""OBS-5: ObserverStore tests.

The store is the source of truth for Observer data. These tests verify:
- schema is created and ``schema_meta`` row exists
- ``start()`` is idempotent; ``stop()`` is idempotent and safe without start
- open -> append -> flush -> load_bundle round-trips with meta as a dict
- ``append_returning_id`` returns a usable id; ``set_event_text`` fills
  text and **merges** meta (a pre-existing key survives)
- ts_ms monotonic clamp: backwards-going timestamps are clamped up
- ``close_session`` sets status=closed and ended_at_ms
- ``find_open_sessions`` returns only status=open rows
- ``purge_session`` removes rows AND the blob directory
- ``purge_expired(7)`` removes an 8-day-old session, keeps a 1-day-old
  session, never touches an open one
- 4 threads x 100 ``append()`` calls then ``flush()``: 400 rows, no
  exception (the cross-thread connection test)
- crash simulation: append, stop() without close_session, reopen on
  the same dir, every event survives
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest

from agentvoca.observer.models import ObserverEvent
from agentvoca.observer.store import SCHEMA_VERSION, ObserverStore
from agentvoca.utils.errors import ObserverError


def _make_event(
    session_id: int,
    ts_ms: int,
    kind: str = "focus_change",
    **kwargs,
) -> ObserverEvent:
    return ObserverEvent(
        id=0,
        session_id=session_id,
        ts_ms=ts_ms,
        kind=kind,  # type: ignore[arg-type]
        **kwargs,
    )


# ── Schema / lifecycle ─────────────────────────────────────────────


class TestSchema:
    def test_start_creates_schema(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            # The DB and the auxiliary directories must exist.
            assert (tmp_path / "sessions.db").is_file()
            assert (tmp_path / "blobs").is_dir()
            assert (tmp_path / "exports").is_dir()
            # Verify the schema_meta row and the version.
            conn = sqlite3.connect(tmp_path / "sessions.db")
            try:
                row = conn.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()
                assert row is not None
                assert row[0] == str(SCHEMA_VERSION)
                tables = {
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                assert {"schema_meta", "sessions", "events"}.issubset(tables)
            finally:
                conn.close()
        finally:
            store.stop()

    def test_start_is_idempotent(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        # Second start() is a no-op (no second writer thread, no exception).
        store.start()
        try:
            # Schema_version row was created once, not twice.
            conn = sqlite3.connect(tmp_path / "sessions.db")
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM schema_meta WHERE key='schema_version'"
                ).fetchone()[0]
                assert count == 1
            finally:
                conn.close()
        finally:
            store.stop()

    def test_stop_is_idempotent(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.stop()  # safe without start()
        store.start()
        store.stop()
        store.stop()  # safe after a real stop

    def test_creates_root_dir_if_missing(self, tmp_path: Path) -> None:
        root = tmp_path / "deep" / "nested" / "observer"
        store = ObserverStore(root=root)
        store.start()
        try:
            assert root.is_dir()
            assert (root / "sessions.db").is_file()
        finally:
            store.stop()


# ── Events: round trip + monotonicity + meta merge ────────────────


class TestEvents:
    def test_open_append_flush_load_round_trip(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            session = store.open_session(app_version="0.4.0")
            for i in range(50):
                store.append(
                    _make_event(
                        session_id=session.id,
                        ts_ms=1_000 + i,
                        kind="focus_change" if i % 2 else "keyframe",
                        meta={"i": i, "tag": "test"},
                    )
                )
            assert store.flush(timeout=2.0)
            bundle = store.load_bundle(session_id=session.id)
            assert bundle.session.id == session.id
            assert bundle.session.status == "open"
            assert len(bundle.events) == 50
            # Ordering: (ts_ms, id) ascending.
            for prev, curr in zip(bundle.events, bundle.events[1:]):
                assert (prev.ts_ms, prev.id) <= (curr.ts_ms, curr.id)
            # Meta round-tripped as dict.
            assert bundle.events[0].meta == {"i": 0, "tag": "test"}
        finally:
            store.stop()

    def test_append_returning_id(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            session = store.open_session(app_version="0.4.0")
            new_id = store.append_returning_id(
                _make_event(
                    session_id=session.id,
                    ts_ms=2_000,
                    kind="keyframe",
                    blob_path="blobs/x/y.jpg",
                )
            )
            assert new_id > 0
            # Wait for any pending work to drain.
            assert store.flush(timeout=2.0)
            bundle = store.load_bundle(session_id=session.id)
            assert bundle.events[0].id == new_id
            assert bundle.events[0].blob_path == "blobs/x/y.jpg"
        finally:
            store.stop()

    def test_set_event_text_merges_meta(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            session = store.open_session(app_version="0.4.0")
            new_id = store.append_returning_id(
                _make_event(
                    session_id=session.id,
                    ts_ms=3_000,
                    kind="keyframe",
                    meta={"trigger": "click", "dhash": 12345},
                )
            )
            assert store.flush(timeout=2.0)
            # Now fill in OCR text and merge in OCR-specific meta.
            store.set_event_text(
                new_id,
                text="Hello world",
                meta_update={"ocr_engine": "rapidocr", "ocr_ms": 50},
            )
            assert store.flush(timeout=2.0)
            bundle = store.load_bundle(session_id=session.id)
            assert bundle.events[0].text == "Hello world"
            # The pre-existing key "trigger" must survive.
            assert bundle.events[0].meta["trigger"] == "click"
            assert bundle.events[0].meta["dhash"] == 12345
            # The new keys are merged in.
            assert bundle.events[0].meta["ocr_engine"] == "rapidocr"
            assert bundle.events[0].meta["ocr_ms"] == 50
        finally:
            store.stop()

    def test_ts_ms_monotonicity_clamp(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            session = store.open_session(app_version="0.4.0")
            # First event: 1000.
            store.append(_make_event(session_id=session.id, ts_ms=1_000))
            # Then a backwards jump — should be clamped to >1000.
            store.append(_make_event(session_id=session.id, ts_ms=500))
            # Then another forward jump past the previous.
            store.append(_make_event(session_id=session.id, ts_ms=2_000))
            # Then another backward — should be > 2000.
            store.append(_make_event(session_id=session.id, ts_ms=1_999))
            assert store.flush(timeout=2.0)
            bundle = store.load_bundle(session_id=session.id)
            assert [e.ts_ms for e in bundle.events] == [1_000, 1_001, 2_000, 2_001]
        finally:
            store.stop()

    def test_ts_ms_monotonicity_isolated_per_session(self, tmp_path: Path) -> None:
        """The clamp must not leak across sessions: a new session starts clean."""
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            a = store.open_session(app_version="0.4.0")
            store.append(_make_event(session_id=a.id, ts_ms=10_000))
            assert store.flush(timeout=2.0)
            b = store.open_session(app_version="0.4.0")
            # New session can start at any ts_ms, including lower.
            store.append(_make_event(session_id=b.id, ts_ms=500))
            assert store.flush(timeout=2.0)
            bundle_a = store.load_bundle(session_id=a.id)
            bundle_b = store.load_bundle(session_id=b.id)
            assert bundle_a.events[0].ts_ms == 10_000
            assert bundle_b.events[0].ts_ms == 500
        finally:
            store.stop()


# ── Session close + status ─────────────────────────────────────────


class TestSessionLifecycle:
    def test_close_session_marks_status_closed(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            session = store.open_session(app_version="0.4.0")
            store.close_session(session.id, ended_at_ms=99_000)
            assert store.flush(timeout=2.0)
            bundle = store.load_bundle(session_id=session.id)
            assert bundle.session.status == "closed"
            assert bundle.session.ended_at_ms == 99_000
            # find_open_sessions must not list it any more.
            open_sessions = store.find_open_sessions()
            assert all(s.id != session.id for s in open_sessions)
        finally:
            store.stop()

    def test_find_open_sessions(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            open_one = store.open_session(app_version="0.4.0")
            open_two = store.open_session(app_version="0.4.0")
            closed_one = store.open_session(app_version="0.4.0")
            store.close_session(closed_one.id, ended_at_ms=50_000)
            assert store.flush(timeout=2.0)
            ids = {s.id for s in store.find_open_sessions()}
            assert open_one.id in ids
            assert open_two.id in ids
            assert closed_one.id not in ids
        finally:
            store.stop()

    def test_list_sessions_orders_by_started_at_desc(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            older = store.open_session(app_version="0.4.0")
            time.sleep(0.01)
            newer = store.open_session(app_version="0.4.0")
            assert store.flush(timeout=2.0)
            listed = store.list_sessions(limit=10)
            ids = [s.id for s in listed]
            assert ids.index(newer.id) < ids.index(older.id)
        finally:
            store.stop()

    def test_mark_compiled_and_abandoned(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            session = store.open_session(app_version="0.4.0")
            store.mark_compiled(session.id)
            assert store.flush(timeout=2.0)
            bundle = store.load_bundle(session_id=session.id)
            assert bundle.session.status == "compiled"

            other = store.open_session(app_version="0.4.0")
            store.mark_abandoned(other.id)
            assert store.flush(timeout=2.0)
            other_bundle = store.load_bundle(session_id=other.id)
            assert other_bundle.session.status == "abandoned"
        finally:
            store.stop()


# ── Purge ──────────────────────────────────────────────────────────


class TestPurge:
    def test_purge_session_removes_rows_and_blobs(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            session = store.open_session(app_version="0.4.0")
            # Create a real blob file.
            blob_dir = tmp_path / "blobs" / session.uuid
            blob_dir.mkdir(parents=True, exist_ok=True)
            (blob_dir / "keyframe.jpg").write_bytes(b"\xff\xd8\xff\xe0")
            assert (blob_dir / "keyframe.jpg").is_file()
            store.purge_session(session.id)
            # Row gone.
            assert not store.find_open_sessions()  # may be empty already
            with pytest.raises(ObserverError):
                store.load_bundle(session_id=session.id)
            # Blob directory gone.
            assert not blob_dir.exists()
        finally:
            store.stop()

    def test_purge_all(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            for _ in range(3):
                store.open_session(app_version="0.4.0")
            assert store.flush(timeout=2.0)
            assert len(store.list_sessions(limit=100)) == 3
            count = store.purge_all()
            assert count == 3
            assert store.list_sessions(limit=100) == []
        finally:
            store.stop()

    def test_purge_expired_zero_disables(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            session = store.open_session(app_version="0.4.0")
            store.close_session(session.id, ended_at_ms=1)
            assert store.flush(timeout=2.0)
            # 0 disables.
            assert store.purge_expired(0) == 0
            assert store.list_sessions(limit=10) != []
        finally:
            store.stop()

    def test_purge_expired_respects_window_and_open(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            now = int(time.time() * 1000)
            day_ms = 86_400_000

            old_session = store.open_session(app_version="0.4.0")
            store.close_session(old_session.id, ended_at_ms=now - 8 * day_ms)

            fresh_session = store.open_session(app_version="0.4.0")
            store.close_session(fresh_session.id, ended_at_ms=now - 1 * day_ms)

            # An open session, even with ended_at_ms deep in the past.
            open_session = store.open_session(app_version="0.4.0")
            # Manually backdate it via a direct UPDATE so we can test
            # the "never purge open" invariant.
            conn = sqlite3.connect(tmp_path / "sessions.db")
            try:
                conn.execute(
                    "UPDATE sessions SET ended_at_ms = ? WHERE id = ?",
                    (now - 30 * day_ms, open_session.id),
                )
                conn.commit()
            finally:
                conn.close()

            assert store.flush(timeout=2.0)
            removed = store.purge_expired(7)
            assert removed == 1
            assert store.flush(timeout=2.0)
            remaining = {s.id for s in store.list_sessions(limit=100)}
            assert old_session.id not in remaining
            assert fresh_session.id in remaining
            assert open_session.id in remaining
        finally:
            store.stop()


# ── Concurrency ────────────────────────────────────────────────────


class TestConcurrency:
    def test_concurrent_appends_all_survive(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            session = store.open_session(app_version="0.4.0")
            n_threads = 4
            per_thread = 100
            errors: list[Exception] = []

            def appender(start_idx: int) -> None:
                try:
                    for i in range(per_thread):
                        store.append(
                            _make_event(
                                session_id=session.id,
                                ts_ms=start_idx + i,
                                kind="focus_change",
                            )
                        )
                except Exception as e:  # noqa: BLE001
                    errors.append(e)

            threads = [
                threading.Thread(target=appender, args=(idx * 10_000,)) for idx in range(n_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10.0)
            assert not errors, f"Concurrent appends raised: {errors!r}"
            assert store.flush(timeout=5.0)
            bundle = store.load_bundle(session_id=session.id)
            assert len(bundle.events) == n_threads * per_thread
            # ts_ms sequence must still be non-decreasing (the clamp is
            # the only thing keeping it so under concurrency).
            for prev, curr in zip(bundle.events, bundle.events[1:]):
                assert prev.ts_ms <= curr.ts_ms
        finally:
            store.stop()


# ── Crash / WAL recovery ───────────────────────────────────────────


class TestCrashRecovery:
    def test_events_survive_hard_restart(self, tmp_path: Path) -> None:
        """Simulate a hard kill: append events, then stop() without close_session.

        On a new process pointing at the same directory, the events must
        still be there and the session must still be ``status='open'``.
        This is the property WAL gives us.
        """
        store = ObserverStore(root=tmp_path)
        store.start()
        session = store.open_session(app_version="0.4.0")
        for i in range(10):
            store.append(_make_event(session_id=session.id, ts_ms=1_000 + i, kind="focus_change"))
        assert store.flush(timeout=2.0)
        # "Crash" — no close_session, just stop.
        store.stop()

        # Reopen on the same dir.
        store2 = ObserverStore(root=tmp_path)
        store2.start()
        try:
            open_sessions = store2.find_open_sessions()
            assert any(s.id == session.id for s in open_sessions)
            bundle = store2.load_bundle(session_id=session.id)
            assert len(bundle.events) == 10
        finally:
            store2.stop()


# ── session_bytes ──────────────────────────────────────────────────


class TestSessionBytes:
    def test_session_bytes_sums_blob_dir(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            session = store.open_session(app_version="0.4.0")
            blob_dir = tmp_path / "blobs" / session.uuid
            blob_dir.mkdir(parents=True, exist_ok=True)
            (blob_dir / "a.jpg").write_bytes(b"x" * 1000)
            (blob_dir / "b.jpg").write_bytes(b"y" * 2000)
            # Nested subdir also counts (PIL may write metadata in a subdir).
            (blob_dir / "sub").mkdir()
            (blob_dir / "sub" / "c.jpg").write_bytes(b"z" * 500)
            assert store.session_bytes(session.id) == 3500
        finally:
            store.stop()

    def test_session_bytes_zero_for_missing_dir(self, tmp_path: Path) -> None:
        store = ObserverStore(root=tmp_path)
        store.start()
        try:
            session = store.open_session(app_version="0.4.0")
            # No blob dir was created.
            assert store.session_bytes(session.id) == 0
        finally:
            store.stop()


# ── Meta round-trip edge cases ─────────────────────────────────────


def test_load_bundle_handles_corrupt_meta_gracefully(tmp_path: Path) -> None:
    """A meta_json cell that is not a JSON object must not crash load_bundle."""
    store = ObserverStore(root=tmp_path)
    store.start()
    try:
        session = store.open_session(app_version="0.4.0")
        new_id = store.append_returning_id(
            _make_event(session_id=session.id, ts_ms=1_000, kind="focus_change")
        )
        assert store.flush(timeout=2.0)
        # Corrupt the meta_json via a direct DB write.
        conn = sqlite3.connect(tmp_path / "sessions.db")
        try:
            conn.execute(
                "UPDATE events SET meta_json = ? WHERE id = ?",
                ("not-json", new_id),
            )
            conn.commit()
        finally:
            conn.close()
        bundle = store.load_bundle(session_id=session.id)
        assert bundle.events[0].meta == {}  # fallback to empty dict
    finally:
        store.stop()
