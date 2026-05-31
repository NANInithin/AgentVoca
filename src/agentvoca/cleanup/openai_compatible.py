"""OpenAI-compatible LLM cleanup provider.

Sends transcripts to any OpenAI-compatible /v1/chat/completions endpoint
using a style-specific system prompt.
"""

import os
from typing import Optional

import httpx

from agentvoca.cleanup.base import CleanupProvider
from agentvoca.cleanup.prompts import get_cleanup_prompt
from agentvoca.config.schema import CleanupConfig
from agentvoca.core.types import CleanupContext
from agentvoca.utils.errors import CleanupError


class OpenAICompatibleCleanupProvider(CleanupProvider):
    """Cleanup provider using an OpenAI-compatible LLM API."""

    def __init__(self, config: CleanupConfig) -> None:
        """Initialize the provider with config.

        Args:
            config: The cleanup configuration block.
        """
        self._config = config
        self._endpoint = config.endpoint or "https://api.openai.com/v1"
        self._model = config.model or "gpt-4o-mini"

        # Get API key from env if configured
        self._api_key = None
        if config.api_key_env:
            self._api_key = os.environ.get(config.api_key_env)

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

    async def rewrite(
        self,
        transcript: str,
        context: Optional[CleanupContext] = None,
    ) -> str:
        """Rewrite transcript using the LLM.

        Args:
            transcript: The raw transcript text.
            context: Cleanup style and preservation hints.

        Returns:
            The cleaned transcript.

        Raises:
            CleanupError: If the API call fails or returns an error.
        """
        if not transcript.strip():
            return transcript

        style = context.style if context else self._config.style
        preserve_code = context.preserve_code if context else self._config.preserve_code
        custom_prompt = context.custom_prompt if context else None

        # Load custom prompt from file if configured but not passed in context
        if not custom_prompt and self._config.custom_prompt_path:
            try:
                with open(self._config.custom_prompt_path, "r", encoding="utf-8") as f:
                    custom_prompt = f.read()
            except Exception as e:
                raise CleanupError(f"Failed to load custom prompt file: {e}")

        system_prompt = get_cleanup_prompt(
            style=style, custom_prompt=custom_prompt, preserve_code=preserve_code
        )

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcript},
            ],
            "temperature": 0.1,  # Low temperature for deterministic-ish cleanup
        }

        # Add any extra parameters from config
        if self._config.extra:
            payload.update(self._config.extra)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self._endpoint.rstrip('/')}/chat/completions"
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()

                result = response.json()
                cleaned_text = result["choices"][0]["message"]["content"].strip()

                if not cleaned_text and transcript:
                    # Guardrail: never return empty if input was not empty
                    return transcript

                return cleaned_text

        except httpx.HTTPError as e:
            raise CleanupError(f"LLM cleanup request failed: {e}")
        except (KeyError, IndexError) as e:
            raise CleanupError(f"Malformed LLM response: {e}")
        except Exception as e:
            raise CleanupError(f"Unexpected error during cleanup: {e}")
