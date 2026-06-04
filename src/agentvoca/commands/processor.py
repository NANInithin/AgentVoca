import re
from typing import Dict, Optional

from agentvoca.commands.base import CommandProcessor, CommandResult


class DefaultCommandProcessor(CommandProcessor):
    """Implementation of CommandProcessor with a default set of editing commands."""

    def __init__(self, phrase_overrides: Optional[Dict[str, str]] = None):
        # Action to internal key mapping
        # "delete_last" and "undo" are often synonyms in voice commands
        self.default_phrases = {
            "new line": "newline",
            "new paragraph": "paragraph",
            "scratch that": "delete_last",
            "undo that": "undo",
            "capitalize that": "capitalize",
        }

        # Merge with overrides from config
        self.phrases = self.default_phrases.copy()
        if phrase_overrides:
            self.phrases.update(phrase_overrides)

        # Compile regexes for each action
        # We want to match these at the start of the string, case-insensitive
        # and potentially followed by text.
        self._patterns = {}
        for phrase, action in self.phrases.items():
            # Match start of string, phrase, then either end of string or a space
            # \b doesn't always work well with multi-word phrases if not careful
            pattern = re.compile(rf"^{re.escape(phrase)}(?:\s+|$)", re.IGNORECASE)
            self._patterns[phrase] = (pattern, action)

    def process(self, transcript: str) -> CommandResult:
        if not transcript:
            return CommandResult(matched=False)

        text = transcript.strip()

        for phrase, (pattern, action) in self._patterns.items():
            match = pattern.match(text)
            if match:
                remaining = text[match.end() :].strip()
                # If there's remaining text, we only match if it's a leading command
                # The spec says "leading/standalone".
                return CommandResult(
                    matched=True,
                    action=action,  # type: ignore
                    remaining_text=remaining,
                )

        return CommandResult(matched=False)
