"""ASR provider adapters.

Exports all built-in ASR providers.
"""

from .base import ASRProvider
from .faster_whisper import FasterWhisperProvider
from .openai_compatible import OpenAICompatibleASRProvider

BUILTIN_ASR_PROVIDERS = {
    "faster_whisper": FasterWhisperProvider,
    "openai_compatible": OpenAICompatibleASRProvider,
}

__all__ = [
    "ASRProvider",
    "FasterWhisperProvider",
    "OpenAICompatibleASRProvider",
    "BUILTIN_ASR_PROVIDERS",
]
