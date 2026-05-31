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
