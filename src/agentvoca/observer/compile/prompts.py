"""System prompt templates for the Observer session compiler (v0.4.0).

Used by ``OpenAICompatibleCompiler`` to ask a remote LLM for a
narrative per block and a one-paragraph session summary. Block and
session prompts are kept separate so the model can never see the raw
event log and so the two are easy to evolve independently.

A chatty model is told to emit only safe markdown (no top-level
headings, no code fences) so a malicious or buggy response cannot
break the document structure.
"""

from __future__ import annotations

# Per-block: ask for a short narrative paragraph plus a 1-2 line
# ``summary`` field. The block markdown lives under the section header
# we already rendered, so the model only fills the BODY of the
# section \u2014 it cannot open a new ``##`` heading.
_BLOCK_SYSTEM_PROMPT = (
    "You are summarizing one block of a recorded work session for the "
    "user's personal notes. The block is a contiguous stretch of work "
    "in a single app.\n"
    "\n"
    "Output two things, in this order:\n"
    "1. A short narrative paragraph (2-4 sentences) describing what "
    "the user was doing in this block, written in third person. "
    "Reference only what is grounded in the input \u2014 do not invent.\n"
    "2. A single line starting with ``SUMMARY:`` followed by a "
    "1-2 sentence summary suitable for a JSON field.\n"
    "\n"
    "Rules you must follow without exception:\n"
    "- Do not include markdown headings (``#``, ``##``, ``###``). The "
    "section header is already rendered.\n"
    "- Do not wrap the response in a code fence.\n"
    "- Do not invent, add, or remove events, app names, file paths, or "
    "numbers.\n"
    "- Preserve all code identifiers, file paths, URLs, and version "
    "strings exactly.\n"
    "- Be concise. The user has limited patience for an LLM that "
    "pads."
)

# Session: ask for a one-paragraph session summary grounded in the
# per-block summaries. The model only sees the per-block summaries,
# never the raw events \u2014 RK7.
_SESSION_SYSTEM_PROMPT = (
    "You are writing a one-paragraph session summary for the user's "
    "personal notes. The input is a list of per-block summaries, one "
    "per app, in chronological order.\n"
    "\n"
    "Write a single paragraph (3-5 sentences) that ties the blocks "
    "together into a coherent narrative. Do not invent any facts not "
    "in the input. Do not add bullet points or headings. The output "
    "goes into a JSON field, so no code fences, no markdown headings."
)


def get_block_prompt() -> str:
    """Return the system prompt for per-block summarization."""
    return _BLOCK_SYSTEM_PROMPT


def get_session_prompt() -> str:
    """Return the system prompt for session-level summarization."""
    return _SESSION_SYSTEM_PROMPT


def strip_unsafe_markdown(text: str) -> str:
    """Strip leading/trailing code fences and any heading above ``###``.

    A model response wrapped in ```` ```markdown ```` would otherwise
    show up in the rendered document as a code block; a chatty model
    that emits ``## Foo`` would break the block structure the
    compiler already established. Belt-and-braces cleanup so neither
    failure mode is possible.
    """
    if not text:
        return ""
    # Strip a leading code fence with optional language tag.
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].lstrip().startswith("```"):
        lines = lines[:-1]
    cleaned = "\n".join(lines).strip()
    # Demote any heading above ``###``. The compiler already rendered
    # the ``##`` block header, so anything else is an attempt to
    # restructure the document.
    demoted: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") and not stripped.startswith("###"):
            prefix_len = len(line) - len(stripped)
            # Find the run of ``#``s at the start of the content.
            i = 0
            while i < len(stripped) and stripped[i] == "#":
                i += 1
            # If the run is 1 or 2 ``#``s, demote to ``###`` (or
            # ``####`` if it was already two, to keep order).
            if i in (1, 2):
                rest = stripped[i:].lstrip()
                new_prefix = "###" if i == 1 else "####"
                demoted.append(" " * prefix_len + f"{new_prefix} {rest}")
                continue
        demoted.append(line)
    return "\n".join(demoted).strip()


__all__ = [
    "get_block_prompt",
    "get_session_prompt",
    "strip_unsafe_markdown",
]
