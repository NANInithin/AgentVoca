"""OpenAI-compatible OCR provider (v0.4.0, OBS-17).

Reuses the same shape as ``vision/openai_compatible.py``: a persistent
``httpx.AsyncClient`` (R8) with ``keepalive_expiry=30.0``, the same
base64 image block construction, the same error handling. A single
adapter serves OpenAI GPT-4o, OpenRouter, Gemini (via gateway), and
local servers such as Ollama.

The prompt asks for verbatim text extraction in reading order,
markdown for tables, no commentary or preamble.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from typing import Optional

import httpx

from agentvoca.config.schema import ObserverOCRConfig
from agentvoca.observer.models import OCRResult
from agentvoca.observer.ocr.base import OCRProvider

logger = logging.getLogger(__name__)


# Module-level constant so the prompt is reviewable.
_OCR_PROMPT = """\
You are a high-fidelity OCR engine. Extract the visible text from the
image in reading order, top to bottom and left to right.

Rules you must follow without exception:
- Transcribe all numbers, currency amounts, dates, and units exactly as shown.
- Preserve all code identifiers, file paths, URLs, and version strings exactly.
- Do not invent, add, omit, or guess any data that is not visible in the image.
- If a value is unreadable, write [unreadable] rather than guessing.
- Render any tabular data as a Markdown table with a header row and a
  separator row.
- Output only the extracted content. Do not add commentary, preamble,
  or closing remarks such as "Here is the text:" or "I hope this helps".
"""


class OpenAICompatibleOCRProvider(OCRProvider):
    """OCR provider using an OpenAI-compatible chat-completions API.

    Sends the JPEG to ``{endpoint}/chat/completions`` along with a
    system prompt that asks for verbatim text extraction. The response
    is returned as the OCRResult.text.
    """

    def __init__(self, config: ObserverOCRConfig) -> None:
        super().__init__(config)
        self._endpoint = config.endpoint or "https://api.openai.com/v1"
        self._model = config.model or "gpt-4o-mini"
        self._api_key: Optional[str] = None
        if config.api_key_env:
            self._api_key = os.environ.get(config.api_key_env)
        # R8: persistent HTTP client — reused across extract()/warm_up().
        # OCR is faster than vision, so the per-request timeout is 30s.
        self._client = self._make_client(timeout=30.0)

    def _make_client(self, *, timeout: float) -> httpx.AsyncClient:
        """Construct the shared ``httpx.AsyncClient``.

        Exposed as a seam so tests can inject a ``MockTransport``.
        """
        return httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=4,
                max_keepalive_connections=4,
                keepalive_expiry=30.0,
            ),
        )

    async def shutdown(self) -> None:
        """Close the pooled HTTP client. Safe to call more than once."""
        await self._client.aclose()

    async def warm_up(self) -> None:
        """Prime the HTTP connection pool with a lightweight health check.

        Must not raise.
        """
        if not self.is_available():
            return
        try:
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            url = f"{self._endpoint.rstrip('/')}/models"
            await self._client.get(url, headers=headers, timeout=5.0)
            logger.debug("OpenAICompatibleOCRProvider warm-up complete")
        except Exception:
            logger.debug("OpenAICompatibleOCRProvider warm-up failed (non-fatal)")

    def is_available(self) -> bool:
        """Return True when an endpoint is configured and an API key is set if required."""
        if not self._endpoint:
            return False
        if self._config.api_key_env and not self._api_key:
            return False
        return True

    async def extract(self, image_jpeg: bytes, *, hint: Optional[str] = None) -> OCRResult:
        """Extract text from a JPEG via the VLM.

        Args:
            image_jpeg: JPEG-encoded bytes from the ScreenGrabber.
            hint: Optional recent utterance (e.g. for context).

        Returns:
            ``OCRResult`` with the model's text and latency.

        Raises:
            Exception: On a genuine HTTP / response failure. A blank
                image is a SUCCESS — the model returns empty text and
                we report ``OCRResult(text="", ...)``.
        """
        if not image_jpeg:
            return OCRResult(text="", confidence=None, latency_ms=0, engine="openai_compatible")
        start = time.perf_counter()
        b64 = base64.standard_b64encode(image_jpeg).decode("ascii")
        data_url = f"data:image/jpeg;base64,{b64}"
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        user_content: list[dict] = [{"type": "image_url", "image_url": {"url": data_url}}]
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _OCR_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.0,
        }
        try:
            url = f"{self._endpoint.rstrip('/')}/chat/completions"
            response = await self._client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            extracted = result["choices"][0]["message"]["content"]
            if extracted is None:
                text = ""
            else:
                text = str(extracted).strip()
        except httpx.HTTPError as exc:
            logger.warning("OCR request failed: %s", exc)
            raise
        except (KeyError, IndexError) as exc:
            logger.warning("Malformed OCR response: %s", exc)
            raise
        except Exception as exc:
            logger.warning("Unexpected OCR error: %s", exc)
            raise
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return OCRResult(
            text=text,
            confidence=None,
            latency_ms=elapsed_ms,
            engine="openai_compatible",
        )
