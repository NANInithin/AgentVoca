"""Unit tests for the rules-based cleanup provider."""

import pytest

from agentvoca.cleanup.rules import RulesCleanupProvider
from agentvoca.core.types import CleanupContext


@pytest.fixture
def provider():
    return RulesCleanupProvider()


@pytest.mark.asyncio
async def test_filler_removal(provider):
    """Test that common filler words are removed."""
    input_text = "uhm so like i mean basically it works"
    expected = "So it works."  # Capitalization and punctuation also applied
    result = await provider.rewrite(input_text)
    assert result == expected


@pytest.mark.asyncio
async def test_capitalization(provider):
    """Test basic sentence capitalization."""
    input_text = "this is a test. and another one! right?"
    expected = "This is a test. And another one! Right?"
    result = await provider.rewrite(input_text)
    assert result == expected


@pytest.mark.asyncio
async def test_punctuation(provider):
    """Test that sentence-end punctuation is added if missing."""
    input_text = "this is a test"
    expected = "This is a test."
    result = await provider.rewrite(input_text)
    assert result == expected


@pytest.mark.asyncio
async def test_tech_token_detection(provider):
    """Test that technical tokens are detected and preserve_code is forced."""
    # 4 technical tokens: URL, path, flag, camelCase
    input_text = "check https://google.com and ~/docs/file.txt with --flag and myVarName"

    # We can't directly check 'preserve_code' internal state easily,
    # but we can check if it mangles them.
    # The rules provider is designed to be safe anyway.
    result = await provider.rewrite(input_text)
    assert "https://google.com" in result
    assert "~/docs/file.txt" in result
    assert "--flag" in result
    assert "myVarName" in result
    assert "Check https://google.com and ~/docs/file.txt with --flag and myVarName." == result


@pytest.mark.asyncio
async def test_raw_style(provider):
    """Test that 'raw' style returns transcript unchanged."""
    input_text = "uhm so like it works"
    context = CleanupContext(style="raw")
    result = await provider.rewrite(input_text, context=context)
    assert result == input_text


@pytest.mark.asyncio
async def test_empty_input(provider):
    """Test that empty input is returned as-is."""
    assert await provider.rewrite("") == ""
    assert await provider.rewrite("   ") == "   "
