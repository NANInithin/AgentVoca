"""Event dataclasses for the agentvoca event bus.

All events that can be published on the event bus are defined here.
"""

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class HotkeyEvent:
    """Published when a global hotkey is pressed.

    Attributes:
        action: The hotkey action to perform.
    """

    action: Literal["toggle_recording", "cancel", "open_settings", "insert_last", "undo"]


@dataclass
class AudioFrameEvent:
    """Published for each audio frame during recording.

    Attributes:
        data: Raw audio bytes.
        sample_rate: Sample rate of the audio data.
        timestamp_ms: Timestamp of this frame in milliseconds.
    """

    data: bytes
    sample_rate: int
    timestamp_ms: int


@dataclass
class VADSpeechEvent:
    """Published when VAD detects speech or silence.

    Attributes:
        is_speech: True if speech is detected, False for silence.
        timestamp_ms: Timestamp of the detection event.
    """

    is_speech: bool
    timestamp_ms: int


@dataclass
class RecordingStoppedEvent:
    """Published when recording stops with the captured audio.

    Attributes:
        audio_bytes: Complete audio buffer.
        duration_ms: Duration of the recording in milliseconds.
        sample_rate: Sample rate of the audio data.
    """

    audio_bytes: bytes
    duration_ms: int
    sample_rate: int


@dataclass
class TranscriptEvent:
    """Published when a transcript segment is available.

    Attributes:
        text: The transcribed text.
        is_final: True if this is the final transcript (not interim).
    """

    text: str
    is_final: bool


@dataclass
class CleanedTextEvent:
    """Published when cleanup produces a result.

    Attributes:
        text: The cleaned (or fallback) text.
        used_fallback: True if the raw transcript was used as fallback.
        latency_ms: Time taken for cleanup in milliseconds.
    """

    text: str
    used_fallback: bool
    latency_ms: int


@dataclass
class InsertionCompleteEvent:
    """Published when text insertion completes.

    Attributes:
        success: True if insertion succeeded.
        method_used: The method used ("keyboard" or "clipboard").
        error: Error message if insertion failed, or None.
    """

    success: bool
    method_used: str
    error: Optional[str] = None


@dataclass
class StateChangedEvent:
    """Published when the application state changes.

    Attributes:
        previous: The previous state.
        current: The new state.
    """

    previous: str
    current: str


@dataclass
class ErrorEvent:
    """Published when an error occurs during pipeline processing.

    Attributes:
        stage: The pipeline stage where the error occurred.
        message: Human-readable error message.
        recoverable: True if the pipeline can recover from this error.
        detail: Optional detailed error information.
    """

    stage: str
    message: str
    recoverable: bool
    detail: Optional[str] = None


@dataclass
class TimingEvent:
    """Published when a pipeline stage completes with timing data.

    Attributes:
        stage: The pipeline stage name.
        duration_ms: Duration of the stage in milliseconds.
    """

    stage: str
    duration_ms: int
