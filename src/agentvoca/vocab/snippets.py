"""Snippet expansion module.

Loads a snippets YAML file (trigger → expansion) and applies
case-insensitive whole-word substitutions to transcript text.

Snippet format (YAML)::

    # snippets.yaml
    "ppl": "people"
    "btw": "by the way"
    "i.e.": "that is"
    "asap": "as soon as possible"
"""

import re
from pathlib import Path
from typing import Optional

import yaml

from agentvoca.utils.errors import ConfigError


def _load_snippets(path: str | Path) -> dict[str, str]:
    """Load snippets from a YAML file.

    Args:
        path: Path to the snippets YAML file.

    Returns:
        Dictionary mapping trigger strings to expansion strings.

    Raises:
        ConfigError: If the file cannot be read or is not a valid mapping.
    """
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise ConfigError(f"Snippets file not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except OSError as exc:
        raise ConfigError(f"Cannot read snippets file {file_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in snippets file {file_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Snippets file {file_path} must contain a top-level mapping.")

    # Validate all values are strings
    snippets: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise ConfigError(f"Invalid snippet trigger in {file_path}: {key!r} must be a string.")
        if not isinstance(value, str):
            raise ConfigError(
                f"Invalid snippet expansion in {file_path}: "
                f"trigger {key!r} must map to a string, got {type(value).__name__}."
            )
        snippets[key] = value

    return snippets


def _build_pattern(triggers: list[str]) -> re.Pattern:
    """Build a compiled regex for whole-word matching of snippet triggers.

    Args:
        triggers: List of trigger strings.

    Returns:
        A compiled regex pattern.
    """
    if not triggers:
        return re.compile(r"(?!x)x")

    escaped = [re.escape(t) for t in triggers]
    escaped.sort(key=len, reverse=True)
    pattern = r"(?<!\w)(" + "|".join(escaped) + r")(?!\w)"
    return re.compile(pattern, re.IGNORECASE)


class SnippetExpander:
    """Snippet expansion for transcript text.

    Replaces trigger words/phrases with their expanded forms.

    Usage::

        expander = SnippetExpander({"ppl": "people", "btw": "by the way"})
        result = expander.expand("I met some ppl btw")
        # -> "I met some people by the way"
    """

    def __init__(
        self,
        path: Optional[str | Path] = None,
        snippets: Optional[dict[str, str]] = None,
    ) -> None:
        """Initialize the snippet expander.

        Args:
            path: Optional path to a snippets.yaml file. Snippets from the file
                  are merged with any ``snippets`` dict.
            snippets: Optional inline dict of trigger → expansion pairs.

        Raises:
            ConfigError: If the snippets file path is given but cannot be loaded.
        """
        self._snippets: dict[str, str] = {}

        if path is not None:
            self._snippets.update(_load_snippets(path))

        if snippets is not None:
            self._snippets.update(snippets)

        self._pattern = _build_pattern(list(self._snippets.keys()))

    @property
    def mapping(self) -> dict[str, str]:
        """The trigger → expansion mapping (read-only)."""
        return dict(self._snippets)

    @property
    def is_empty(self) -> bool:
        """True if no snippets are registered."""
        return len(self._snippets) == 0

    def expand(self, text: str) -> str:
        """Expand snippet triggers in the given text.

        Triggers are matched as case-insensitive whole words and replaced
        with their expansion text (preserving the original case of the
        expansion in lowercase, since expansions are typically phrases).

        Args:
            text: The transcript text to process.

        Returns:
            The text with snippets expanded.
        """
        if not text or self.is_empty:
            return text

        def _replace(match: re.Match) -> str:
            matched = match.group(1)
            lower = matched.lower()
            # Return the expansion as-is (we use the defined casing)
            return self._snippets.get(lower, matched)

        return self._pattern.sub(_replace, text)
