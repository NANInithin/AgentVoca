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

        Lines are sorted by box top-left y, then x, and joined with
        newlines. The mean of the per-line scores is the confidence.
        """
        start = time.perf_counter()
        try:
            # RapidOCR is CPU-bound; do not block the loop.
            result = await asyncio.to_thread(self._extract_sync, image_jpeg)
        except Exception as exc:
            logger.debug("RapidOCR extract failed: %s", exc)
            raise
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        lines = _normalize_result(result)
        if not lines:
            return OCRResult(text="", confidence=None, latency_ms=elapsed_ms, engine="rapidocr")

        def _key(line: tuple[Any, str, Any]) -> tuple[float, float]:
            """Reading order: top-left corner of the box, y then x."""
            box = line[0]
            try:
                return (float(box[0][1]), float(box[0][0]))
            except (IndexError, TypeError, ValueError):
                return (0.0, 0.0)

        ordered = sorted(lines, key=_key)
        text = "\n".join(str(t) for _, t, _ in ordered)
        scores = [s for _, _, s in lines if s is not None]
        confidence: Optional[float] = None
        if scores:
            try:
                mean_score = sum(float(s) for s in scores) / len(scores)
                # Normalise to [0, 1] if the engine returns 0-100.
                if mean_score > 1.0:
                    mean_score = mean_score / 100.0
                confidence = mean_score
            except (TypeError, ValueError):
                confidence = None
        return OCRResult(
            text=text,
            confidence=confidence,
            latency_ms=elapsed_ms,
            engine="rapidocr",
        )

    def _extract_sync(self, image_jpeg: bytes) -> Any:
        """Call the engine synchronously. Shape varies; see ``_normalize_result``."""
        engine = self._get_engine()
        return engine(image_jpeg)


def _normalize_result(result: Any) -> list[tuple[Any, str, Any]]:
    """Flatten whatever the engine returned into ``[(box, text, score), …]``.

    ``rapidocr_onnxruntime`` has shipped two different return shapes and
    the pin is ``>=1.4.0``, so both must be handled:

    * 1.4.x returns ``(results, elapse_list)`` where ``results`` is
      ``None`` (nothing detected) or a list of ``[box, text, score]``.
    * Older builds return a parallel ``(boxes, txts, scores)`` triple.

    Assuming the triple unconditionally is what made every keyframe come
    back ``ocr_status='failed'`` on 1.4.4: the two-element unpack raised
    ``ValueError`` before a single character was read.

    Returns:
        One entry per detected line, or an empty list when the image
        held no text — which is a success, not a failure.
    """
    if not result:
        return []
    if len(result) == 2:
        detections = result[0]
        if not detections:
            return []
        lines: list[tuple[Any, str, Any]] = []
        for item in detections:
            try:
                box, text, score = item[0], item[1], item[2]
            except (IndexError, KeyError, TypeError):
                continue
            lines.append((box, text, score))
        return lines
    if len(result) == 3:
        boxes, txts, scores = result[0], result[1], result[2]
        if not txts:
            return []
        boxes = boxes or []
        scores = scores or []
        return [
            (
                boxes[i] if i < len(boxes) else None,
                txts[i],
                scores[i] if i < len(scores) else None,
            )
            for i in range(len(txts))
        ]
    return []
