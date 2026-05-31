"""Passthrough cleanup provider.

Returns the transcript unchanged. Used when cleanup is disabled.
"""

from typing import Optional

from agentvoca.cleanup.base import CleanupProvider
from agentvoca.config.schema import CleanupConfig
from agentvoca.core.types import CleanupContext


class NoneCleanupProvider(CleanupProvider):
    """Cleanup provider that performs no changes."""

    def __init__(self, config: Optional[CleanupConfig] = None) -> None:
        """Initialize the provider.

        Args:
            config: Optional configuration (ignored by this provider).
        """
        self._config = config

    def get_name(self) -> str:
        """Return the registry key for this provider."""
        return "none"

    def is_available(self) -> bool:
        """Always available."""
        return True

    async def rewrite(
        self,
        transcript: str,
        context: Optional[CleanupContext] = None,
    ) -> str:
        """Return the transcript unchanged."""
        return transcript
