"""Insertion strategy abstract base class.

All text insertion strategies must subclass ``InsertionStrategy`` and implement
the required methods. The orchestrator constructs instances via the provider
registry.
"""

from abc import ABC, abstractmethod

from agentvoca.core.types import InsertionResult


class InsertionStrategy(ABC):
    """Abstract base class for text insertion strategies.

    Implementations must handle their own internal errors and return
    ``InsertionResult(success=False, ...)`` rather than raising.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Return the registry key for this strategy.

        Returns:
            The unique string name used to register and look up this strategy.
        """

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if insertion can proceed on this platform.

        This should check platform-specific requirements (e.g., accessibility
        permissions on macOS, UAC on Windows).

        Returns:
            True if the strategy can insert text on the current platform.
        """

    @abstractmethod
    async def insert(self, text: str) -> InsertionResult:
        """Insert text at the current cursor position.

        Must not raise. On failure, return ``InsertionResult(success=False, ...)``.
        The orchestrator decides when to fall back to another strategy.

        Args:
            text: The text to insert.

        Returns:
            An ``InsertionResult`` indicating success or failure.
        """

    @abstractmethod
    async def undo_last(self) -> bool:
        """Attempt to undo the last insertion.

        Returns:
            True if the undo was successful.
        """
