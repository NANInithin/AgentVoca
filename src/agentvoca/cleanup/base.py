"""Cleanup provider abstract base class.

All cleanup/rewriting adapters must subclass ``CleanupProvider`` and implement
the required methods. The orchestrator constructs instances via the provider
registry.
"""

from abc import ABC, abstractmethod
from typing import Optional

from agentvoca.core.types import CleanupContext


class CleanupProvider(ABC):
    """Abstract base class for transcript cleanup providers.

    Implementations must handle their own internal errors and surface them
    as ``CleanupError`` (or a subclass) defined in ``src.agentvoca.utils.errors``.
    """

    # -- v2 additions (safe defaults) -----------------------------------

    def supports_streaming(self) -> bool:
        """Return True if the provider can clean partial segments coherently.

        Default False.
        """
        return False

    async def warm_up(self) -> None:
        """Prime connection pool / load local model. Must not raise. Default no-op."""
        return None

    # -- v1 abstract methods (unchanged) ---------------------------------

    @abstractmethod
    def get_name(self) -> str:
        """Return the registry key for this provider.

        Returns:
            The unique string name used to register and look up this provider.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider can accept requests right now.

        This should check that required models are loaded, API keys are
        configured, or remote endpoints are reachable.

        Returns:
            True if the provider is ready to rewrite transcripts.
        """

    @abstractmethod
    async def rewrite(
        self,
        transcript: str,
        context: Optional[CleanupContext] = None,
    ) -> str:
        """Return a cleaned version of the transcript.

        Must never return an empty string when input is non-empty.
        Must never alter code blocks, URLs, file paths, or identifiers
        unless ``context.preserve_code`` is explicitly False.
        On any internal failure, raise ``CleanupError``.

        Args:
            transcript: The raw transcript text to clean.
            context: Optional style hints, vocabulary, and preservation flags.

        Returns:
            The cleaned transcript text.
        """
