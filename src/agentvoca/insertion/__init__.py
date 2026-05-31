"""Text insertion strategies."""

from agentvoca.core.types import InsertionResult
from agentvoca.insertion.base import InsertionStrategy
from agentvoca.insertion.clipboard import ClipboardInsertionStrategy
from agentvoca.insertion.keyboard import KeyboardInsertionStrategy

BUILTIN_INSERTION_STRATEGIES = {
    "keyboard": KeyboardInsertionStrategy,
    "clipboard": ClipboardInsertionStrategy,
}

__all__ = [
    "BUILTIN_INSERTION_STRATEGIES",
    "ClipboardInsertionStrategy",
    "InsertionResult",
    "InsertionStrategy",
    "KeyboardInsertionStrategy",
]
