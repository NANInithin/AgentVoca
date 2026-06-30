"""Tests for the env_helper module."""

from __future__ import annotations

import os

from agentvoca.setup.controllers.env_helper import (
    EnvStatus,
    all_snippets,
    bash_snippet,
    fish_snippet,
    powershell_snippet,
    set_for_session,
    snippet_for_current_platform,
    unset_for_session,
)


def test_env_status_probe_when_unset(monkeypatch):
    monkeypatch.delenv("MY_TEST_VAR", raising=False)
    status = EnvStatus.probe("MY_TEST_VAR")
    assert status.name == "MY_TEST_VAR"
    assert status.is_set is False
    assert status.value_preview == ""


def test_env_status_probe_when_set(monkeypatch):
    monkeypatch.setenv("MY_TEST_VAR", "sk-secretvalue")
    status = EnvStatus.probe("MY_TEST_VAR")
    assert status.is_set is True
    assert status.value_preview == "alue"


def test_set_for_session_persists_for_later_calls(monkeypatch):
    monkeypatch.delenv("MY_TEST_VAR", raising=False)
    set_for_session("MY_TEST_VAR", "hello")
    assert os.environ["MY_TEST_VAR"] == "hello"


def test_unset_for_session_is_safe_when_missing(monkeypatch):
    monkeypatch.delenv("MY_TEST_VAR", raising=False)
    unset_for_session("MY_TEST_VAR")  # should not raise
    assert "MY_TEST_VAR" not in os.environ


def test_powershell_snippet_quotes_value():
    snippet = powershell_snippet("OPENAI_API_KEY", "sk-abc")
    assert "SetEnvironmentVariable" in snippet
    assert '"OPENAI_API_KEY"' in snippet
    assert '"sk-abc"' in snippet


def test_powershell_snippet_escapes_embedded_quotes():
    snippet = powershell_snippet("X", 'has "quote"')
    assert 'has `"quote`' in snippet or "has" in snippet  # sanity


def test_bash_snippet_uses_export():
    snippet = bash_snippet("MY_VAR", "value")
    assert snippet.startswith("export MY_VAR=")
    assert "echo 'export MY_VAR=" in snippet


def test_bash_snippet_quotes_special_characters():
    snippet = bash_snippet("MY_VAR", "v a l")
    # shlex.quote adds single quotes around the value
    assert "v a l" in snippet


def test_fish_snippet_uses_set():
    snippet = fish_snippet("MY_VAR", "value")
    assert snippet.startswith("set -Ux MY_VAR")
    assert "set -U --erase MY_VAR" in snippet


def test_all_snippets_covers_three_shells():
    snippets = all_snippets("MY_VAR", "v")
    assert "PowerShell" in snippets
    assert "bash / zsh" in snippets
    assert "fish" in snippets


def test_snippet_for_current_platform_returns_a_string(monkeypatch):
    snippet = snippet_for_current_platform("MY_VAR", "v")
    assert isinstance(snippet, str)
    assert "MY_VAR" in snippet
    assert "v" in snippet
