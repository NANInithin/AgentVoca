"""``none`` session compiler (v0.4.0, Track 3, OBS-23).

Raw chronological dump: one line per event, no grouping, no
rewriting. The escape hatch for a user who wants the unprocessed
timeline (e.g. for downstream analysis). ``summary=""``,
``degraded=False`` \u2014 the contract for ``none`` says it is the
deliberate minimum, not a degraded state.
"""

from __future__ import annotations

import datetime
import logging

from agentvoca.observer.compile.base import SessionCompiler
from agentvoca.observer.models import CompiledSession, SessionBundle

logger = logging.getLogger(__name__)


def _local_time(ts_ms: int) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(ts_ms / 1000.0).astimezone()


class NoneCompiler(SessionCompiler):
    """Raw chronological event dump. The no-op compiler."""

    async def compile(self, bundle: SessionBundle) -> CompiledSession:
        """Render every event as one line, in ts_ms order.

        The output is intentionally minimal so a user who picks
        ``provider: none`` gets exactly what they asked for: a flat
        timeline they can grep, awk, or load into a notebook.
        """
        events = bundle.events

        title = "# Session (raw dump)"
        if events:
            started = events[0].ts_ms
            ended = events[-1].ts_ms
            started_local = _local_time(started).strftime("%Y-%m-%d %H:%M:%S")
            ended_local = _local_time(ended).strftime("%Y-%m-%d %H:%M:%S")
            title = f"# Session \u2014 {started_local} \u2013 {ended_local} (raw dump)"

        lines: list[str] = [title, ""]
        for event in events:
            local = _local_time(event.ts_ms).strftime("%H:%M:%S")
            text = (event.text or "").replace("\n", " ").strip()
            app = event.app_name or "?"
            lines.append(f"{local} [{event.kind:<20}] {app} :: {text}")

        markdown = "\n".join(lines) + "\n"

        return CompiledSession(
            markdown=markdown,
            summary="",
            blocks=[
                {
                    "index": 0,
                    "started_at_ms": events[0].ts_ms if events else 0,
                    "ended_at_ms": events[-1].ts_ms if events else 0,
                    "app_name": "",
                    "window_title": "",
                    "summary": "",
                    "utterances": [
                        {
                            "ts_ms": e.ts_ms,
                            "text": e.text or "",
                            "source": ("dictated" if e.kind == "utterance_dictated" else "ambient"),
                        }
                        for e in events
                        if e.kind in ("utterance_ambient", "utterance_dictated")
                    ],
                    "selections": [
                        {
                            "ts_ms": e.ts_ms,
                            "text": e.text or "",
                            "method": e.meta.get("method", "uia"),
                            "truncated": bool(e.meta.get("truncated", False)),
                        }
                        for e in events
                        if e.kind == "selection"
                    ],
                    "keyframes": [
                        {
                            "ts_ms": e.ts_ms,
                            "blob_path": e.blob_path or "",
                            "trigger": e.meta.get("trigger", "window_change"),
                            "ocr_text": e.text or "",
                        }
                        for e in events
                        if e.kind == "keyframe"
                    ],
                    "gaps": [],
                }
            ]
            if events
            else [],
            provider="none",
            degraded=False,
        )


__all__ = ["NoneCompiler"]
