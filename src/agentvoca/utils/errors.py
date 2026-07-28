"""Domain exception hierarchy for the AgentVoca application.

All modules surface errors as exceptions defined here.
"""


class AgentVocaError(Exception):
    """Base exception for all AgentVoca errors."""


class ConfigError(AgentVocaError):
    """Raised when configuration loading or validation fails."""


class ASRError(AgentVocaError):
    """Raised when ASR transcription fails."""


class CleanupError(AgentVocaError):
    """Raised when cleanup/rewriting fails."""


class InsertionError(AgentVocaError):
    """Raised when text insertion fails."""


class VisionError(AgentVocaError):
    """Raised when a vision (VLM) extraction fails."""


class CaptureError(AgentVocaError):
    """Raised when screenshot capture fails."""


class AudioError(AgentVocaError):
    """Raised when audio capture or playback fails."""


class ProviderNotFoundError(AgentVocaError):
    """Raised when a requested provider is not registered."""


class ProviderNotAvailableError(AgentVocaError):
    """Raised when a provider exists but is not available (e.g., model not loaded)."""


class HotkeyError(AgentVocaError):
    """Raised when hotkey binding fails."""


class VADError(AgentVocaError):
    """Raised when voice activity detection fails."""


class ObserverError(AgentVocaError):
    """Raised when the Observer subsystem fails to operate.

    Used for store-side failures (writer thread cannot drain, schema
    mismatch, missing root directory) and for lifecycle failures (a
    session cannot be opened because one is already open, a join times
    out, etc). The Observer subsystem is best-effort by design: an
    ObserverError never propagates out of the hot path of the main
    pipeline.
    """
