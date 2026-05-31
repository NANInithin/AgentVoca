"""Shared data types for the agentvoca pipeline.

All dataclasses used across module boundaries are defined here.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class TranscriptSegment:
    """A segment of transcribed speech.

    Attributes:
        text: The transcribed text.
        is_final: True if this segment is complete (not interim).
        confidence: Confidence score between 0 and 1, or None if unavailable.
        language_detected: Language code detected by ASR, or None.
        start_ms: Start time in milliseconds relative to the audio, or None.
        end_ms: End time in milliseconds relative to the audio, or None.
    """

    text: str
    is_final: bool
    confidence: Optional[float] = None
    language_detected: Optional[str] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None


@dataclass
class ASRContext:
    """Context hints passed to an ASR provider.

    Attributes:
        language_hint: Preferred language code (e.g., "en", "fr").
        vocabulary_hints: List of terms the ASR should bias toward.
    """

    language_hint: Optional[str] = None
    vocabulary_hints: list[str] = field(default_factory=list)


@dataclass
class CleanupContext:
    """Context passed to a cleanup provider.

    Attributes:
        style: Cleanup style name (raw, light, standard, technical, professional, custom).
        preserve_code: If True, the provider must preserve code identifiers, paths, URLs.
        vocabulary: List of terms from the user dictionary.
        app_name: Name of the currently active application, for context only.
        custom_prompt: Custom prompt override for the cleanup provider.
    """

    style: str = "standard"
    preserve_code: bool = True
    vocabulary: list[str] = field(default_factory=list)
    app_name: Optional[str] = None
    custom_prompt: Optional[str] = None


@dataclass
class InsertionResult:
    """Result of a text insertion attempt.

    Attributes:
        success: True if the text was inserted successfully.
        method_used: The method used for insertion ("keyboard" or "clipboard").
        error: Error message if insertion failed, or None.
    """

    success: bool
    method_used: Literal["keyboard", "clipboard"]
    error: Optional[str] = None


# Application state literal type
AppState = Literal[
    "idle",
    "recording",
    "transcribing",
    "cleaning",
    "inserting",
    "error",
]
