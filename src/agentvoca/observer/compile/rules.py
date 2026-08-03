"""Deterministic rules-based session compiler (v0.4.0, Track 3, OBS-21).

The zero-config default. D3 says Observer must produce a genuinely
useful artifact with no API key, exactly as ``cleanup.provider: rules``
does today. If this output is not worth reading, the zero-config promise
is hollow.

Deterministic, no network, no LLM. Produces a markdown document grouped
by ``split_blocks`` boundaries with said / highlighted / on-screen
sections per block. Aggressive OCR dedup keeps the document short;
markdown escaping protects against untrusted OCR text.

The same algorithm is reused by ``OpenAICompatibleCompiler`` for any
block whose LLM call fails (degraded rendering), so the markdown and
JSON sidecar block boundaries are guaranteed to match.
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import Iterable

from agentvoca import __version__
from agentvoca.observer.compile.base import SessionCompiler, block_window, split_blocks
from agentvoca.observer.models import CompiledSession, ObserverEvent, SessionBundle

logger = logging.getLogger(__name__)


# Limits from the OBS-21 spec.
_OCR_MAX_CHARS = 200
_SELECTION_MAX_CHARS = 500
_OCR_LINES_PER_KEYFRAME = 2

# Pause-reason -> human label. Kept in one place so the rules compiler
# and the JSON exporter render identically.
_PAUSE_REASON_LABEL = {
    "hotkey": "capture paused (hotkey)",
    "excluded_app": "capture paused (excluded app in foreground)",
    "disk_cap": "capture paused (session disk cap reached)",
}

# Markdown-significant characters. ``_escape_md`` mangles all of them in
# a single pass so an OCR string of ``a|b \`c\` _d_`` cannot break the
# table, blockquote, or emphasis rendering.
_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|>~=])")


def _escape_md(text: str) -> str:
    """Escape markdown-significant characters in ``text``."""
    if not text:
        return ""
    return _MD_SPECIAL.sub(r"\\\1", text)


def _local_time(ts_ms: int) -> datetime.datetime:
    """Convert epoch ms to a local-time ``datetime`` (for HH:MM headers)."""
    return datetime.datetime.fromtimestamp(ts_ms / 1000.0).astimezone()


def _fmt_hhmm(ts_ms: int) -> str:
    """Format ``ts_ms`` as ``HH:MM`` in local time."""
    return _local_time(ts_ms).strftime("%H:%M")


def _fmt_date(ts_ms: int) -> str:
    """Format ``ts_ms`` as a human-readable date, e.g. ``28 Jul 2026``."""
    return _local_time(ts_ms).strftime("%d %b %Y")


def _fmt_duration(ms: int) -> str:
    """Format a duration in ms as ``H h M m`` (with zero-hours elided)."""
    if ms < 0:
        ms = 0
    total_minutes = ms // 60_000
    hours, minutes = divmod(total_minutes, 60)
    if hours and minutes:
        return f"{hours} h {minutes} m"
    if hours:
        return f"{hours} h"
    return f"{minutes} m"


def _truncate(text: str, max_chars: int) -> str:
    """Truncate ``text`` to ``max_chars``, appending an ellipsis if cut."""
    if not text or len(text) <= max_chars:
        return text or ""
    return text[: max_chars - 1].rstrip() + "\u2026"


def _first_non_empty_lines(text: str, count: int) -> list[str]:
    """Return the first ``count`` non-empty lines of ``text`` (preserving order)."""
    if not text:
        return []
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        out.append(stripped)
        if len(out) >= count:
            break
    return out


def _dedup_lines(lines: Iterable[str]) -> list[str]:
    """De-duplicate ``lines`` preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def _pluralize(n: int, singular: str, plural: str | None = None) -> str:
    """Return ``f"{n} {singular}"`` or ``f"{n} {plural}"`` per English rules."""
    if n == 1:
        return f"{n} {singular}"
    return f"{n} {plural or (singular + 's')}"


def _render_header(
    session: object,
    total_duration_ms: int,
    app_names: list[str],
    block_count: int,
    started_at: int,
    ended_at: int,
) -> str:
    """Render the document header + stats line.

    ``started_at`` and ``ended_at`` are the event-boundary timestamps so
    the header always matches the events shown below it (the session
    metadata can drift from the events when, e.g., a fixture sets a
    fixed base for events but a runtime ``_now_ms()`` for the session
    row).
    """
    del session  # unused now that events drive the header
    date_part = _fmt_date(started_at)
    started = _fmt_hhmm(started_at)
    ended = _fmt_hhmm(ended_at) if ended_at else "?"
    apps = ", ".join(app_names) if app_names else "none"
    duration = _fmt_duration(total_duration_ms)
    title = f"# Session \u2014 {date_part}, {started}\u2013{ended}"
    stats = f"**Duration:** {duration} \u00b7 **Apps:** {apps} \u00b7 **Captures:** {block_count}"
    return f"{title}\n\n{stats}\n\n---"


def _render_empty_session(bundle: SessionBundle) -> CompiledSession:
    """Render a stub for a session that has zero events."""
    started_at = bundle.session.started_at_ms or 0
    ended_at = bundle.session.ended_at_ms or started_at
    if started_at:
        end_part = _fmt_hhmm(ended_at) if ended_at else "?"
        title = f"# Session \u2014 {_fmt_date(started_at)}, {_fmt_hhmm(started_at)}\u2013{end_part}"
    else:
        title = "# Session"
    markdown = (
        f"{title}\n\n"
        "_No events were recorded in this session._\n\n---\n\n"
        f"*Compiled by AgentVoca v{__version__} \u00b7 rules compiler \u00b7 no LLM used*"
    )
    return CompiledSession(
        markdown=markdown,
        summary="Empty session (0 spoken lines across 0 apps).",
        blocks=[],
        provider="rules",
        degraded=False,
    )


def _render_block(block: list[ObserverEvent], index: int) -> tuple[str, dict]:
    """Render a single block.

    Returns:
        ``(markdown, block_record)`` where ``block_record`` matches the
        ``blocks[]`` shape in contracts \xa75.
    """
    started_at, ended_at = block_window(block)
    # Pick the most recent focus_change's app_name and window_title. A
    # focus_change is the first event of every normal block.
    app_name = ""
    window_title = ""
    for event in block:
        if event.app_name:
            app_name = event.app_name
        if event.window_title:
            window_title = event.window_title
    if not app_name and block:
        # Fall back to whatever the first event had.
        app_name = block[0].app_name or ""
    if not window_title and block:
        window_title = block[0].window_title or ""

    header_range = f"{_fmt_hhmm(started_at)} \u2013 {_fmt_hhmm(ended_at)}"
    header = f"## {header_range} \u00b7 {app_name or 'unknown'}"
    if window_title:
        sub = f"### {_escape_md(window_title)}"
    else:
        sub = ""

    # Collect per-kind events. Order within a kind is preserved.
    utterances: list[ObserverEvent] = []
    selections: list[ObserverEvent] = []
    keyframes: list[ObserverEvent] = []
    pauses: list[dict] = []  # {ts, kind, reason, pattern, dropped}

    for event in block:
        kind = event.kind
        if kind == "utterance_ambient" or kind == "utterance_dictated":
            utterances.append(event)
        elif kind == "selection":
            selections.append(event)
        elif kind == "keyframe":
            keyframes.append(event)
        elif kind == "pause_start":
            reason = event.meta.get("reason", "hotkey")
            pauses.append(
                {
                    "ts_ms": event.ts_ms,
                    "kind": "pause_start",
                    "reason": reason,
                    "pattern": event.meta.get("pattern"),
                }
            )
        elif kind == "pause_end":
            pauses.append(
                {
                    "ts_ms": event.ts_ms,
                    "kind": "pause_end",
                    "reason": event.meta.get("reason", "hotkey"),
                }
            )
        elif kind == "gap":
            pauses.append(
                {
                    "ts_ms": event.ts_ms,
                    "kind": "gap",
                    "reason": event.meta.get("reason", "asr_queue_full"),
                    "dropped": int(event.meta.get("dropped", 0)),
                }
            )

    # Build the per-block JSON record.
    block_record = {
        "index": index,
        "started_at_ms": started_at,
        "ended_at_ms": ended_at,
        "app_name": app_name,
        "window_title": window_title,
        "summary": "",  # rules compiler leaves this empty; LLM compiler fills it.
        "utterances": [
            {
                "ts_ms": e.ts_ms,
                "text": e.text or "",
                "source": "dictated" if e.kind == "utterance_dictated" else "ambient",
            }
            for e in utterances
        ],
        "selections": [
            {
                "ts_ms": e.ts_ms,
                "text": e.text or "",
                "method": e.meta.get("method", "uia"),
                "truncated": bool(e.meta.get("truncated", False)),
            }
            for e in selections
        ],
        "keyframes": [
            {
                "ts_ms": e.ts_ms,
                "blob_path": e.blob_path or "",
                "trigger": e.meta.get("trigger", "window_change"),
                "ocr_text": e.text or "",
            }
            for e in keyframes
        ],
        "gaps": [],
    }

    chunks: list[str] = []
    chunks.append(header)
    if sub:
        chunks.append(sub)

    # Said
    if utterances:
        chunks.append("**Said**")
        for u in utterances:
            text = _escape_md((u.text or "").strip())
            if not text:
                continue
            marker = _fmt_hhmm(u.ts_ms)
            chunks.append(f"- {marker} \u2014 {text}")

    # Highlighted
    if selections:
        chunks.append("**Highlighted**")
        for s in selections:
            text = _truncate(s.text or "", _SELECTION_MAX_CHARS)
            text_esc = _escape_md(text)
            chunks.append(f"> {text_esc}")

    # On screen
    if keyframes:
        chunks.append(f"**On screen** *({_pluralize(len(keyframes), 'capture')})*")
        # Aggressive dedup: take the first N non-empty lines from each
        # keyframe and drop lines we've already shown earlier in this
        # block. Raw OCR dumps make the document unreadable; this is the
        # single fastest way to make the output worth reading.
        shown: set[str] = set()
        for kf in keyframes:
            lines = _first_non_empty_lines(kf.text or "", _OCR_LINES_PER_KEYFRAME)
            new_lines = [line for line in lines if line not in shown]
            shown.update(lines)
            if not new_lines:
                continue
            marker = _fmt_hhmm(kf.ts_ms)
            joined = _truncate(" | ".join(new_lines), _OCR_MAX_CHARS)
            chunks.append(f"- {marker} \u2014 {_escape_md(joined)}")

    # Gaps / pauses. Render as a single blockquote with the time range
    # and the reason, unmissable.
    if pauses:
        rendered: list[str] = []
        for p in pauses:
            ts = _fmt_hhmm(p["ts_ms"])
            if p["kind"] == "pause_start":
                rendered.append(f"{ts} \u2014 {_PAUSE_REASON_LABEL.get(p['reason'], p['reason'])}")
                block_record["gaps"].append(
                    {
                        "ts_ms": p["ts_ms"],
                        "reason": f"pause_{p['reason']}",
                        "dropped": 0,
                    }
                )
            elif p["kind"] == "pause_end":
                rendered.append(f"{ts} \u2014 capture resumed")
            elif p["kind"] == "gap":
                noun = "item" if p["dropped"] == 1 else "items"
                rendered.append(f"{ts} \u2014 data dropped ({p['reason']}, {p['dropped']} {noun})")
                block_record["gaps"].append(
                    {
                        "ts_ms": p["ts_ms"],
                        "reason": p["reason"],
                        "dropped": p["dropped"],
                    }
                )
        for line in rendered:
            chunks.append(f"> \u26a0\ufe0f {line}")

    return "\n\n".join(c for c in chunks if c), block_record


class RulesCompiler(SessionCompiler):
    """Zero-config, deterministic session compiler.

    Produces a markdown document grouped by ``split_blocks`` boundaries.
    ``degraded`` is always ``False``; ``summary`` is a one-line
    deterministic statistic \u2014 enough to fill the JSON field without
    pretending to be an LLM summary.
    """

    async def compile(self, bundle: SessionBundle) -> CompiledSession:
        """Render a session as a markdown document.

        The same algorithm is reused by the LLM compiler for any block
        whose LLM call fails (degraded rendering). Pure deterministic:
        the same bundle always produces byte-identical output, which is
        what the test golden file relies on.
        """
        events = bundle.events
        if not events:
            return _render_empty_session(bundle)

        # Header stats computed from the bundle, not guessed. The session
        # metadata (``bundle.session.started_at_ms`` / ``ended_at_ms``) is
        # set by ``ObserverStore.open_session`` / ``close_session`` at the
        # time of the API call, which can drift from the actual event
        # timestamps (e.g. the test fixture opens the session at the
        # current wall-clock time but writes events at a fixed base). Use
        # the event boundaries so the rendered header always matches the
        # events shown below it and so the output is byte-identical
        # across runs.
        started_at = events[0].ts_ms
        ended_at = events[-1].ts_ms
        duration_ms = max(0, ended_at - started_at)

        blocks = split_blocks(bundle)

        # Unique apps in order of first appearance.
        seen_apps: set[str] = set()
        app_names: list[str] = []
        for e in events:
            if e.app_name and e.app_name not in seen_apps:
                seen_apps.add(e.app_name)
                app_names.append(e.app_name)

        header = _render_header(
            session=bundle.session,
            total_duration_ms=duration_ms,
            app_names=app_names,
            block_count=len(blocks),
            started_at=started_at,
            ended_at=ended_at,
        )

        # Per-block markdown.
        block_markdowns: list[str] = []
        block_records: list[dict] = []
        for i, block in enumerate(blocks):
            md, record = _render_block(block, index=i)
            block_markdowns.append(md)
            block_records.append(record)

        body = "\n\n---\n\n".join(block_markdowns)

        spoken = sum(1 for e in events if e.kind in ("utterance_ambient", "utterance_dictated"))
        summary = (
            f"{_pluralize(spoken, 'spoken line', 'spoken lines')} across "
            f"{_pluralize(len(app_names), 'app', 'apps')} over "
            f"{_fmt_duration(duration_ms)}."
        )

        markdown = (
            f"{header}\n\n{body}\n\n---\n\n"
            f"*Compiled by AgentVoca v{__version__} \u00b7 rules compiler \u00b7 no LLM used*"
        )

        return CompiledSession(
            markdown=markdown,
            summary=summary,
            blocks=block_records,
            provider="rules",
            degraded=False,
        )


__all__ = [
    "RulesCompiler",
    "_render_block",  # used by the LLM compiler for degraded rendering
]
