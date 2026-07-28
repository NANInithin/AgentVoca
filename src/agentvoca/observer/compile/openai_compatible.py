"""OpenAI-compatible LLM session compiler (v0.4.0, Track 3, OBS-22).

Two-phase rolling summarization (RK7):

1. Per block: send that block's utterances, selections, and deduped
   OCR (token-budgeted) and ask for a short narrative paragraph plus
   a one-line ``SUMMARY:`` field. Blocks are independent -> run with
   ``asyncio.gather``, order-preserving, per-block error isolation.
2. Session: send the per-block summaries only (never the raw events)
   and ask for the one-paragraph session summary.

Degradation is a hard requirement. If a block's LLM call fails, render
that block with the rules compiler for the affected block only, mark
``degraded=True``, and continue. A user who just recorded an hour of
work always gets an artifact.

The block markdown from the LLM is untrusted output: a chatty model
that emits ``## Foo`` would break the document structure, so
``prompts.strip_unsafe_markdown`` sanitises it before insertion.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx

from agentvoca.config.schema import ObserverCompileConfig
from agentvoca.observer.compile.base import SessionCompiler, block_window, split_blocks
from agentvoca.observer.compile.prompts import (
    get_block_prompt,
    get_session_prompt,
    strip_unsafe_markdown,
)
from agentvoca.observer.compile.rules import _render_block
from agentvoca.observer.models import CompiledSession, ObserverEvent, SessionBundle

logger = logging.getLogger(__name__)


# Per-block LLM input is token-budgeted; the actual cost depends on the
# model, so this is a *character* budget that roughly tracks the per-block
# prompt the plan describes (~2000 tokens in).
_BLOCK_CHAR_BUDGET = 8_000


def _serialise_block_for_llm(block: list[ObserverEvent]) -> str:
    """Render a block as a compact JSON-ish text for the LLM.

    Token-budgeted: stops adding OCR text once the running total
    crosses ``_BLOCK_CHAR_BUDGET``. The exact character count is
    irrelevant; the goal is "small enough that any reasonable model
    stays inside its context".
    """
    if not block:
        return "(empty block)"

    started_at, ended_at = block_window(block)
    app = next((e.app_name for e in block if e.app_name), "unknown")
    title = next((e.window_title for e in block if e.window_title), "")

    lines: list[str] = [
        f"App: {app}",
        f"Window title: {title or '(none)'}",
        f"Block window: {started_at} -> {ended_at} ms",
        "",
    ]

    char_count = sum(len(line) for line in lines)
    for event in block:
        if char_count > _BLOCK_CHAR_BUDGET:
            lines.append("... (further events omitted for length)")
            break
        kind = event.kind
        ts = event.ts_ms
        if kind in ("utterance_ambient", "utterance_dictated"):
            source = "dictated" if kind == "utterance_dictated" else "ambient"
            lines.append(f"[{ts}] [said/{source}] {event.text or ''}")
        elif kind == "selection":
            text = event.text or ""
            lines.append(f"[{ts}] [highlighted] {text}")
        elif kind == "keyframe":
            ocr = (event.text or "").strip()
            trigger = event.meta.get("trigger", "window_change")
            # Only the first 2 non-empty OCR lines so we don't blow
            # the budget.
            ocr_lines = [ln for ln in ocr.splitlines() if ln.strip()][:2]
            ocr_excerpt = " | ".join(ocr_lines)
            lines.append(f"[{ts}] [on_screen/{trigger}] {ocr_excerpt}")
        elif kind == "pause_start":
            reason = event.meta.get("reason", "hotkey")
            lines.append(f"[{ts}] [pause_start] reason={reason}")
        elif kind == "pause_end":
            lines.append(f"[{ts}] [pause_end]")
        elif kind == "gap":
            reason = event.meta.get("reason", "asr_queue_full")
            dropped = int(event.meta.get("dropped", 0))
            lines.append(f"[{ts}] [gap] reason={reason} dropped={dropped}")
        elif kind == "focus_change":
            prev = event.meta.get("previous_app", "")
            lines.append(f"[{ts}] [focus_change] app={event.app_name} prev={prev}")
        char_count = sum(len(line) for line in lines)

    return "\n".join(lines)


def _parse_block_response(text: str) -> tuple[str, str]:
    """Split an LLM response into ``(body, summary_line)``.

    The block prompt asks for a paragraph and a single ``SUMMARY:``
    line. If the model omitted the marker, the whole response is
    treated as the body and the summary is empty.
    """
    if not text:
        return "", ""
    body_lines: list[str] = []
    summary = ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("SUMMARY:"):
            summary = stripped.split(":", 1)[1].strip()
        else:
            body_lines.append(line)
    return "\n".join(body_lines).strip(), summary


class OpenAICompatibleCompiler(SessionCompiler):
    """LLM session compiler for any OpenAI-compatible /v1/chat/completions endpoint.

    Reuses the same HTTP pattern as
    ``agentvoca.cleanup.openai_compatible.OpenAICompatibleCleanupProvider``
    (R8: persistent ``httpx.AsyncClient`` with ``keepalive_expiry=30.0``,
    soft ``shutdown()`` contract).

    If a per-block call fails, the block is rendered with the rules
    compiler for that block only; ``degraded=True`` is set so the user
    is never shown a partially-compiled document as if it were complete.
    """

    def __init__(self, config: ObserverCompileConfig) -> None:
        super().__init__(config)
        self._endpoint = config.endpoint or "https://api.openai.com/v1"
        self._model = config.model or "gpt-4o-mini"
        self._api_key: str | None = None
        if config.api_key_env:
            self._api_key = os.environ.get(config.api_key_env)
        self._client = self._make_client(timeout=60.0)

    def _make_client(self, *, timeout: float) -> httpx.AsyncClient:
        """Build the persistent HTTP client. Exposed as a seam for tests."""
        return httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=4,
                max_keepalive_connections=4,
                keepalive_expiry=30.0,
            ),
        )

    async def shutdown(self) -> None:
        """Close the pooled HTTP client. Safe to call more than once."""
        try:
            await self._client.aclose()
        except Exception:
            logger.debug("OpenAICompatibleCompiler shutdown: aclose failed", exc_info=True)

    # ── HTTP seam ──────────────────────────────────────────────────

    async def _chat(self, system: str, user: str) -> str:
        """Send a chat-completion request and return the assistant text.

        Exposed as a seam so tests can monkey-patch it without going
        through ``httpx``. Raises on transport or HTTP error.
        """
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        url = f"{self._endpoint.rstrip('/')}/chat/completions"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        response = await self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        return str(result["choices"][0]["message"]["content"])

    # ── Compilation ───────────────────────────────────────────────

    async def _compile_one_block(
        self, block: list[ObserverEvent], index: int
    ) -> tuple[str, str, dict]:
        """Compile one block. Returns ``(markdown, summary, block_record)``.

        On HTTP failure, the block is rules-rendered for that block
        only and the returned ``summary`` is the empty string. The
        caller collects the failure count so the session-level
        ``degraded`` flag is set when any block fell back.
        """
        block_started_at, block_ended_at = block_window(block)
        rendered_md, block_record = _render_block(block, index=index)

        try:
            user_input = _serialise_block_for_llm(block)
            raw = await self._chat(get_block_prompt(), user_input)
            body, summary_line = _parse_block_response(raw)
            body = strip_unsafe_markdown(body)
        except Exception as exc:  # noqa: BLE001 - we want any failure to fall back
            logger.warning(
                "LLM block %d failed (%s); falling back to rules rendering",
                index,
                exc,
            )
            return rendered_md, "", block_record

        # Stitch: the LLM body goes ABOVE the deterministic per-block
        # sections (Said / Highlighted / On screen) so the user gets
        # both the narrative and the raw data. If the model emitted
        # nothing usable, just use the rules rendering as-is.
        if body:
            final_md = f"{body}\n\n{rendered_md}"
        else:
            final_md = rendered_md

        block_record = dict(block_record)
        block_record["summary"] = summary_line
        return final_md, summary_line, block_record

    async def compile(self, bundle: SessionBundle) -> CompiledSession:
        """Compile a session. Never raises.

        Per-block calls run in parallel via ``asyncio.gather``; a
        failure in one block does not affect the others. If every
        block fails, the output equals a pure rules compile but
        ``degraded=True`` is set.
        """
        events = bundle.events
        if not events:
            # No LLM needed for an empty session. Use the rules stub
            # directly.
            from agentvoca.observer.compile.rules import RulesCompiler

            rules = RulesCompiler(self._config)
            return await rules.compile(bundle)

        blocks = split_blocks(bundle)

        # Per-block, in parallel. ``return_exceptions=True`` so a single
        # failure does not cancel the others.
        results = await asyncio.gather(
            *(self._compile_one_block(b, i) for i, b in enumerate(blocks)),
            return_exceptions=True,
        )

        any_degraded = False
        block_markdowns: list[str] = []
        block_records: list[dict] = []
        block_summaries: list[str] = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.warning("Block %d raised during gather (%s); using rules", i, r)
                from agentvoca.observer.compile.rules import RulesCompiler

                md, rec = RulesCompiler(self._config)._render_block(blocks[i], index=i)  # type: ignore[attr-defined]
                block_markdowns.append(md)
                block_records.append(rec)
                block_summaries.append("")
                any_degraded = True
                continue
            md, summary, rec = r
            block_markdowns.append(md)
            block_records.append(rec)
            block_summaries.append(summary)
            if not summary:
                # Means we fell back to rules rendering for this block.
                any_degraded = True

        # Session-level summary, grounded in the per-block summaries
        # only (RK7). If it fails, fall back to a rules-style statistic.
        session_summary = ""
        if any(block_summaries):
            try:
                user_input = json.dumps(block_summaries, ensure_ascii=False, indent=2)
                raw = await self._chat(get_session_prompt(), user_input)
                session_summary = strip_unsafe_markdown(raw).strip()
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "LLM session summary failed (%s); falling back to deterministic", exc
                )
                session_summary = ""
                any_degraded = True

        if not session_summary:
            from agentvoca.observer.compile.rules import RulesCompiler

            rules_compiled = await RulesCompiler(self._config).compile(bundle)
            session_summary = rules_compiled.summary
            any_degraded = True

        # Header is the rules header \u2014 it's deterministic and gives
        # the user the session metadata they need to navigate the file.
        # We then drop the rules "Compiled by" footer since the LLM
        # compiler takes over attribution.
        from agentvoca.observer.compile.rules import RulesCompiler

        rules_full = await RulesCompiler(self._config).compile(bundle)
        # Use the header (first three lines + stats + ``---``) and
        # replace the body. Strip the trailing footer.
        header = rules_full.markdown.split("---\n\n", 1)[0]
        body = "\n\n---\n\n".join(block_markdowns)
        degraded_note = (
            "degraded: some blocks used rules rendering"
            if any_degraded
            else "LLM summarization"
        )
        footer = (
            f"*Compiled by AgentVoca v0.4.0 \u00b7 "
            f"openai_compatible compiler \u00b7 {degraded_note}*"
        )
        markdown = f"{header}\n\n{body}\n\n---\n\n{footer}"

        return CompiledSession(
            markdown=markdown,
            summary=session_summary,
            blocks=block_records,
            provider="openai_compatible",
            degraded=any_degraded,
        )


__all__ = [
    "OpenAICompatibleCompiler",
]
