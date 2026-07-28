"""Frozen data models for Observer mode (v0.4.0).

Pure data. No I/O, no behavior, no imports from other observer modules.
Every other observer module may import this one; this one imports nothing
from observer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

# Every value ``events.kind`` may take. Adding a member is an additive change
# that must be announced; renaming one is not permitted.
EventKind = Literal[
    "utterance_ambient",  # speech captured while not dictating
    "utterance_dictated",  # speech captured via the dictation hotkey
    "keyframe",  # a screenshot + its OCR text
    "selection",  # text the user highlighted
    "focus_change",  # foreground app or window title changed
    "pause_start",  # capture suspended (hotkey, exclusion, or disk cap)
    "pause_end",  # capture resumed
    "gap",  # data was intentionally dropped; reason in meta
]

SessionStatus = Literal["open", "closed", "compiled", "abandoned"]

# Why a keyframe was requested. Recorded in ``meta["trigger"]``.
TriggerReason = Literal["window_change", "scroll_settle", "click", "selection", "speech_onset"]


@dataclass(frozen=True)
class ObserverEvent:
    """One row in the session timeline.

    Attributes:
        id: Database row id. 0 for an event that has not been written yet.
        session_id: Owning session row id.
        ts_ms: Unix epoch milliseconds. Monotonically non-decreasing within a
            session (the store enforces this).
        kind: Discriminator; see ``EventKind``.
        app_name: Foreground executable name at capture time (e.g. "chrome.exe").
        window_title: Foreground window title at capture time.
        text: The textual payload. Transcript for utterances, OCR text for
            keyframes, selected text for selections. None until OCR fills it in.
        blob_path: Path to the JPEG, RELATIVE to ``observer.storage.dir``.
            Keyframes only. Relative so the storage dir can be moved.
        meta: Kind-specific extras. Serialized to the ``meta_json`` column.
            See §4 for the per-kind key contract.
    """

    id: int
    session_id: int
    ts_ms: int
    kind: EventKind
    app_name: Optional[str] = None
    window_title: Optional[str] = None
    text: Optional[str] = None
    blob_path: Optional[str] = None
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ObserverSession:
    """A recording session.

    Attributes:
        id: Database row id.
        uuid: Stable external identifier; also the blob subdirectory name.
        started_at_ms: Session open time.
        ended_at_ms: Session close time, or None while open.
        status: See ``SessionStatus``.
        app_version: agentvoca version that produced the session.
        schema_version: Store schema version at write time.
    """

    id: int
    uuid: str
    started_at_ms: int
    ended_at_ms: Optional[int]
    status: SessionStatus
    app_version: str
    schema_version: int


@dataclass(frozen=True)
class SessionBundle:
    """A whole session loaded into memory for compilation.

    ``events`` is ordered by ``(ts_ms, id)`` ascending. Compilers must not
    assume it fits any particular size — see ``blocks()`` in
    ``observer/compile/base.py`` for the chunking helper.
    """

    session: ObserverSession
    events: list[ObserverEvent]


@dataclass(frozen=True)
class OCRResult:
    """Output of an OCRProvider.

    Attributes:
        text: Extracted text, reading order, newline separated. Empty string
            when the image contained no detectable text — this is a SUCCESS,
            not a failure.
        confidence: Mean confidence in [0.0, 1.0], or None if the engine does
            not report one.
        latency_ms: Wall time of the extraction.
        engine: Provider name that produced this ("rapidocr", "openai_compatible").
    """

    text: str
    confidence: Optional[float]
    latency_ms: int
    engine: str


@dataclass(frozen=True)
class Selection:
    """Text the user highlighted on screen.

    Attributes:
        text: The selected text, truncated to ``observer.selection.max_chars``.
        method: How it was obtained — "uia" or "ocr_rect".
        app_name: Foreground app at selection time.
        window_title: Foreground window title at selection time.
        truncated: True if ``text`` was cut at max_chars.
    """

    text: str
    method: Literal["uia", "ocr_rect"]
    app_name: Optional[str]
    window_title: Optional[str]
    truncated: bool = False


@dataclass(frozen=True)
class Grab:
    """A captured screen region, already encoded.

    Attributes:
        jpeg: JPEG-encoded bytes, already downscaled.
        width: Encoded width in pixels.
        height: Encoded height in pixels.
        dhash: 64-bit difference hash of the image, for dedup.
        app_name: Foreground app at grab time.
        window_title: Foreground window title at grab time.
    """

    jpeg: bytes
    width: int
    height: int
    dhash: int
    app_name: Optional[str]
    window_title: Optional[str]


@dataclass(frozen=True)
class CompiledSession:
    """Output of a SessionCompiler.

    Attributes:
        markdown: The full rendered markdown document.
        summary: One-paragraph session summary. Empty string for the ``none``
            provider.
        blocks: Structured per-block records for the JSON sidecar. Each dict
            must match the ``blocks[]`` shape in §5.
        provider: Which compiler produced this.
        degraded: True if any block fell back to the rules rendering because
            an LLM call failed. Surfaced to the user so a partial result is
            never presented as a complete one.
    """

    markdown: str
    summary: str
    blocks: list[dict]
    provider: str
    degraded: bool = False
