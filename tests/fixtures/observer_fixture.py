"""Fixture-session generator for Observer mode (v0.4.0).

Unblocks Track 3 to work in parallel with Track 2. Track 3 cannot
wait for real capture, so this module writes a realistic synthetic
session into a temp store. The result is deterministic: fixed base
timestamp, fixed text, fixed dHash values, so Track 3's compiler
tests can assert on exact markdown output across runs.

Shape (per block): a focus_change, 2-4 ambient utterances, 2-3
keyframes with OCR text already populated, 1 selection. Block 2 also
has a dictated utterance, a pause_start/pause_end pair, and a gap
marker. Blocks use different apps (chrome.exe / Code.exe / chrome.exe)
so the 5-minute same-app split rule is also exercised by the third
block.

Real (small) JPEG bytes are written for every keyframe blob so
``session_bytes()`` and ``purge_session()`` have something to measure
and delete.
"""

from __future__ import annotations

import datetime
import io
from pathlib import Path

from PIL import Image

from agentvoca.observer.models import (
    ObserverEvent,
    ObserverSession,
)
from agentvoca.observer.store import ObserverStore

# Fixed base timestamp so the output is byte-identical across runs.
#
# Derived from a fixed *local* wall clock rather than a fixed epoch. The
# rules compiler renders every timestamp with ``.astimezone()`` — local
# time is what a user wants to read — so a hard-coded epoch renders as a
# different clock time in every timezone, and the committed golden file
# only matched on a machine in the author's zone. Anchoring the wall
# clock instead makes the epoch machine-dependent and the *rendering*
# identical everywhere, which is what the golden compares.
#
# 2026-01-15 09:40 local time. Mid-January, so no DST boundary.
_BASE_TS_MS = int(datetime.datetime(2026, 1, 15, 9, 40).timestamp() * 1000)

# Per-block: (app_name, window_title, [utterance texts], [keyframe texts],
# selection_text, [extra events]). All text is short and deterministic.
_BLOCKS: list[dict] = [
    {
        "app": "chrome.exe",
        "title": "Senior Backend Engineer - Acme | LinkedIn",
        "utterances": [
            "Looking at the job description for the senior backend role.",
            "They want five years of Python and PostgreSQL experience.",
            "Also some Kubernetes and observability tooling.",
        ],
        "keyframe_texts": [
            "Senior Backend Engineer\nAcme Corp\nRemote (US)\n"
            "5+ years Python, PostgreSQL, Kubernetes",
            "Requirements:\n- Distributed systems\n- Observability\n"
            "- On-call rotation 1 week per quarter",
        ],
        "selection": (
            "Five or more years of professional experience building "
            "high-throughput backend services in Python."
        ),
        "extras": [],
    },
    {
        "app": "Code.exe",
        "title": "scratch.py — agentvoca",
        "utterances": [
            "Let me draft a quick cover letter that maps to these points.",
            "I should mention the OpenTelemetry side of my last project.",
        ],
        "keyframe_texts": [
            "# Cover letter\n\nDear Acme team,\n\nI am writing to apply for "
            "the Senior Backend Engineer role."
        ],
        "selection": (
            "I led the migration of our metrics pipeline from Prometheus "
            "to OpenTelemetry across thirty services."
        ),
        # A dictated utterance, a pause pair, and a gap marker.
        "extras": [
            {
                "kind": "utterance_dictated",
                "text": "Insert at cursor: I would welcome the chance to discuss the role further.",
                "duration_ms": 4500,
            },
            {"kind": "pause_start", "meta": {"reason": "hotkey"}},
            {"kind": "gap", "meta": {"reason": "asr_queue_full", "dropped": 2}},
            {"kind": "pause_end", "meta": {"reason": "hotkey"}},
        ],
    },
    {
        # Third block uses the same app as block 1 (chrome) so the
        # 5-minute same-app split rule is exercised — but the gap between
        # block 2's last event and this block's events is well over five
        # minutes, so this becomes its own block.
        "app": "chrome.exe",
        "title": "Acme — Benefits & Perks",
        "utterances": [
            "Let me check the benefits before I send the application.",
        ],
        "keyframe_texts": [
            "Acme Benefits:\n- Comprehensive health, dental, vision\n"
            "- 4 weeks PTO + 12 holidays\n- $2k/year learning budget"
        ],
        "selection": ("Four weeks of paid time off plus the twelve company holidays."),
        "extras": [],
    },
]


def _make_jpeg_bytes(width: int = 32, height: int = 24, color: tuple = (200, 200, 200)) -> bytes:
    """Build a tiny valid JPEG so the blob path is non-empty.

    Real keyframes will be much larger; this is enough to exercise
    ``session_bytes()`` and ``purge_session()``.
    """
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=75)
    return buf.getvalue()


def _write_blob(blobs_dir: Path, session_uuid: str, ts_ms: int, seq: int) -> str:
    """Write a real JPEG into the session's blob subdirectory.

    Returns the relative path stored in the DB (blobs/<uuid>/<ts>-<seq>.jpg).
    """
    subdir = blobs_dir / session_uuid
    subdir.mkdir(parents=True, exist_ok=True)
    rel = f"blobs/{session_uuid}/{ts_ms}-{seq}.jpg"
    (subdir / f"{ts_ms}-{seq}.jpg").write_bytes(_make_jpeg_bytes())
    return rel


def build_fixture_session(store: ObserverStore, *, blocks: int = 3) -> ObserverSession:
    """Write a realistic multi-block session into ``store`` and return it.

    Deterministic: fixed base timestamp, fixed text, fixed dHash values.
    Two calls produce byte-identical databases (modulo row ids and
    session uuids) so Track 3's compiler tests can assert on exact
    markdown output.

    Args:
        store: A started ``ObserverStore``.
        blocks: How many of the three hard-coded blocks to include.

    Returns:
        The session row that was created.
    """
    if blocks < 0 or blocks > len(_BLOCKS):
        raise ValueError(f"blocks must be in [0, {len(_BLOCKS)}], got {blocks}")
    session = store.open_session(app_version="0.4.0")
    ts = _BASE_TS_MS
    step_ms = 60_000  # one minute between events inside a block

    for block_idx in range(blocks):
        block = _BLOCKS[block_idx]

        # 1) focus_change opens the block.
        previous_app = "explorer.exe" if block_idx == 0 else _BLOCKS[block_idx - 1]["app"]
        focus = ObserverEvent(
            id=0,
            session_id=session.id,
            ts_ms=ts,
            kind="focus_change",
            app_name=block["app"],
            window_title=block["title"],
            meta={"previous_app": previous_app},
        )
        store.append(focus)
        ts += step_ms

        # 2) ambient utterances.
        for text in block["utterances"]:
            store.append(
                ObserverEvent(
                    id=0,
                    session_id=session.id,
                    ts_ms=ts,
                    kind="utterance_ambient",
                    text=text,
                    app_name=block["app"],
                    window_title=block["title"],
                    meta={"duration_ms": 2_500, "confidence": 0.92},
                )
            )
            ts += step_ms // 2

        # 3) keyframes — each writes a real JPEG blob first.
        for seq, ocr_text in enumerate(block["keyframe_texts"]):
            blob_path = _write_blob(store.blobs_dir, session.uuid, ts, seq)
            # ``append_returning_id`` so the fixture can attach OCR text
            # via ``set_event_text`` — exercising both code paths and
            # keeping the resulting event aligned with the real capture
            # pipeline.
            dhash = (block_idx * 1_000_000) + (seq * 65_537) + 1
            trigger = "window_change" if seq == 0 else "scroll_settle"
            width = 1280
            height = 720
            new_id = store.append_returning_id(
                ObserverEvent(
                    id=0,
                    session_id=session.id,
                    ts_ms=ts,
                    kind="keyframe",
                    app_name=block["app"],
                    window_title=block["title"],
                    blob_path=blob_path,
                    meta={
                        "trigger": trigger,
                        "dhash": dhash,
                        "width": width,
                        "height": height,
                    },
                )
            )
            store.set_event_text(
                new_id,
                text=ocr_text,
                meta_update={
                    "ocr_engine": "rapidocr",
                    "ocr_status": "ok",
                    "ocr_ms": 120,
                    "ocr_confidence": 0.93,
                },
            )
            ts += step_ms

        # 4) selection.
        if block["selection"]:
            store.append(
                ObserverEvent(
                    id=0,
                    session_id=session.id,
                    ts_ms=ts,
                    kind="selection",
                    text=block["selection"],
                    app_name=block["app"],
                    window_title=block["title"],
                    meta={
                        "method": "uia",
                        "truncated": False,
                        "chars": len(block["selection"]),
                    },
                )
            )
            ts += step_ms

        # 5) block-specific extras (dictated utterance, pause pair, gap).
        for extra in block["extras"]:
            kind = extra["kind"]
            if kind == "utterance_dictated":
                store.append(
                    ObserverEvent(
                        id=0,
                        session_id=session.id,
                        ts_ms=ts,
                        kind=kind,  # type: ignore[arg-type]
                        text=extra["text"],
                        app_name=block["app"],
                        window_title=block["title"],
                        meta={
                            "duration_ms": extra["duration_ms"],
                            "inserted": True,
                        },
                    )
                )
            elif kind in ("pause_start", "pause_end", "gap"):
                store.append(
                    ObserverEvent(
                        id=0,
                        session_id=session.id,
                        ts_ms=ts,
                        kind=kind,  # type: ignore[arg-type]
                        app_name=block["app"],
                        window_title=block["title"],
                        meta=extra["meta"],
                    )
                )
            ts += step_ms

        # Push the next block's first event well past the 5-minute
        # same-app split rule so the compiler's block boundaries are
        # deterministic. 7 minutes (420000 ms) is safely past 5 min.
        ts += 7 * step_ms

    # Close the session so the fixture looks like a finished recording.
    import time as _time

    store.close_session(session.id, ended_at_ms=int(_time.time() * 1000))
    store.flush(timeout=5.0)
    return session


__all__ = ["build_fixture_session"]
