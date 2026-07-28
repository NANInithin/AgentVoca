"""Tests for ``observer/privacy.py`` (OBS-25, exclusion matching)."""

from __future__ import annotations

import time

from agentvoca.config.schema import ObserverPrivacyConfig
from agentvoca.observer.privacy import ExclusionMatcher


def _config(apps=(), titles=()) -> ObserverPrivacyConfig:
    return ObserverPrivacyConfig(exclude_apps=list(apps), exclude_title_patterns=list(titles))


# ── Tests ──────────────────────────────────────────────────────────────


def test_password_manager_excluded() -> None:
    m = ExclusionMatcher(_config(apps=("1Password.exe",), titles=()))
    excluded, pattern = m.is_excluded("1Password.exe", "My Vault")
    assert excluded is True
    assert pattern == "1Password.exe"


def test_chrome_not_excluded() -> None:
    m = ExclusionMatcher(_config(apps=("1Password.exe",), titles=()))
    excluded, pattern = m.is_excluded("chrome.exe", "Foo")
    assert excluded is False
    assert pattern is None


def test_case_insensitive_app() -> None:
    """Windows exe names are case-insensitive; pattern is too."""
    m = ExclusionMatcher(_config(apps=("1Password.exe",), titles=()))
    excluded, _ = m.is_excluded("1PASSWORD.EXE", "Foo")
    assert excluded is True


def test_case_insensitive_title_glob() -> None:
    """Title globs match case-insensitively too."""
    m = ExclusionMatcher(_config(apps=(), titles=("*Incognito*",)))
    excluded, pattern = m.is_excluded("chrome.exe", "Foo - Incognito - Chrome")
    assert excluded is True
    assert pattern == "*Incognito*"
    excluded, _ = m.is_excluded("chrome.exe", "foo - incognito - chrome")
    assert excluded is True


def test_none_app_and_title_not_excluded() -> None:
    m = ExclusionMatcher(_config(apps=("chrome.exe",), titles=("Foo",)))
    excluded, pattern = m.is_excluded(None, None)
    assert excluded is False
    assert pattern is None


def test_empty_lists_exclude_nothing() -> None:
    m = ExclusionMatcher(_config(apps=(), titles=()))
    excluded, pattern = m.is_excluded("1Password.exe", "Password Manager")
    assert excluded is False
    assert pattern is None


def test_match_returns_pattern() -> None:
    """The matched pattern, not just True, is returned for ``pause_start`` meta."""
    m = ExclusionMatcher(_config(apps=("KeePass.exe", "1Password.exe"), titles=()))
    excluded, pattern = m.is_excluded("KeePass.exe", "Foo")
    assert excluded is True
    assert pattern == "KeePass.exe"


def test_first_match_wins() -> None:
    """When multiple patterns could match, the first one in the list wins."""
    m = ExclusionMatcher(_config(apps=("K*", "KeePass.exe"), titles=()))
    excluded, pattern = m.is_excluded("KeePass.exe", "Foo")
    assert excluded is True
    assert pattern == "K*"


def test_app_match_takes_precedence_over_title() -> None:
    """App is checked first; if it matches, title is not consulted."""
    m = ExclusionMatcher(_config(apps=("chrome.exe",), titles=("Foo",)))
    excluded, pattern = m.is_excluded("chrome.exe", "Bar")
    assert excluded is True
    assert pattern == "chrome.exe"


def test_title_match_when_app_does_not() -> None:
    m = ExclusionMatcher(_config(apps=("chrome.exe",), titles=("*InPrivate*",)))
    excluded, pattern = m.is_excluded("firefox.exe", "InPrivate Browsing")
    assert excluded is True
    assert pattern == "*InPrivate*"


def test_performance_10k_calls_under_100ms() -> None:
    """10 000 calls with 20 patterns complete in < 100 ms.

    The matcher runs at the foreground-poll rate (2 Hz) and is
    compiled once, so this is comfortable headroom for the real
    hot path.
    """
    apps = tuple(f"App{i}.exe" for i in range(10))
    titles = tuple(f"*Pattern{i}*" for i in range(10))
    m = ExclusionMatcher(_config(apps=apps, titles=titles))

    started = time.perf_counter()
    for _ in range(10_000):
        m.is_excluded("App5.exe", "Title with Pattern7 in it")
    elapsed = time.perf_counter() - started
    assert elapsed < 0.1, f"10 000 calls took {elapsed:.3f}s; expected < 0.1s"


def test_blank_patterns_are_ignored() -> None:
    """An empty or whitespace pattern is silently dropped at construction."""
    m = ExclusionMatcher(_config(apps=("", "  ", "1Password.exe"), titles=()))
    assert m.app_patterns == ["1Password.exe"]


def test_defaults_are_sensible() -> None:
    """The schema defaults are non-empty lists of common exclusions."""
    m = ExclusionMatcher(ObserverPrivacyConfig())
    # The default excludes 1Password and several others.
    assert any("1Password" in p for p in m.app_patterns)
    # And it has a "Password" title pattern by default.
    assert any("Password" in p for p in m.title_patterns)
