"""Deterministic rules-based cleanup provider.

Performs basic filler removal, capitalization, and punctuation without
external dependencies. Also implements technical token detection.
"""

import re
from typing import Optional

from agentvoca.cleanup.base import CleanupProvider
from agentvoca.config.schema import CleanupConfig
from agentvoca.core.types import CleanupContext

# Common filler words and phrases to remove
FILLER_WORDS = [
    r"\buhm?\b",
    r"\bumm?\b",
    r"\bahm?\b",
    r"\berm?\b",
    r"\byou know\b",
    r"\bi mean\b",
]

# Regex patterns for technical tokens
TECH_PATTERNS = {
    "path": r"(?:[a-zA-Z]:\\|[~/]|[.\\]+[\/\\])\S+",
    "url": r"https?://\S+|file://\S+",
    "flag": r"--\w+(?:[=-]\S+)?",
    "camel": r"\b[a-z][a-z0-9]*([A-Z][a-z0-9]*)+\b",
    "constant": r"\b[A-Z_]{2,}\b",
}


class RulesCleanupProvider(CleanupProvider):
    """Cleanup provider using deterministic Python rules."""

    def __init__(self, config: Optional[CleanupConfig] = None) -> None:
        self._config = config
        # Compile filler regex with case-insensitivity
        self._filler_re = re.compile("|".join(FILLER_WORDS), re.IGNORECASE)
        # Compile tech patterns
        self._tech_res = {name: re.compile(pattern) for name, pattern in TECH_PATTERNS.items()}

    # ── v2: warm-up (trivial — no external dependencies) ─────────────

    async def warm_up(self) -> None:
        """No-op: rules-based cleanup has no model to load or pool to prime."""
        return None

    def get_name(self) -> str:
        """Return the registry key for this provider."""
        return "rules"

    def is_available(self) -> bool:
        """Always available (no dependencies)."""
        return True

    def _detect_tech_tokens(self, text: str) -> bool:
        """Return True if 4 or more technical tokens are detected."""
        count = 0
        for pattern_re in self._tech_res.values():
            count += len(pattern_re.findall(text))
            if count >= 4:
                return True
        return False

    async def rewrite(
        self,
        transcript: str,
        context: Optional[CleanupContext] = None,
    ) -> str:
        """Clean transcript using deterministic rules."""
        if not transcript.strip():
            return transcript

        style = context.style if context else "standard"
        if style == "raw":
            return transcript
        preserve_code = (context.preserve_code if context else False) or bool(
            self._config and self._config.preserve_code
        )
        if preserve_code and ("\n" in transcript or self._detect_tech_tokens(transcript)):
            return transcript

        # In this rules-based provider, "preserving" means we are careful
        # with our regexes not to mangle them. The "passthrough marker"
        # mentioned in the spec is primarily for when this logic is used
        # to guard an LLM, but here we can just apply our rules carefully.

        text = transcript

        # 2. Filler removal (if not in raw mode or if standard/technical)
        if style in ("standard", "technical", "professional"):
            # Remove fillers but preserve spaces
            protected = [
                match.span()
                for pattern in self._tech_res.values()
                for match in pattern.finditer(text)
            ]
            text = self._filler_re.sub(
                lambda match: (
                    match.group()
                    if any(start < match.end() and match.start() < end for start, end in protected)
                    else ""
                ),
                text,
            )
            # Clean up extra spaces
            text = re.sub(r"[ \t]+", " ", text).strip()

        # 3. Basic Capitalization
        # Capitalize first letter of the whole text
        if text:
            text = text[0].upper() + text[1:]

        # Capitalize after sentence-ending punctuation
        text = re.sub(r"([.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)

        # 4. Sentence-end punctuation
        if text and text[-1] not in ".!?":
            text += "."

        return text
