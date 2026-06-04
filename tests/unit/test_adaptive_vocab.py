from agentvoca.vocab.adaptive import AdaptiveStore


def test_adaptive_store_promotion(tmp_path):
    learned_path = tmp_path / "learned.txt"
    store = AdaptiveStore(learned_vocab_path=learned_path, promote_threshold=2)

    # First correction
    promoted = store.record_correction("nini", "NANI")
    assert not promoted
    assert ("nini", "NANI") not in store.get_mappings()

    # Second correction (threshold reached)
    promoted = store.record_correction("nini", "NANI")
    assert promoted
    assert ("nini", "NANI") in store.get_mappings()
    assert "nini -> NANI" in learned_path.read_text()


def test_adaptive_store_persistence(tmp_path):
    learned_path = tmp_path / "learned.txt"
    learned_path.write_text("Existing\nwrong -> NewTerm", encoding="utf-8")

    store = AdaptiveStore(learned_vocab_path=learned_path)
    assert "Existing" in store.get_terms()
    assert ("wrong", "NewTerm") in store.get_mappings()

    # Record something new
    store.promote_threshold = 1
    store.record_correction("another", "Improved")

    # Reload and check
    store2 = AdaptiveStore(learned_vocab_path=learned_path)
    assert ("another", "Improved") in store2.get_mappings()
    assert "Existing" in store2.get_terms()


def test_adaptive_store_ignore_similar(tmp_path):
    learned_path = tmp_path / "learned.txt"
    store = AdaptiveStore(learned_vocab_path=learned_path, promote_threshold=1)

    # Should not record if same word
    promoted = store.record_correction("Word", "word")
    assert not promoted
    assert not store.get_terms()
    assert not store.get_mappings()

    # Should not record if already in learned mappings
    store.learned_mappings = [("wrong", "AlreadyHere")]
    promoted = store.record_correction("wrong", "AlreadyHere")
    assert not promoted
