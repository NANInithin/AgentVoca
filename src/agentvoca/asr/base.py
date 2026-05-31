"""ASR provider abstract base class.

All ASR adapters must subclass ``ASRProvider`` and implement the required
methods. The orchestrator constructs instances via the provider registry.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from agentvoca.core.types import ASRContext, TranscriptSegment


class ASRProvider(ABC):
    """Abstract base class for automatic speech recognition providers.

    Implementations must handle their own internal errors and surface them
    as ``ASRError`` (or a subclass) defined in ``src.agentvoca.utils.errors``.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Return the registry key for this provider.

        Returns:
            The unique string name used to register and look up this provider.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider can accept requests right now.

        This should check that required models are downloaded, API keys are
        configured, or remote endpoints are reachable.

        Returns:
            True if the provider is ready to transcribe.
        """

    @abstractmethod
    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> TranscriptSegment:
        """Transcribe a complete audio buffer.

        Always returns a final segment (``is_final=True``).

        Args:
            audio_bytes: Raw audio data.
            sample_rate: Sample rate of the audio in Hz.
            context: Optional hints (language, vocabulary) for the ASR.

        Returns:
            A ``TranscriptSegment`` containing the transcribed text.
        """

    @abstractmethod
    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> AsyncIterator[TranscriptSegment]:
        """Yield interim and final segments as audio arrives.

        Providers that do not support streaming must implement this by
        buffering internally and yielding one final segment at the end.
        Must yield at least one segment with ``is_final=True`` before returning.

        Args:
            audio_stream: Async iterator of raw audio chunks.
            sample_rate: Sample rate of the audio in Hz.
            context: Optional hints for the ASR.

        Yields:
            ``TranscriptSegment`` instances (interim and final).
        """
