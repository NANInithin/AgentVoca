"""Tests for R9: mtime-keyed cache of the custom cleanup prompt file.

Verifies that the prompt file is opened at most once between mtime
changes, that edits with a newer mtime are picked up, and that a missing
file still raises CleanupError with the same message prefix as before.
"""

import os
import time

import pytest

from agentvoca.cleanup.openai_compatible import OpenAICompatibleCleanupProvider
from agentvoca.config.schema import CleanupConfig
from agentvoca.utils.errors import CleanupError


def _provider_with_prompt(path: str) -> OpenAICompatibleCleanupProvider:
    config = CleanupConfig(
        provider="openai_compatible",
        endpoint="https://api.example.com/v1",
        custom_prompt_path=path,
    )
    return OpenAICompatibleCleanupProvider(config)


def test_prompt_read_once_per_mtime(tmp_path, monkeypatch):
    """Two rewrite() calls with the same mtime should open the file only once."""
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("be terse")

    real_open = open

    open_count = {"n": 0}

    def counting_open(*args, **kwargs):
        if args and "prompt.txt" in str(args[0]):
            open_count["n"] += 1
        return real_open(*args, **kwargs)

    monkeypatch.setattr("builtins.open", counting_open)

    config = CleanupConfig(
        provider="openai_compatible",
        endpoint="https://api.example.com/v1",
        custom_prompt_path=str(prompt_file),
    )
    provider = OpenAICompatibleCleanupProvider(config)

    # Manually exercise the cache via the public method; rewrite() goes
    # through httpx which we don't want to set up here.
    provider._load_custom_prompt()
    provider._load_custom_prompt()

    assert open_count["n"] == 1, (
        f"expected 1 file read, got {open_count['n']} (cache miss)"
    )


def test_prompt_cache_invalidated_by_mtime(tmp_path):
    """Touching the file with newer content + newer mtime causes the
    next call to re-read it."""
    prompt_file = tmp_path / "prompt.txt"
    prompt_file.write_text("be terse")

    provider = _provider_with_prompt(str(prompt_file))

    assert provider._load_custom_prompt() == "be terse"
    assert provider._prompt_cache is not None

    # Bump mtime to a guaranteed-future time so the comparison is stable
    # even on filesystems with coarse mtime resolution.
    future = time.time() + 2.0
    prompt_file.write_text("be verbose and use bullets")
    os.utime(str(prompt_file), (future, future))

    assert provider._load_custom_prompt() == "be verbose and use bullets"


def test_missing_prompt_raises_cleanup_error(tmp_path):
    """A missing custom_prompt_path raises CleanupError with the same
    message prefix the pre-R9 implementation used."""
    # Construct the provider with a real file (so the config validator
    # passes), then delete the file to simulate it going missing later.
    present = tmp_path / "present.txt"
    present.write_text("placeholder")
    config = CleanupConfig(
        provider="openai_compatible",
        endpoint="https://api.example.com/v1",
        custom_prompt_path=str(present),
    )
    provider = OpenAICompatibleCleanupProvider(config)
    present.unlink()
    with pytest.raises(CleanupError, match="Failed to load custom prompt file"):
        provider._load_custom_prompt()
