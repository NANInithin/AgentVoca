from agentvoca.commands.processor import DefaultCommandProcessor


def test_command_matching_standalone():
    processor = DefaultCommandProcessor()

    # Test standalone commands
    res = processor.process("new line")
    assert res.matched
    assert res.action == "newline"
    assert res.remaining_text == ""

    res = processor.process("new paragraph")
    assert res.matched
    assert res.action == "paragraph"

    res = processor.process("scratch that")
    assert res.matched
    assert res.action == "delete_last"

    res = processor.process("undo that")
    assert res.matched
    assert res.action == "undo"

    res = processor.process("capitalize that")
    assert res.matched
    assert res.action == "capitalize"


def test_command_matching_leading():
    processor = DefaultCommandProcessor()

    res = processor.process("new line This is a test")
    assert res.matched
    assert res.action == "newline"
    assert res.remaining_text == "This is a test"

    res = processor.process("capitalize that Hello world")
    assert res.matched
    assert res.action == "capitalize"
    assert res.remaining_text == "Hello world"


def test_command_matching_case_insensitive():
    processor = DefaultCommandProcessor()

    res = processor.process("New Line")
    assert res.matched
    assert res.action == "newline"

    res = processor.process("SCraTCH THat")
    assert res.matched
    assert res.action == "delete_last"


def test_command_matching_no_match():
    processor = DefaultCommandProcessor()

    # Should not match if embedded
    res = processor.process("I want a new line please")
    assert not res.matched

    # Should not match if just a substring of a word
    res = processor.process("newline")  # without space if processor expects "new line"
    # Actually "new line" is our phrase. "newline" won't match "new line".
    assert not res.matched


def test_command_overrides():
    overrides = {"delete": "delete_last", "undo": "undo"}
    processor = DefaultCommandProcessor(phrase_overrides=overrides)

    res = processor.process("delete")
    assert res.matched
    assert res.action == "delete_last"

    res = processor.process("undo")
    assert res.matched
    assert res.action == "undo"

    # Default should still work
    res = processor.process("new line")
    assert res.matched
    assert res.action == "newline"
