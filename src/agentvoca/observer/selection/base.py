"""Selection reader abstract base class (v0.4.0, OBS-18).

The contract: read the user's current text selection (highlighted
text on screen). The whole point of UIA is that this NEVER touches
the clipboard and NEVER injects keystrokes (D5).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from agentvoca.observer.models import Selection


class SelectionReader(ABC):
    """Reads the current text selection on screen.

    Implementations must be read-only. They MUST NOT touch the clipboard
    and MUST NOT inject keystrokes. They MUST return within
    ``timeout_ms`` because the caller runs on a bounded worker.
    """

    @abstractmethod
    def is_available(self) -> bool:
        """Return False on platforms/configs where selection reading
        cannot work (e.g. macOS without UIA, or ``method == "none"``).
        """

    @abstractmethod
    def read_selection(self, timeout_ms: int = 250) -> Optional[Selection]:
        """Read the current selection, or None if there is none.

        Returns ``None`` when:
        - the foreground app has no text pattern (caller falls back
          to OCR-rect);
        - the UIA call timed out (RK4 — Electron / PDF viewers);
        - the call raised (R8: soft contract; the caller logs once
          per app and falls back).

        Args:
            timeout_ms: Maximum wall-clock time the call may take. The
                implementation must return None on timeout, never block.
        """
