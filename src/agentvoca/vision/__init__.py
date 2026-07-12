"""Vision (screenshot-to-text) providers (v3).

Exports all built-in vision providers and the anchor splicer. The
``OpenAICompatibleVisionProvider`` is imported lazily (PEP 562) so that
importing this package does not pull in httpx for a user who has not
enabled vision.
"""
from __future__ import annotations

import importlib

from agentvoca.vision.anchors import DEFAULT_ANCHOR_PHRASES, AnchorSplicer
from agentvoca.vision.base import VisionProvider

_LAZY = {
    "OpenAICompatibleVisionProvider": "agentvoca.vision.openai_compatible",
}


def __getattr__(name: str):
    if name == "BUILTIN_VISION_PROVIDERS":
        return {
            "openai_compatible": getattr(
                importlib.import_module(_LAZY["OpenAICompatibleVisionProvider"]),
                "OpenAICompatibleVisionProvider",
            ),
        }
    if name in _LAZY:
        return getattr(importlib.import_module(_LAZY[name]), name)
    raise AttributeError(name)


__all__ = [
    "AnchorSplicer",
    "DEFAULT_ANCHOR_PHRASES",
    "VisionProvider",
    "OpenAICompatibleVisionProvider",
    "BUILTIN_VISION_PROVIDERS",
]
