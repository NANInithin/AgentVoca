from pathlib import Path
from typing import Dict, List, Optional, Tuple

from agentvoca.utils.logging import get_logger

logger = get_logger(__name__)


class AdaptiveStore:
    """Tracks user corrections and promotes frequently corrected terms to the vocabulary.

    This store keeps track of how many times a user has corrected a specific
    misrecognition (wrong -> right). Once a correction threshold is crossed,
    the 'right' term is promoted to the permanent learned vocabulary.
    """

    def __init__(self, learned_vocab_path: Optional[str | Path] = None, promote_threshold: int = 3):
        """Initialize the adaptive store.

        Args:
            learned_vocab_path: Path to the learned_vocab.txt file.
            promote_threshold: Number of corrections needed before promotion.
        """
        self.promote_threshold = promote_threshold
        if learned_vocab_path:
            self.learned_vocab_path = Path(learned_vocab_path).expanduser().resolve()
        else:
            self.learned_vocab_path = Path("~/.agentvoca/learned_vocab.txt").expanduser().resolve()

        # Track corrections: (wrong.lower(), right) -> count
        self._corrections: Dict[Tuple[str, str], int] = {}

        # Load existing learned terms and mappings
        self.learned_terms: List[str] = []
        self.learned_mappings: List[Tuple[str, str]] = []
        self._load_learned_vocab()

    def _load_learned_vocab(self) -> None:
        """Load learned terms from the persistence file."""
        if not self.learned_vocab_path.is_file():
            return

        try:
            text = self.learned_vocab_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if " -> " in stripped:
                    wrong, right = stripped.split(" -> ", 1)
                    self.learned_mappings.append((wrong.strip(), right.strip()))
                else:
                    self.learned_terms.append(stripped)
            logger.info(
                "Loaded %d terms and %d mappings",
                len(self.learned_terms),
                len(self.learned_mappings),
            )
        except Exception as e:
            logger.error("Failed to load learned vocabulary: %s", e)

    def record_correction(self, wrong: str, right: str) -> bool:
        """Record a correction from 'wrong' to 'right'.

        Returns:
            True if the correction was promoted to the learned vocabulary.
        """
        if not wrong or not right:
            return False

        # Clean inputs
        wrong_clean = wrong.strip()
        right_clean = right.strip()

        # If they are effectively the same, ignore
        if wrong_clean.lower() == right_clean.lower():
            return False

        # If already learned as mapping, ignore
        if any(
            w.lower() == wrong_clean.lower() and r == right_clean for w, r in self.learned_mappings
        ):
            return False

        key = (wrong_clean.lower(), right_clean)
        self._corrections[key] = self._corrections.get(key, 0) + 1

        logger.debug(
            "Recorded correction: '%s' -> '%s' (count=%d/%d)",
            wrong_clean,
            right_clean,
            self._corrections[key],
            self.promote_threshold,
        )

        if self._corrections[key] >= self.promote_threshold:
            # Promote to learned mappings
            self.learned_mappings.append((wrong_clean, right_clean))
            self._save_learned_vocab()
            logger.info(
                "Promoted mapping '%s' -> '%s' to learned vocabulary", wrong_clean, right_clean
            )
            return True

        return False

    def _save_learned_vocab(self) -> None:
        """Save learned terms and mappings to the persistence file."""
        try:
            self.learned_vocab_path.parent.mkdir(parents=True, exist_ok=True)
            lines = self.learned_terms + [f"{w} -> {r}" for w, r in self.learned_mappings]
            self.learned_vocab_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save learned vocabulary: %s", e)

    def get_terms(self) -> List[str]:
        """Return the current list of learned vocabulary terms."""
        return list(self.learned_terms)

    def get_mappings(self) -> List[Tuple[str, str]]:
        """Return the current list of learned vocabulary mappings."""
        return list(self.learned_mappings)
