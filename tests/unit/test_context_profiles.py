"""Unit tests for the ProfileResolver context engine component."""

from __future__ import annotations

from agentvoca.context.profiles import ProfileResolver


class TestProfileResolver:
    """Profile resolution tests."""

    def test_empty_profiles_returns_none(self) -> None:
        """With no profiles, resolve should return None."""
        resolver = ProfileResolver(profiles={})
        assert resolver.resolve("Code.exe") is None

    def test_exact_match(self) -> None:
        """Exact app name match should return the configured style."""
        resolver = ProfileResolver(profiles={"Code.exe": "technical"})
        assert resolver.resolve("Code.exe") == "technical"

    def test_fallback_wildcard(self) -> None:
        """When no pattern matches, the '*' fallback should be used."""
        resolver = ProfileResolver(profiles={"*": "standard"})
        assert resolver.resolve("unknown_app") == "standard"

    def test_fnmatch_pattern(self) -> None:
        """Patterns using glob wildcards should match via fnmatch."""
        resolver = ProfileResolver(profiles={"Code*": "technical"})
        assert resolver.resolve("Code.exe") == "technical"
        assert resolver.resolve("Code - Insiders") == "technical"

    def test_fnmatch_case_sensitivity(self) -> None:
        """fnmatch behavior depends on the platform (case-insensitive on Windows).

        On Windows, fnmatch is case-insensitive. On POSIX it's case-sensitive.
        The resolver handles whatever fnmatch gives it.
        """
        import fnmatch

        resolver = ProfileResolver(profiles={"code*": "technical"})
        assert resolver.resolve("code.exe") == "technical"
        # On Windows fnmatch is case-insensitive, so Code.exe also matches.
        # On POSIX it's case-sensitive so it wouldn't match (no fallback).
        expected = "technical" if fnmatch.fnmatch("Code.exe", "code*") else None
        assert resolver.resolve("Code.exe") == expected

    def test_exact_match_precedes_pattern(self) -> None:
        """Exact match should take priority over fnmatch pattern."""
        resolver = ProfileResolver(profiles={"Code.exe": "technical", "Code*": "professional"})
        assert resolver.resolve("Code.exe") == "technical"
        assert resolver.resolve("Code - Insiders") == "professional"

    def test_multiple_apps(self) -> None:
        """Multiple app patterns should resolve independently."""
        resolver = ProfileResolver(
            profiles={
                "Code.exe": "technical",
                "slack": "professional",
                "firefox": "standard",
                "*": "standard",
            }
        )
        assert resolver.resolve("Code.exe") == "technical"
        assert resolver.resolve("slack") == "professional"
        assert resolver.resolve("firefox") == "standard"
        assert resolver.resolve("terminal") == "standard"  # fallback

    def test_resolve_none_returns_fallback(self) -> None:
        """resolve(None) should return the fallback style if set."""
        resolver = ProfileResolver(profiles={"*": "light"})
        assert resolver.resolve(None) == "light"

    def test_resolve_none_no_fallback(self) -> None:
        """resolve(None) should return None when no fallback is configured."""
        resolver = ProfileResolver(profiles={"Code.exe": "technical"})
        assert resolver.resolve(None) is None

    def test_mapping_property(self) -> None:
        """The mapping property should return a copy of the raw config dict."""
        profiles = {"Code.exe": "technical", "*": "standard"}
        resolver = ProfileResolver(profiles=profiles)
        assert resolver.mapping == profiles
        # Ensure it's a copy
        resolver.mapping["new"] = "value"
        assert "new" not in resolver.mapping  # copy

    def test_unknown_style_warned_and_ignored(self) -> None:
        """Unknown styles should be logged and ignored (not raise)."""
        resolver = ProfileResolver(profiles={"Code.exe": "technical", "Unknown.exe": "nonexistent"})
        assert resolver.resolve("Code.exe") == "technical"
        assert resolver.resolve("Unknown.exe") is None

    def test_no_profiles_constructor(self) -> None:
        """Constructor with no arguments should create an empty resolver."""
        resolver = ProfileResolver()
        assert resolver.mapping == {}

    def test_resolve_empty_string_app(self) -> None:
        """An empty string app name should behave like None."""
        resolver = ProfileResolver(profiles={"*": "standard"})
        assert resolver.resolve("") == "standard"
