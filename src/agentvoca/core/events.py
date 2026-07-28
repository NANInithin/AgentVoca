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

    action: Literal[
        "toggle_recording",
        "cancel",
        "open_settings",
        "insert_last",
        "undo",
        "capture_screenshot",
        "toggle_observer",
        "pause_observer",
    ]


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
class AudioChunkEvent:
    """Published by the AudioChunker during recording (Chunker → Bus).

    Attributes:
        data: Raw PCM audio bytes for the chunk.
        sample_rate: Sample rate of the audio data.
        timestamp_ms: Timestamp of this chunk in milliseconds.
        is_flush: True on the final flush at recording stop.
    """

    data: bytes
    sample_rate: int
    timestamp_ms: int
    is_flush: bool = False


@dataclass
class PartialTranscriptEvent:
    """Published when a streaming partial transcript is available.

    Attributes:
        text: Cumulative interim text for overlay display.
    """

    text: str


@dataclass
class SegmentFinalizedEvent:
    """Published when a streaming ASR segment is finalized.

    Attributes:
        text: The finalized segment text.
        index: Order of the finalized segment.
    """

    text: str
    index: int


@dataclass
class WarmupCompleteEvent:
    """Published when background warm-up completes.

    Attributes:
        asr_ready: True if ASR warm-up succeeded.
        cleanup_ready: True if cleanup warm-up succeeded.
        duration_ms: Total warm-up duration in milliseconds.
    """

    asr_ready: bool
    cleanup_ready: bool
    duration_ms: int


@dataclass
class ContextResolvedEvent:
    """Published when the context engine resolves the current context.

    Attributes:
        app_name: Name of the currently active application, or None.
        style: Resolved style profile, or None.
        language: Resolved language hint, or None.
    """

    app_name: Optional[str] = None
    style: Optional[str] = None
    language: Optional[str] = None


@dataclass
class CommandRecognizedEvent:
    """Published when a voice command is recognized.

    Attributes:
        action: The command action that was matched.
        original_text: The original transcript text before command processing.
    """

    action: str
    original_text: str


@dataclass
class CorrectionLearnedEvent:
    """Published when a correction is learned by the adaptive vocab.

    Attributes:
        wrong: The original (wrong) text that was corrected.
        right: The corrected text.
        promoted: True if the correction crossed the promote_threshold.
    """

    wrong: str
    right: str
    promoted: bool = False


@dataclass
class ScreenshotCapturedEvent:
    """Published when a screenshot is captured during a dictation session (v3).

    Attributes:
        index: Zero-based order of this capture within the current session.
        width: Pixel width of the captured image, or None if unknown.
        height: Pixel height of the captured image, or None if unknown.
    """

    index: int
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class VisionExtractedEvent:
    """Published when vision extraction completes for the captured screenshots (v3).

    Attributes:
        count: Number of screenshots successfully extracted.
        anchors_matched: Number of anchor phrases matched in the transcript.
        latency_ms: Total extraction time in milliseconds.
    """

    count: int
    anchors_matched: int
    latency_ms: int


@dataclass
class TimingEvent:
    """Published when a pipeline stage completes with timing data.

    Attributes:
        stage: The pipeline stage name.
        duration_ms: Duration of the stage in milliseconds.
    """

    stage: str
    duration_ms: int


# ── v0.4.0: Observer mode events ───────────────────────────────────
# All six are declared here in a single commit even though Track 1 only
# publishes two of them. The other tracks never open this file because
# their events are already in place.


@dataclass
class ObserverSessionStartedEvent:
    """Published when a session opens. Attributes: session_uuid, session_id, started_at_ms.

    Attributes:
        session_uuid: Stable external identifier for the session.
        session_id: Owning row id in the sessions table.
        started_at_ms: Unix epoch milliseconds the session was opened.
    """

    session_uuid: str
    session_id: int
    started_at_ms: int


@dataclass
class ObserverSessionEndedEvent:
    """Published when a session closes, before compilation begins.

    Attributes:
        session_uuid: Stable external identifier for the session.
        session_id: Owning row id in the sessions table.
        duration_ms: Wall-clock duration of the session.
        event_count: Number of timeline events stored in the session.
    """

    session_uuid: str
    session_id: int
    duration_ms: int
    event_count: int


@dataclass
class ObserverPausedEvent:
    """Published on pause/resume. ``paused`` False means resumed.

    Attributes:
        paused: True when capture is suspended, False when it has resumed.
        reason: Why the state changed ("hotkey" | "excluded_app" | "disk_cap").
    """

    paused: bool
    reason: str


@dataclass
class ObserverKeyframeEvent:
    """Published when a keyframe is stored (before OCR completes).

    Attributes:
        event_id: Row id of the keyframe event in the events table.
        trigger: The trigger that requested this keyframe; see TriggerReason.
        app_name: Foreground app at capture time, or None if unknown.
        deduped: True if the keyframe was dropped because it matched a
            previous frame's perceptual hash.
    """

    event_id: int
    trigger: str
    app_name: Optional[str] = None
    deduped: bool = False


@dataclass
class ObserverUtteranceEvent:
    """Published when an utterance is transcribed and stored.

    Attributes:
        text: The transcribed text.
        source: Where the utterance came from ("ambient" | "dictated").
        duration_ms: Wall-clock duration of the utterance.
    """

    text: str
    source: str
    duration_ms: int


@dataclass
class ObserverCompiledEvent:
    """Published when compilation finishes.

    Attributes:
        session_uuid: Stable external identifier for the session.
        markdown_path: Path to the rendered markdown document.
        json_path: Path to the JSON sidecar, or None when "json" is not
            in compile.formats.
        degraded: True if any block fell back to the rules rendering
            because an LLM call failed.
        latency_ms: Wall-clock duration of the compilation.
    """

    session_uuid: str
    markdown_path: str
    json_path: Optional[str]
    degraded: bool
    latency_ms: int
