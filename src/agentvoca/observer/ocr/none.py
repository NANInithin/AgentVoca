"""No-op OCR provider (v0.4.0, OBS-15).

Returns an empty ``OCRResult`` for every keyframe. The keyframe row is
still stored (so the user can see what was on screen), but no OCR
text fills the ``text`` column. Useful as a "stop recording text" mode
or as a fallback when a remote OCR provider is unavailable.
"""

from __future__ import annotations

from typing import Optional

from agentvoca.config.schema import ObserverOCRConfig
from agentvoca.observer.models import OCRResult
from agentvoca.observer.ocr.base import OCRProvider


class NoneOCRProvider(OCRProvider):
    """No-op OCR. Every keyframe yields an empty ``OCRResult``."""

    def __init__(self, config: ObserverOCRConfig) -> None:
        super().__init__(config)

    async def extract(self, image_jpeg: bytes, *, hint: Optional[str] = None) -> OCRResult:
        return OCRResult(
            text="",
            confidence=None,
            latency_ms=0,
            engine="none",
        )
