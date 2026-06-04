"""Context provider abstract base class and shared dataclasses.

All context detection adapters must subclass ``ContextProvider`` and implement
the required methods. The orchestrator constructs instances via the provider
registry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ResolvedContext:
    """The resolved context at a point in time.

    Attributes:
        app_name: Name of the foreground application (e.g. "Code.exe", "firefox").
            None if detection failed or is disabled.
        window_title: Title of the foreground window. None if detection failed.
        style: Resolved style profile (e.g. "technical", "professional") or None
            to keep the global configured style.
        language: Resolved language hint (e.g. "en", "fr") or None for auto.
    """

    app_name: Optional[str] = None
    window_title: Optional[str] = None
    style: Optional[str] = None
    language: Optional[str] = None


class ContextProvider(ABC):
    """Abstract base for context detection providers.

    Implementations must handle their own internal errors gracefully and
    surface them via logging rather than exceptions. Context resolution
    is advisory — a failure must never block dictation.
    """

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if context detection works on this platform.

        Returns:
            True if the platform supports foreground app detection and
            the required native APIs are accessible.
        """

    @abstractmethod
    def resolve(self) -> ResolvedContext:
        """Return the current context.

        Must not raise. Returns an empty ``ResolvedContext`` (all fields
        None) on any failure or when context is disabled.

        Returns:
            The current ``ResolvedContext`` with whatever fields could
            be determined.
        """
