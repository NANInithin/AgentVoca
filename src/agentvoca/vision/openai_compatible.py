"""OpenAI-compatible vision provider (v3).

Sends a screenshot plus the spoken instruction to any OpenAI-compatible
/v1/chat/completions endpoint that accepts image content blocks. This single
adapter serves Claude (via an OpenAI-compatible gateway), OpenAI GPT-4o,
OpenRouter, Gemini, and local servers such as Ollama — matching AgentVoca's
model-agnostic philosophy.
"""

import base64
import logging
import os
from typing import Optional

import httpx

from agentvoca.config.schema import VisionConfig
from agentvoca.core.types import VisionContext
from agentvoca.utils.errors import VisionError
from agentvoca.vision.base import VisionProvider
from agentvoca.vision.prompts import get_vision_prompt

logger = logging.getLogger(__name__)


class OpenAICompatibleVisionProvider(VisionProvider):
    """Vision provider using an OpenAI-compatible chat-completions API."""

    def __init__(self, config: VisionConfig) -> None:
        """Initialize the provider with config.

        Args:
            config: The vision configuration block.
        """
        self._config = config
        self._endpoint = config.endpoint or "https://api.openai.com/v1"
        self._model = config.model or "gpt-4o-mini"

        self._api_key = None
        if config.api_key_env:
            self._api_key = os.environ.get(config.api_key_env)

    async def warm_up(self) -> None:
        """Prime the HTTP connection pool with a lightweight health check.

        Must not raise.
        """
        if not self.is_available():
            logger.debug("OpenAICompatibleVisionProvider warm-up skipped (not available)")
            return
        try:
            headers = {}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                url = f"{self._endpoint.rstrip('/')}/models"
                await client.get(url, headers=headers)
            logger.debug("OpenAICompatibleVisionProvider warm-up complete")
        except Exception:
            logger.debug("OpenAICompatibleVisionProvider warm-up failed (non-fatal)")

    def get_name(self) -> str:
        """Return the registry key for this provider."""
        return "openai_compatible"

    def is_available(self) -> bool:
        """Return True if endpoint and API key (if required) are set."""
        if not self._endpoint:
            return False
        if self._config.api_key_env and not self._api_key:
            return False
        return True

    async def extract(
        self,
        image_data: bytes,
        instruction: str,
        context: Optional[VisionContext] = None,
        mime_type: str = "image/png",
    ) -> str:
        """Extract image content via the VLM.

        Args:
            image_data: Encoded image bytes.
            instruction: The spoken dictation guiding extraction.
            context: Optional style/preservation hints.
            mime_type: MIME type of ``image_data``.

        Returns:
            The extracted content text.

        Raises:
            VisionError: If the API call fails or returns an error.
        """
        if not image_data:
            raise VisionError("No image data to extract.")

        output_format = self._config.output_format
        if context is not None and context.output_format != "auto":
            output_format = context.output_format

        system_prompt = get_vision_prompt(instruction=instruction, output_format=output_format)

        b64 = base64.standard_b64encode(image_data).decode("ascii")
        data_url = f"data:{mime_type};base64,{b64}"

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        user_content: list[dict] = [
            {"type": "image_url", "image_url": {"url": data_url}},
        ]
        if instruction.strip():
            user_content.insert(0, {"type": "text", "text": instruction.strip()})

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
        }

        if self._config.extra:
            payload.update(self._config.extra)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                url = f"{self._endpoint.rstrip('/')}/chat/completions"
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()

                result = response.json()
                extracted = result["choices"][0]["message"]["content"]
                if extracted is None:
                    raise VisionError("Vision response contained no content.")
                return extracted.strip()

        except httpx.HTTPError as e:
            raise VisionError(f"Vision request failed: {e}")
        except (KeyError, IndexError) as e:
            raise VisionError(f"Malformed vision response: {e}")
        except VisionError:
            raise
        except Exception as e:
            raise VisionError(f"Unexpected error during vision extraction: {e}")
