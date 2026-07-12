"""OpenAI-compatible ASR provider.

Sends audio to any OpenAI-compatible /v1/audio/transcriptions endpoint.
"""

import io
import logging
import os
import wave
from typing import AsyncIterator, Optional

import httpx
import numpy as np

from agentvoca.asr.base import ASRProvider
from agentvoca.config.schema import ASRConfig
from agentvoca.core.types import ASRContext, TranscriptSegment
from agentvoca.utils.errors import ASRError

logger = logging.getLogger(__name__)


def _pcm_f32_to_wav(audio_bytes: bytes, sample_rate: int, channels: int = 1) -> bytes:
    """Wrap raw little-endian float32 PCM in a standard 16-bit PCM WAV container.

    The audio pipeline captures ``float32`` samples in ``[-1.0, 1.0]`` (mono,
    ``sample_rate`` Hz) and passes the *headerless* bytes straight through —
    that is exactly what the local faster-whisper provider consumes via
    ``np.frombuffer(..., dtype=np.float32)``. A remote ``/audio/transcriptions``
    endpoint, however, needs a real decodable file: without the RIFF/WAVE
    header the server cannot determine the sample rate/format and rejects the
    upload with ``400 Bad Request``. We therefore convert float32 → int16 and
    emit a conventional PCM WAV, which every Whisper-compatible endpoint
    (OpenAI, Groq, whisper.cpp, …) accepts.
    """
    # Trim any trailing partial sample so ``frombuffer`` never rejects a
    # buffer whose length is not an exact multiple of 4 bytes.
    usable = len(audio_bytes) - (len(audio_bytes) % 4)
    samples = np.frombuffer(audio_bytes[:usable], dtype=np.float32)
    # Replace non-finite values, then clip before scaling so loud input does
    # not wrap around when cast to int16.
    samples = np.nan_to_num(samples, nan=0.0, posinf=1.0, neginf=-1.0)
    int16 = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)  # int16
        wav.setframerate(sample_rate)
        wav.writeframes(int16.tobytes())
    return buffer.getvalue()


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

        # The pipeline hands us raw float32 PCM (what faster-whisper consumes
        # in-process); a remote endpoint needs a real WAV file or it 400s.
        try:
            wav_bytes = _pcm_f32_to_wav(audio_bytes, sample_rate)
        except Exception as exc:  # malformed buffer — surface as an ASR error
            raise ASRError(f"Failed to encode audio for upload: {exc}") from exc

        # Prepare multipart/form-data
        files = {
            "file": ("audio.wav", wav_bytes, "audio/wav"),
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

        url = f"{self._endpoint.rstrip('/')}/audio/transcriptions"
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, headers=headers, files=files, data=data)
                response.raise_for_status()

                result = response.json()
                text = result.get("text", "").strip()

                return TranscriptSegment(
                    text=text, is_final=True, language_detected=result.get("language")
                )

        except httpx.HTTPStatusError as e:
            # Surface the provider's own error body — it usually explains the
            # real cause (unsupported model, endpoint that has no transcription
            # API, bad audio, quota) far better than the bare status line.
            detail = (e.response.text or "").strip()
            if len(detail) > 500:
                detail = detail[:500] + "…"
            message = (
                f"OpenAI-compatible ASR request failed: HTTP {e.response.status_code} from {url}"
            )
            if detail:
                message += f" — {detail}"
            raise ASRError(message) from e
        except httpx.HTTPError as e:
            raise ASRError(f"OpenAI-compatible ASR request failed: {e}") from e
        except Exception as e:
            raise ASRError(f"Unexpected error during ASR: {e}") from e

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
