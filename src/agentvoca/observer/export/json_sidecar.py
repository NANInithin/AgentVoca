"""JSON sidecar exporter for Observer sessions (v0.4.0, Track 3, OBS-24).

Writes the v0.5.0 Agent contract (contracts \xa75) to
``<out_dir>/<session-uuid>/session.json``. Block boundaries are
re-derived via ``split_blocks`` so the JSON can never disagree with
the markdown about where blocks begin.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from agentvoca.observer.compile.base import split_blocks
from agentvoca.observer.export.base import atomic_write_text
from agentvoca.observer.models import CompiledSession, SessionBundle

logger = logging.getLogger(__name__)


class JsonExporter:
    """Build contracts \xa75's JSON sidecar for the v0.5.0 Agent contract."""

    name = "json"

    def __init__(self, bundle: SessionBundle, out_dir: Path) -> None:
        self._bundle = bundle
        self._out_dir = Path(out_dir)

    async def export(self, compiled: CompiledSession) -> str:
        """Write the JSON sidecar and return its path.

        Args:
            compiled: The compiled session from a ``SessionCompiler``.

        Returns:
            The absolute path the JSON sidecar landed at.
        """
        blocks_payload = self._build_blocks(compiled)
        session = self._bundle.session
        first_ts = self._bundle.events[0].ts_ms if self._bundle.events else session.started_at_ms
        last_ts = self._bundle.events[-1].ts_ms if self._bundle.events else session.ended_at_ms
        duration_ms = max(0, (last_ts or 0) - first_ts)
        document = {
            "schema": "agentvoca.observer.session/1",
            "session": {
                "uuid": session.uuid,
                "started_at_ms": session.started_at_ms,
                "ended_at_ms": session.ended_at_ms if session.ended_at_ms is not None else last_ts,
                "duration_ms": duration_ms,
                "app_version": session.app_version,
                "compiler": compiled.provider,
                "degraded": bool(compiled.degraded),
            },
            "summary": compiled.summary or "",
            "blocks": blocks_payload,
        }
        text = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False)
        target = self._path()
        atomic_write_text(target, text)
        logger.debug("JsonExporter wrote %s (%d bytes)", target, len(text))
        return str(target)

    def _path(self) -> Path:
        return self._out_dir / self._bundle.session.uuid / "session.json"

    def _build_blocks(self, compiled: CompiledSession) -> list[dict]:
        """Build the JSON ``blocks`` array.

        Block boundaries come from ``split_blocks`` so the JSON and
        markdown can never disagree. Per-block ``summary`` fields
        populated by the LLM compiler are merged in by index when
        present.
        """
        blocks = split_blocks(self._bundle)
        compiled_summaries: dict[int, str] = {}
        for record in compiled.blocks or []:
            idx = int(record.get("index", -1))
            if idx >= 0 and record.get("summary"):
                compiled_summaries[idx] = str(record["summary"])

        out: list[dict] = []
        for index, block in enumerate(blocks):
            if not block:
                continue
            started_at = block[0].ts_ms
            ended_at = block[-1].ts_ms
            app_name = next((e.app_name for e in block if e.app_name), "")
            window_title = next((e.window_title for e in block if e.window_title), "")
            utterances: list[dict] = []
            selections: list[dict] = []
            keyframes: list[dict] = []
            gaps: list[dict] = []
            for event in block:
                kind = event.kind
                if kind in ("utterance_ambient", "utterance_dictated"):
                    utterances.append(
                        {
                            "ts_ms": event.ts_ms,
                            "text": event.text or "",
                            "source": "dictated" if kind == "utterance_dictated" else "ambient",
                        }
                    )
                elif kind == "selection":
                    selections.append(
                        {
                            "ts_ms": event.ts_ms,
                            "text": event.text or "",
                            "method": event.meta.get("method", "uia"),
                            "truncated": bool(event.meta.get("truncated", False)),
                        }
                    )
                elif kind == "keyframe":
                    blob = event.blob_path or ""
                    keyframes.append(
                        {
                            "ts_ms": event.ts_ms,
                            "blob_path": blob,
                            "trigger": event.meta.get("trigger", "window_change"),
                            "ocr_text": event.text or "",
                        }
                    )
                elif kind == "pause_start":
                    reason = event.meta.get("reason", "hotkey")
                    gaps.append(
                        {
                            "ts_ms": event.ts_ms,
                            "reason": f"pause_{reason}",
                            "dropped": 0,
                        }
                    )
                elif kind == "pause_end":
                    gaps.append(
                        {
                            "ts_ms": event.ts_ms,
                            "reason": "pause_end",
                            "dropped": 0,
                        }
                    )
                elif kind == "gap":
                    gaps.append(
                        {
                            "ts_ms": event.ts_ms,
                            "reason": event.meta.get("reason", "asr_queue_full"),
                            "dropped": int(event.meta.get("dropped", 0)),
                        }
                    )
            out.append(
                {
                    "index": index,
                    "started_at_ms": started_at,
                    "ended_at_ms": ended_at,
                    "app_name": app_name,
                    "window_title": window_title,
                    "summary": compiled_summaries.get(index, ""),
                    "utterances": utterances,
                    "selections": selections,
                    "keyframes": keyframes,
                    "gaps": gaps,
                }
            )
        return out


__all__ = ["JsonExporter"]
