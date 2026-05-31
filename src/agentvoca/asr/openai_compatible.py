"""OpenAI-compatible ASR provider.

Sends audio to any OpenAI-compatible /v1/audio/transcriptions endpoint.
"""

import os
from typing import AsyncIterator, Optional

import httpx

from agentvoca.asr.base import ASRProvider
from agentvoca.config.schema import ASRConfig
from agentvoca.core.types import ASRContext, TranscriptSegment
from agentvoca.utils.errors import ASRError


class OpenAICompatibleASRProvider(ASRProvider):
    """ASR provider using an OpenAI-compatible API."""

    def __init__(self, config: ASRConfig) -> None:
        """Initialize the provider with config.

        Args:
            config: The ASR configuration block.
        """
        self._config = config
        self._endpoint = config.endpoint or "https://api.openai.com/v1"
        self._model = config.model or "whisper-1"

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

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> TranscriptSegment:
        """Transcribe a complete audio buffer via API."""
        if not audio_bytes:
            return TranscriptSegment(text="", is_final=True)

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # Prepare multipart/form-data
        files = {
            "file": ("audio.wav", audio_bytes, "audio/wav"),
        }
        data = {
            "model": self._model,
            "response_format": "json",
        }

        language = context.language_hint if context else self._config.language_hint
        if language:
            data["language"] = language

        # Optional prompt from context/config
        prompt = ""
        if context and context.vocabulary_hints:
            prompt = ", ".join(context.vocabulary_hints)
        if prompt:
            data["prompt"] = prompt

        # Add any extra parameters from config
        if self._config.extra:
            data.update(self._config.extra)

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                url = f"{self._endpoint.rstrip('/')}/audio/transcriptions"
                response = await client.post(url, headers=headers, files=files, data=data)
                response.raise_for_status()

                result = response.json()
                text = result.get("text", "").strip()

                return TranscriptSegment(
                    text=text, is_final=True, language_detected=result.get("language")
                )

        except httpx.HTTPError as e:
            raise ASRError(f"OpenAI-compatible ASR request failed: {e}")
        except Exception as e:
            raise ASRError(f"Unexpected error during ASR: {e}")

    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> AsyncIterator[TranscriptSegment]:
        """Buffer all audio and return a single final segment."""
        # Most OpenAI-compatible APIs don't support streaming audio upload
        # for transcriptions in the same way they do for chat.
        all_bytes = bytearray()
        async for chunk in audio_stream:
            all_bytes.extend(chunk)

        final_segment = await self.transcribe_audio(bytes(all_bytes), sample_rate, context)
        yield final_segment
