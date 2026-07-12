"""Tests for R13: batched learned-mapping merge in VocabularyDictionary.

Verifies that ``add_mappings`` rebuilds the pattern exactly once for a
batch of mappings, while ``add_mapping`` (singular) keeps its previous
behavior for the adaptive single-promotion path.
"""

import pytest

from agentvoca.vocab.dictionary import (
    VocabularyDictionary,
)


@pytest.fixture
def counting_build_pattern(monkeypatch):
    """Wrap ``_build_pattern`` so the test can count rebuilds."""
    import agentvoca.vocab.dictionary as mod

    real = mod._build_pattern
    counter = {"calls": 0}

    def wrapper(terms):
        counter["calls"] += 1
        return real(terms)

    monkeypatch.setattr(mod, "_build_pattern", wrapper)
    return counter


def test_bulk_mappings_trigger_single_rebuild(counting_build_pattern):
    """A single ``add_mappings`` call rebuilds the pattern exactly once,
    regardless of batch size."""
    vocab = VocabularyDictionary()
    counter = counting_build_pattern
    # Reset after constructor (which itself does an initial rebuild).
    counter["calls"] = 0

    pairs = [(f"wrong{i:03d}", f"right{i:03d}") for i in range(200)]
    vocab.add_mappings(pairs)

    assert counter["calls"] == 1, (
        f"expected 1 rebuild, got {counter['calls']} "
        "(add_mappings should batch and rebuild once)"
    )


def test_bulk_mappings_apply_correctly(counting_build_pattern):
    """All 200 mappings apply to a transcript after a single bulk insert."""
    vocab = VocabularyDictionary()
    pairs = [(f"wrong{i:03d}", f"right{i:03d}") for i in range(200)]
    vocab.add_mappings(pairs)

    for i in (0, 50, 100, 199):
        wrong = f"wrong{i:03d}"
        right = f"right{i:03d}"
        assert vocab.apply(f"see the {wrong} here") == f"see the {right} here"


def test_singular_add_mapping_still_rebuilds(counting_build_pattern):
    """``add_mapping`` (singular) still rebuilds the pattern — used by the
    adaptive single-promotion path."""
    vocab = VocabularyDictionary()
    counter = counting_build_pattern
    counter["calls"] = 0
    vocab.add_mapping("polars", "Polars")
    assert counter["calls"] == 1
    assert vocab.apply("use polars today") == "use Polars today"


def test_empty_bulk_is_noop(counting_build_pattern):
    """An empty batch is a no-op and does not trigger a rebuild."""
    vocab = VocabularyDictionary()
    counter = counting_build_pattern
    counter["calls"] = 0
    vocab.add_mappings([])
    assert counter["calls"] == 0
    assert vocab.is_empty
