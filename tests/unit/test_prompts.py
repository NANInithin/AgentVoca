"""Unit tests for cleanup prompt generation."""

from agentvoca.cleanup.prompts import TECHNICAL_GUARDRAILS, get_cleanup_prompt


def test_standard_prompt():
    """Test standard style prompt generation."""
    prompt = get_cleanup_prompt(style="standard")
    assert "You are a transcript cleaner" in prompt
    assert "standard" in prompt.lower() or "natural" in prompt.lower()
    assert TECHNICAL_GUARDRAILS in prompt


def test_raw_prompt():
    """Test raw style prompt generation."""
    prompt = get_cleanup_prompt(style="raw")
    assert "Return the transcript exactly as provided" in prompt
    assert TECHNICAL_GUARDRAILS in prompt


def test_custom_prompt():
    """Test custom prompt override."""
    custom = "Rewrite this as a poem."
    prompt = get_cleanup_prompt(custom_prompt=custom)
    assert custom in prompt
    assert TECHNICAL_GUARDRAILS in prompt


def test_no_preserve_code():
    """Test prompt generation without technical guardrails."""
    prompt = get_cleanup_prompt(preserve_code=False)
    assert TECHNICAL_GUARDRAILS not in prompt
