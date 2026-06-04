from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class CommandResult:
    matched: bool
    action: Optional[Literal["newline", "paragraph", "delete_last", "undo", "capitalize"]] = None
    remaining_text: str = ""  # dictation text left after stripping the command


class CommandProcessor:
    def process(self, transcript: str) -> CommandResult:
        """High-precision match of leading/standalone command phrases.
        Returns matched=False for anything ambiguous (treat as dictation)."""
        raise NotImplementedError()
