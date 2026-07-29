"""No-op selection reader (v0.4.0, OBS-18).

Used on macOS/Linux, and on Windows when ``observer.selection.method ==
"none"``. ``is_available()`` is always False; ``read_selection()``
always returns None.
"""

from __future__ import annotations

from typing import Optional

from agentvoca.observer.models import Selection
from agentvoca.observer.selection.base import SelectionReader


class NoopSelectionReader(SelectionReader):
    """Selection reader that is never available. macOS/Linux default."""

    def is_available(self) -> bool:
        return False

    def read_selection(self, timeout_ms: int = 250) -> Optional[Selection]:
        return None
