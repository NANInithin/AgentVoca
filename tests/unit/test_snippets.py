"""Tests for the snippet expansion module."""

import pytest

from agentvoca.utils.errors import ConfigError
from agentvoca.vocab.snippets import SnippetExpander


class TestSnippetExpander:
    def test_empty_snippets(self):
        """No snippets means no expansion."""
        expander = SnippetExpander()
        assert expander.is_empty
        assert expander.mapping == {}
        result = expander.expand("hello world")
        assert result == "hello world"

    def test_empty_text(self):
        """Empty text returns empty text."""
        expander = SnippetExpander(snippets={"ppl": "people"})
        assert expander.expand("") == ""
        assert expander.expand("  ") == "  "

    def test_single_snippet(self):
        """A single snippet trigger is expanded."""
        expander = SnippetExpander(snippets={"ppl": "people"})
        result = expander.expand("hello ppl")
        assert result == "hello people"

    def test_snippet_case_insensitive_trigger(self):
        """Trigger matching is case-insensitive."""
        expander = SnippetExpander(snippets={"ppl": "people"})
        result = expander.expand("HELLO PPL")
        assert result == "HELLO people"

    def test_multiple_snippets(self):
        """Multiple snippets are all expanded."""
        expander = SnippetExpander(
            snippets={"ppl": "people", "btw": "by the way", "asap": "as soon as possible"}
        )
        result = expander.expand("ppl btw please reply asap")
        assert result == "people by the way please reply as soon as possible"

    def test_trigger_not_expanded_within_word(self):
        """A trigger should not be expanded when it appears inside another word."""
        expander = SnippetExpander(snippets={"ppl": "people"})
        result = expander.expand("apples are tasty")
        # "ppl" is inside "apples" — word boundary prevents match
        assert result == "apples are tasty"

    def test_longer_trigger_matches_first(self):
        """Longer triggers are matched before shorter ones."""
        expander = SnippetExpander(snippets={"idk": "I do not know", "id": "identification"})
        result = expander.expand("idk what that means")
        assert result == "I do not know what that means"

    def test_trigger_with_special_regex_chars(self):
        """Triggers with regex special characters are escaped."""
        expander = SnippetExpander(snippets={"c++": "c plus plus", "c#": "c sharp"})
        result = expander.expand("learning c++ and c#")
        assert result == "learning c plus plus and c sharp"

    def test_snippets_loaded_from_file(self, tmp_path):
        """Snippets from a YAML file are loaded correctly."""
        snippets_file = tmp_path / "snippets.yaml"
        snippets_file.write_text("ppl: people\nbtw: by the way\n")
        expander = SnippetExpander(path=str(snippets_file))
        assert expander.mapping == {"ppl": "people", "btw": "by the way"}
        result = expander.expand("ppl btw")
        assert result == "people by the way"

    def test_file_missing(self):
        """A missing snippets file raises ConfigError."""
        with pytest.raises(ConfigError, match="Snippets file not found"):
            SnippetExpander(path="/nonexistent/snippets.yaml")

    def test_file_invalid_yaml(self, tmp_path):
        """An invalid YAML file raises ConfigError."""
        snippets_file = tmp_path / "bad.yaml"
        snippets_file.write_text("{{ invalid yaml")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            SnippetExpander(path=str(snippets_file))

    def test_file_not_a_mapping(self, tmp_path):
        """A YAML file that parses to a non-dict raises ConfigError."""
        snippets_file = tmp_path / "list.yaml"
        snippets_file.write_text("[a, b, c]")
        with pytest.raises(ConfigError, match="must contain a top-level mapping"):
            SnippetExpander(path=str(snippets_file))

    def test_file_non_string_value(self, tmp_path):
        """A YAML file with non-string values raises ConfigError."""
        snippets_file = tmp_path / "bad_types.yaml"
        snippets_file.write_text("ppl: 123")
        with pytest.raises(ConfigError, match="must map to a string"):
            SnippetExpander(path=str(snippets_file))

    def test_merge_file_and_inline(self, tmp_path):
        """File snippets and inline snippets are merged."""
        snippets_file = tmp_path / "snippets.yaml"
        snippets_file.write_text("ppl: people\n")
        expander = SnippetExpander(
            path=str(snippets_file),
            snippets={"btw": "by the way"},
        )
        assert expander.mapping == {"ppl": "people", "btw": "by the way"}

    def test_mapping_property_returns_copy(self):
        """The mapping property returns a copy, not the internal dict."""
        expander = SnippetExpander(snippets={"a": "b"})
        mapping = expander.mapping
        mapping["c"] = "d"
        assert expander.mapping == {"a": "b"}

    def test_no_false_positive_on_similar_words(self):
        """A trigger should not match words that merely contain it."""
        expander = SnippetExpander(snippets={"asap": "as soon as possible"})
        result = expander.expand("asap is an acronym, but asaps is not")
        # "asap" at the start matches. "asaps" has \b after 's' not after 'p',
        # so "asap" inside "asaps" should NOT match.
        assert "as soon as possible" in result
