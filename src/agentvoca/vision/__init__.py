"""Vision (screenshot-to-text) providers (v3).

Exports all built-in vision providers and the anchor splicer.
"""

from agentvoca.vision.anchors import DEFAULT_ANCHOR_PHRASES, AnchorSplicer
from agentvoca.vision.base import VisionProvider
from agentvoca.vision.openai_compatible import OpenAICompatibleVisionProvider

BUILTIN_VISION_PROVIDERS = {
    "openai_compatible": OpenAICompatibleVisionProvider,
}

__all__ = [
    "AnchorSplicer",
    "DEFAULT_ANCHOR_PHRASES",
    "VisionProvider",
    "OpenAICompatibleVisionProvider",
    "BUILTIN_VISION_PROVIDERS",
]
