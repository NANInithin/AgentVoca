"""Anchor-phrase splicing for screenshot extractions (v3).

When the user dictates with screenshots attached, spoken *anchor phrases*
(e.g. "the attached screenshot") mark where each extraction is spliced into
the transcript. Captures map to anchors in order: the first screenshot fills
the first anchor, the second fills the second, and so on. Extractions with no
matching anchor are appended at the end. The merged text is later passed to
the cleanup LLM (with ``preserve_code``) which smooths the surrounding prose
while leaving the extracted block intact.
"""

from __future__ import annotations

import re

# Built-in anchor phrases. "screen shot" / "screenshots" variants are included
# because ASR transcribes the word inconsistently. Order does not matter — the
# splicer prefers the longest match at each position.
DEFAULT_ANCHOR_PHRASES: list[str] = [
    "the attached screenshot",
    "the attached screen shot",
    "the attached image",
    "this screenshot",
    "this screen shot",
    "this image",
    "the screenshot",
    "the screen shot",
    "attached screenshot",
    "attached screen shot",
    "as shown above",
    "as shown below",
    "as shown",
    "as in the screenshot",
    "as in the screen shot",
]


class AnchorSplicer:
    """Splices ordered extractions into a transcript at anchor phrases."""

    def __init__(self, phrases: list[str] | None = None) -> None:
        """Initialize with a phrase list, falling back to the built-in defaults.

        Args:
            phrases: Anchor phrases to match. Empty/None uses the defaults.
        """
        self._phrases = [p for p in (phrases or []) if p.strip()] or list(DEFAULT_ANCHOR_PHRASES)
        # Longest phrases first so "the attached screenshot" wins over "screenshot".
        ordered = sorted(self._phrases, key=len, reverse=True)
        pattern = "|".join(re.escape(p) for p in ordered)
        self._regex = re.compile(pattern, re.IGNORECASE) if pattern else None

    def find_anchors(self, transcript: str) -> list[re.Match[str]]:
        """Return non-overlapping anchor matches in left-to-right order."""
        if self._regex is None or not transcript:
            return []
        return list(self._regex.finditer(transcript))

    def splice(self, transcript: str, extractions: list[str]) -> tuple[str, int]:
        """Splice extractions into the transcript.

        Args:
            transcript: The dictated text (after vocab/snippets).
            extractions: Extracted content blocks, in capture order.

        Returns:
            A tuple ``(spliced_text, anchors_matched)`` where ``anchors_matched``
            is the number of anchor phrases that consumed an extraction.
        """
        extractions = [e for e in extractions if e and e.strip()]
        if not extractions:
            return transcript, 0

        matches = self.find_anchors(transcript)
        n_paired = min(len(matches), len(extractions))

        # Replace paired anchors right-to-left so earlier match offsets stay valid.
        result = transcript
        for i in range(n_paired - 1, -1, -1):
            m = matches[i]
            block = f"\n\n{extractions[i].strip()}\n\n"
            result = result[: m.start()] + block + result[m.end() :]

        # Any extraction beyond the available anchors is appended in order.
        leftover = extractions[n_paired:]
        if leftover:
            tail = "\n\n".join(e.strip() for e in leftover)
            result = result.rstrip() + "\n\n" + tail

        # Collapse the 3+ newlines a mid-sentence splice can create.
        result = re.sub(r"\n{3,}", "\n\n", result).strip()
        return result, n_paired
