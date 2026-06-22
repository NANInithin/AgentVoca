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
class VisionContext:
    """Context passed to a vision (VLM) provider for image extraction.

    Attributes:
        instruction: The spoken dictation text, used as the extraction
            instruction so the model infers the desired output format
            (e.g., "make a table of the expenses" → a markdown table).
        preserve_code: If True, the model must preserve code identifiers,
            paths, URLs, and numeric values exactly.
        app_name: Name of the currently active application, for context only.
        output_format: Optional explicit format hint ("markdown", "plain",
            or "auto"). When "auto" (default) the model infers from the
            instruction.
    """

    instruction: str = ""
    preserve_code: bool = True
    app_name: Optional[str] = None
    output_format: str = "auto"


@dataclass
class Screenshot:
    """A captured screenshot awaiting vision extraction.

    Attributes:
        data: Encoded image bytes (PNG).
        mime_type: MIME type of the image data.
    """

    data: bytes
    mime_type: str = "image/png"


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
