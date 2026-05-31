"""Voice activity detection wrapper around silero-vad.

Wraps the silero-vad library to provide speech detection on audio chunks.
Emits ``VADSpeechEvent`` via the event bus when speech/silence transitions
are detected.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import VADSpeechEvent
from agentvoca.utils.errors import VADError

logger = logging.getLogger(__name__)

# Silero-VAD operates at 16kHz mono
_VAD_SAMPLE_RATE = 16000
# Default threshold for speech probability
_DEFAULT_THRESHOLD = 0.5


class VAD:
    """Voice activity detector using silero-vad.

    Args:
        event_bus: Event bus for publishing ``VADSpeechEvent``.
        threshold: Speech probability threshold (0.0 to 1.0).
            Values above this are considered speech.
        sample_rate: Expected sample rate of incoming audio.
            Must be 8000 or 16000. Will be resampled if needed.
    """

    def __init__(
        self,
        event_bus: EventBus,
        threshold: float = _DEFAULT_THRESHOLD,
        sample_rate: int = _VAD_SAMPLE_RATE,
    ) -> None:
        self._event_bus = event_bus
        self._threshold = threshold
        self._target_sample_rate = sample_rate

        # Lazy-loaded model
        self._model: Optional[object] = None
        self._last_speech_state: Optional[bool] = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """Load the silero-vad model.

        Raises:
            VADError: If the model fails to load.
        """
        try:
            import silero_vad

            self._model = silero_vad.load_silero_vad()
            logger.info("VAD model loaded")
        except Exception as exc:
            raise VADError(f"Failed to load VAD model: {exc}") from exc

    def stop(self) -> None:
        """Release VAD resources."""
        self._model = None
        self._last_speech_state = None

    @property
    def is_available(self) -> bool:
        """Return True if the VAD model is loaded."""
        return self._model is not None

    # ── Detection ──────────────────────────────────────────────────────

    def is_speech(self, audio_chunk: bytes) -> bool:
        """Check whether an audio chunk contains speech.

        Args:
            audio_chunk: Raw PCM mono audio bytes at 16kHz.

        Returns:
            True if speech is detected above the threshold.
        """
        if self._model is None:
            logger.warning("VAD not initialized; assuming speech")
            return True

        # Convert bytes to numpy float32 array
        audio_float = np.frombuffer(audio_chunk, dtype=np.float32).squeeze()

        # Ensure mono
        if audio_float.ndim > 1:
            audio_float = audio_float.mean(axis=1)

        try:
            import silero_vad

            speech_prob = silero_vad.get_speech_timestamps(
                audio_float,
                self._model,
                threshold=self._threshold,
                sampling_rate=self._target_sample_rate,
                return_seconds=True,
            )
            # get_speech_timestamps returns a list of speech segments;
            # non-empty list means speech detected
            return len(speech_prob) > 0
        except Exception as exc:
            logger.warning("VAD inference failed: %s", exc)
            return True  # Default to speech on error

    def process_chunk(self, audio_chunk: bytes, timestamp_ms: int) -> None:
        """Process an audio chunk and emit VADSpeechEvent on state change.

        Args:
            audio_chunk: Raw PCM mono audio bytes at 16kHz.
            timestamp_ms: Timestamp of the chunk in milliseconds.
        """
        is_speech = self.is_speech(audio_chunk)

        if self._last_speech_state is None or self._last_speech_state != is_speech:
            self._last_speech_state = is_speech
            self._event_bus.publish(VADSpeechEvent(is_speech=is_speech, timestamp_ms=timestamp_ms))
