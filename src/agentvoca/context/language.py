"""Language hint resolution for the context engine.

Consumes the ``language_detected`` field from ASR transcript segments
(currently discarded) and propagates it as a language hint for the
next utterance's ASR invocation and for cleanup context.

This is a simple pass-through storage with a single "latest detected
language" slot. No language detection is performed here.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LanguageResolver:
    """Tracks the latest detected language from ASR and provides it as a hint.

    The ASR provider may detect a language during transcription (stored in
    ``TranscriptSegment.language_detected``). This resolver stores that value
    and makes it available as a hint for the next utterance and for cleanup.

    The resolver is purely advisory: if no language has been detected, it
    returns ``None``.
    """

    def __init__(self) -> None:
        self._latest_detected: Optional[str] = None

    def update(self, language_detected: Optional[str]) -> None:
        """Update the latest detected language.

        Args:
            language_detected: Language code detected by ASR (e.g. "en", "fr"),
                or None to retain the previous value.
        """
        if language_detected is not None:
            previous = self._latest_detected
            self._latest_detected = language_detected
            if previous != language_detected:
                logger.debug("Language hint updated: %s -> %s", previous, language_detected)

    def get_hint(self) -> Optional[str]:
        """Return the latest detected language as a hint for the next utterance.

        Returns:
            The detected language code, or None if no language has been detected.
        """
        return self._latest_detected

    def reset(self) -> None:
        """Reset the detected language (e.g. when the user changes the configured language)."""
        self._latest_detected = None
