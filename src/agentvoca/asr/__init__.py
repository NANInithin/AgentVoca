"""ASR provider adapters.

Provider classes are imported lazily (PEP 562) so that importing this
package does not pull in ctranslate2/numpy. ``faster_whisper.py`` also
runs ``_register_cuda_dlls()`` at import time — keeping it out of the
cold-start path means a user who picks a cloud ASR provider never pays
for it.
"""
from __future__ import annotations

import importlib

from agentvoca.asr.base import ASRProvider

_LAZY = {
    "FasterWhisperProvider": "agentvoca.asr.faster_whisper",
    "OpenAICompatibleASRProvider": "agentvoca.asr.openai_compatible",
}


def __getattr__(name: str):
    if name == "BUILTIN_ASR_PROVIDERS":
        return {
            "faster_whisper": getattr(
                importlib.import_module(_LAZY["FasterWhisperProvider"]),
                "FasterWhisperProvider",
            ),
            "openai_compatible": getattr(
                importlib.import_module(_LAZY["OpenAICompatibleASRProvider"]),
                "OpenAICompatibleASRProvider",
            ),
        }
    if name in _LAZY:
        return getattr(importlib.import_module(_LAZY[name]), name)
    raise AttributeError(name)


__all__ = [
    "ASRProvider",
    "FasterWhisperProvider",
    "OpenAICompatibleASRProvider",
    "BUILTIN_ASR_PROVIDERS",
]
