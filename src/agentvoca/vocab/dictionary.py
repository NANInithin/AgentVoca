"""Vocabulary substitution module.

Loads a user-defined vocabulary (one term per line) and applies
case-insensitive whole-word substitutions to transcript text.

Vocabulary can come from:
- A vocab.txt file (one term per line) referenced by ``VocabularyConfig.path``.
- An inline list of terms from ``VocabularyConfig.inline``.

Each term is a word or phrase that the ASR may not transcribe correctly.
Vocabulary substitution replaces these terms in the transcript with
themselves (casing-preserving), effectively biasing the output toward
including these terms.
"""

import re
from pathlib import Path
from typing import Optional

from agentvoca.utils.errors import ConfigError


def _read_vocab_file(path: str | Path) -> list[str]:
    """Read a vocabulary file, one term per line.

    Lines are stripped. Empty lines and lines starting with ``#`` are ignored.

    Args:
        path: Path to the vocabulary file.

    Returns:
        List of vocabulary terms.

    Raises:
        ConfigError: If the file cannot be read.
    """
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise ConfigError(f"Vocabulary file not found: {file_path}")

    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read vocabulary file {file_path}: {exc}") from exc

    terms = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            terms.append(stripped)
    return terms


def _build_pattern(terms: list[str]) -> re.Pattern:
    """Build a compiled regex for whole-word matching of the given terms.

    Uses ``(?<!\\w)`` and ``(?!\\w)`` instead of ``\\b`` so that terms
    ending with non-word characters (e.g., ``C++``, ``C#``) match correctly.

    Args:
        terms: List of vocabulary terms.

    Returns:
        A compiled regex pattern.
    """
    if not terms:
        return re.compile(r"(?!x)x")

    escaped = [re.escape(term) for term in terms]
    # Sort longest first so longer phrases match before their substrings
    escaped.sort(key=len, reverse=True)
    pattern = r"(?<!\w)(" + "|".join(escaped) + r")(?!\w)"
    return re.compile(pattern, re.IGNORECASE)


class VocabularyDictionary:
    """User-defined vocabulary for term substitution in transcripts.

    Usage::

        vocab = VocabularyDictionary(terms=["PyTorch", "CUDA"])
        corrected = vocab.apply("I use pytorch and cuda")
        # -> "I use PyTorch and CUDA"
    """

    def __init__(
        self,
        path: Optional[str | Path] = None,
        terms: Optional[list[str]] = None,
    ) -> None:
        """Initialize the dictionary.

        Args:
            path: Optional path to a vocab.txt file. Terms from the file are
                  merged with any ``terms`` list.
            terms: Optional inline list of vocabulary terms.

        Raises:
            ConfigError: If the vocab file path is given but cannot be read.
        """
        self._terms: list[str] = []

        # Load from file if path is provided
        if path is not None:
            self._terms.extend(_read_vocab_file(path))

        # Add inline terms
        if terms is not None:
            self._terms.extend(terms)

        self._pattern = _build_pattern(self._terms)

    @property
    def terms(self) -> list[str]:
        """The list of registered vocabulary terms (read-only)."""
        return list(self._terms)

    @property
    def is_empty(self) -> bool:
        """True if no vocabulary terms are registered."""
        return len(self._terms) == 0

    def _replacement(self, match: re.Match) -> str:
        """Return the original vocabulary term casing for a matched word.

        Looks up the matched text (case-insensitively) in the registered
        terms list to find the stored casing. If not found, returns the
        match unchanged.
        """
        matched = match.group(1)
        lower = matched.lower()
        for term in self._terms:
            if term.lower() == lower:
                return term
        return matched

    def apply(self, text: str) -> str:
        """Apply vocabulary substitution to the given text.

        Terms are matched as case-insensitive whole words and their
        original casing is preserved.

        Args:
            text: The transcript text to process.

        Returns:
            The text with vocabulary terms preserved/reinforced.
        """
        if not text or self.is_empty:
            return text

        return self._pattern.sub(self._replacement, text)
