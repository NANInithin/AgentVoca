"""Unit tests for the vision anchor splicer (v3)."""

from agentvoca.vision.anchors import DEFAULT_ANCHOR_PHRASES, AnchorSplicer


def test_no_extractions_returns_transcript_unchanged() -> None:
    sp = AnchorSplicer()
    out, n = sp.splice("just some dictation", [])
    assert out == "just some dictation"
    assert n == 0


def test_no_anchor_appends_at_end() -> None:
    sp = AnchorSplicer()
    out, n = sp.splice("here are the numbers", ["| A | B |"])
    assert n == 0
    assert out.startswith("here are the numbers")
    assert "| A | B |" in out
    assert out.endswith("| A | B |")


def test_single_anchor_replaced_in_place() -> None:
    sp = AnchorSplicer()
    out, n = sp.splice("make a table from the attached screenshot now", ["TABLE"])
    assert n == 1
    assert "the attached screenshot" not in out
    assert "TABLE" in out
    # Surrounding words are preserved around the splice point.
    assert out.startswith("make a table from")
    assert out.rstrip().endswith("now")


def test_multiple_anchors_map_in_order() -> None:
    sp = AnchorSplicer()
    transcript = "first this screenshot then the attached image done"
    out, n = sp.splice(transcript, ["ONE", "TWO"])
    assert n == 2
    assert out.index("ONE") < out.index("TWO")


def test_more_extractions_than_anchors_appends_leftover() -> None:
    sp = AnchorSplicer()
    out, n = sp.splice("only this screenshot here", ["ONE", "TWO", "THREE"])
    assert n == 1
    assert out.index("ONE") < out.index("TWO") < out.index("THREE")
    assert out.rstrip().endswith("THREE")


def test_more_anchors_than_extractions_leaves_extra_anchor() -> None:
    sp = AnchorSplicer()
    out, n = sp.splice("this screenshot and the attached image", ["ONE"])
    assert n == 1
    assert "ONE" in out
    # The second anchor had no extraction, so its text remains.
    assert "the attached image" in out


def test_longest_phrase_wins() -> None:
    sp = AnchorSplicer()
    # "the attached screenshot" should be matched as a whole, not just "screenshot".
    out, n = sp.splice("see the attached screenshot please", ["X"])
    assert n == 1
    assert "the attached screenshot" not in out
    assert "screenshot" not in out


def test_custom_phrases_override_defaults() -> None:
    sp = AnchorSplicer(phrases=["insert here"])
    out, n = sp.splice("put it insert here thanks", ["BLOCK"])
    assert n == 1
    assert "BLOCK" in out
    # A default phrase is no longer recognised.
    out2, n2 = sp.splice("the attached screenshot", ["BLOCK"])
    assert n2 == 0


def test_empty_phrases_falls_back_to_defaults() -> None:
    sp = AnchorSplicer(phrases=[])
    assert sp._phrases == DEFAULT_ANCHOR_PHRASES


def test_whitespace_blank_extractions_ignored() -> None:
    sp = AnchorSplicer()
    out, n = sp.splice("this screenshot", ["   ", ""])
    assert n == 0
    assert out == "this screenshot"


def test_no_excessive_blank_lines() -> None:
    sp = AnchorSplicer()
    out, _ = sp.splice("a this screenshot b", ["X"])
    assert "\n\n\n" not in out
