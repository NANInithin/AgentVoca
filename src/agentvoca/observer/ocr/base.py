"""OCR provider abstract base class (v0.4.0, OBS-15).

Mirrors the conventions of ``agentvoca.asr.base`` and
``agentvoca.vision.base``: constructor takes the typed config block,
``warm_up`` and ``shutdown`` are optional soft contracts, ``extract``
is the single required method.

The contract (see ``docs/proposals/v0.4.0-contracts.md`` §6):
- ``extract`` is async and must NOT raise on a blank image. An image
  with no text is a SUCCESS — return ``OCRResult(text="", ...)``.
- ``extract`` raises only on a genuine engine failure; the caller
  isolates the failure to one keyframe and records
  ``meta["ocr_status"] = "failed"``.
- The ``hint`` argument is an optional context string the provider may
  use to bias its recognition (e.g. a preceding context snippet).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from agentvoca.config.schema import ObserverOCRConfig
from agentvoca.observer.models import OCRResult


class OCRProvider(ABC):
    """Abstract base class for Observer OCR providers."""

    def __init__(self, config: ObserverOCRConfig) -> None:
        self._config = config

    @abstractmethod
    async def extract(self, image_jpeg: bytes, *, hint: Optional[str] = None) -> OCRResult:
        """Extract text from a JPEG.

        Args:
            image_jpeg: JPEG-encoded bytes (the ScreenGrabber's output).
            hint: Optional context string (e.g. a recent utterance).

        Returns:
            An ``OCRResult`` with reading-order text, confidence, latency,
            and engine name. Empty text on a successful no-text image.

        Raises:
            Only on a genuine engine failure. A blank image must NOT
            raise; return ``OCRResult(text="", ...)`` instead.
        """

    async def warm_up(self) -> None:
        """Optional preload. Default: no-op."""

    async def shutdown(self) -> None:
        """Optional soft contract. Default: no-op."""
