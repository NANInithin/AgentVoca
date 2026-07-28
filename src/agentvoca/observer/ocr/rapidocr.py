"""RapidOCR (ONNX) provider (v0.4.0, OBS-16).

The local OCR default — no API key, no network. Rides the ``onnxruntime``
already pulled in transitively by ``silero-vad``, so the dependency
footprint is the rapidocr-onnxruntime wheel (~15 MB of ONNX models
downloaded on first use, not at import).

The engine is constructed lazily on first use so the cold-start
import graph does not pay the cost (R14). Inference runs in
``asyncio.to_thread`` because it is CPU-bound.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import Any, Optional

from PIL import Image

from agentvoca.config.schema import ObserverOCRConfig
from agentvoca.observer.models import OCRResult
from agentvoca.observer.ocr.base import OCRProvider

logger = logging.getLogger(__name__)


class RapidOCRProvider(OCRProvider):
    """Local ONNX OCR. Default provider — no API key, fully offline.

    The engine is constructed lazily on first ``extract()`` and reused
    across calls. Construction loads ~15 MB of ONNX models and must not
    happen at import or registry-construction time (R14).
    """

    def __init__(self, config: ObserverOCRConfig) -> None:
        super().__init__(config)
        self._engine: Any = None
        self._engine_lock = asyncio.Lock()

    def _get_engine(self) -> Any:
        """Return the cached engine, building it on first call.

        The import is inside this method so the module loads without
        pulling ``rapidocr_onnxruntime`` (R14).
        """
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR  # noqa: PLC0415

            # intra_op_num_threads=1: prevent ONNX from spawning one
            # thread per core, which alone would blow the 5% CPU budget.
            self._engine = RapidOCR(intra_op_num_threads=1)
        return self._engine

    async def warm_up(self) -> None:
        """Run a one-off inference on a 64×64 blank to load the model.

        The first real keyframe would otherwise pay the model-load
        latency. Wrapped so a warm-up failure is non-fatal.
        """
        try:
            await asyncio.to_thread(self._warm_up_sync)
        except Exception:
            logger.debug("RapidOCR warm-up failed (non-fatal)", exc_info=True)

    def _warm_up_sync(self) -> None:
        engine = self._get_engine()
        blank = Image.new("RGB", (64, 64), (255, 255, 255))
        buf = io.BytesIO()
        blank.save(buf, format="PNG")
        try:
            engine(buf.getvalue())
        except Exception:
            # warm-up is best-effort
            pass

    async def extract(self, image_jpeg: bytes, *, hint: Optional[str] = None) -> OCRResult:
        """Run OCR on a JPEG. Returns ``OCRResult`` with reading-order text.

        The engine returns ``(boxes, txts, scores)`` per call. We sort
        the lines by box top-left y, then x, and join with newlines. The
        mean of scores is the confidence.
        """
        start = time.perf_counter()
        try:
            # RapidOCR is CPU-bound; do not block the loop.
            result = await asyncio.to_thread(self._extract_sync, image_jpeg)
        except Exception as exc:
            logger.debug("RapidOCR extract failed: %s", exc)
            raise
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        if result is None:
            return OCRResult(text="", confidence=None, latency_ms=elapsed_ms, engine="rapidocr")
        boxes, txts, scores = result
        if not txts:
            return OCRResult(text="", confidence=None, latency_ms=elapsed_ms, engine="rapidocr")
        # Sort by (top_y, left_x) for reading order.
        indexed = list(enumerate(txts))
        if boxes is not None and len(boxes) == len(txts):
            try:
                indexed.sort(
                    key=lambda i_b: (
                        float(i_b[1][0][1]) if i_b[1] else 0.0,  # not used
                        # Use box coords for the sort.
                        0.0,
                    )
                )
            except Exception:
                pass

            # Robust sort: extract (y0, x0) from the first box corner.
            def _key(item: tuple[int, str]) -> tuple[float, float]:
                idx, _txt = item
                if boxes is None or idx >= len(boxes):
                    return (0.0, 0.0)
                try:
                    box = boxes[idx]
                    # Each box is a list of 4 corner points. Take top-left.
                    y0 = float(box[0][1])
                    x0 = float(box[0][0])
                    return (y0, x0)
                except (IndexError, TypeError, ValueError):
                    return (0.0, 0.0)

            ordered = sorted(indexed, key=_key)
            text = "\n".join(t for _, t in ordered)
        else:
            text = "\n".join(txts)
        if scores is not None and len(scores) > 0:
            try:
                mean_score = sum(float(s) for s in scores) / len(scores)
                # Normalise to [0, 1] if the engine returns 0-100.
                if mean_score > 1.0:
                    mean_score = mean_score / 100.0
                confidence: Optional[float] = mean_score
            except (TypeError, ValueError):
                confidence = None
        else:
            confidence = None
        return OCRResult(
            text=text,
            confidence=confidence,
            latency_ms=elapsed_ms,
            engine="rapidocr",
        )

    def _extract_sync(self, image_jpeg: bytes) -> Optional[tuple]:
        """Call the engine synchronously. Returns the (boxes, txts, scores) tuple."""
        engine = self._get_engine()
        return engine(image_jpeg)
