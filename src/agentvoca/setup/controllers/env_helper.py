"""Env-var helper — the UI's "Set this API key now" affordance.

AgentVoca never writes API keys to disk. The config references the env var by
name (``api_key_env: OPENAI_API_KEY``); this helper exists so users can:

1. See whether the variable is currently set in the process's environment.
2. Set it for the running process immediately (so saving config + applying
   the new provider works without a manual restart).
3. Copy a shell snippet for making the variable persistent across sessions.

Three persistence snippets are generated: PowerShell (Windows), bash/zsh
(macOS/Linux), and fish. The user picks whichever matches their shell.
"""

from __future__ import annotations

import os
import platform
import shlex
from dataclasses import dataclass


@dataclass
class EnvStatus:
    """Current status of an env var.

    Attributes:
        name: The env var name (e.g. ``OPENAI_API_KEY``).
        is_set: True if the variable is currently present in ``os.environ``.
        value_preview: Last 4 characters of the value, for the "looks like sk-…"
            visual confirmation. Empty if the variable is not set.
    """

    name: str
    is_set: bool
    value_preview: str

    @classmethod
    def probe(cls, name: str) -> "EnvStatus":
        """Build an EnvStatus for ``name`` based on the current environment."""
        value = os.environ.get(name)
        if value:
            preview = value[-4:] if len(value) >= 4 else value
            return cls(name=name, is_set=True, value_preview=preview)
        return cls(name=name, is_set=False, value_preview="")


def set_for_session(name: str, value: str) -> None:
    """Set the env var for the current process only.

    Args:
        name: Env var name.
        value: Value to assign.
    """
    os.environ[name] = value


def unset_for_session(name: str) -> None:
    """Remove the env var from the current process environment."""
    os.environ.pop(name, None)


# ── Snippet generators ───────────────────────────────────────────────


def powershell_snippet(name: str, value: str) -> str:
    """Return a PowerShell command that sets the env var for the user account.

    Uses ``[Environment]::SetEnvironmentVariable`` with target ``User`` so it
    survives reboots and applies to all new processes for that user.
    """
    quoted_value = value.replace('"', '`"')
    return f'[System.Environment]::SetEnvironmentVariable("{name}", "{quoted_value}", "User")'


def bash_snippet(name: str, value: str) -> str:
    """Return a bash/zsh snippet to export the env var.

    Includes a commented-out line that, if the user uncomments it, appends
    the export to ``~/.bashrc`` so it persists across sessions.
    """
    safe = shlex.quote(value)
    return (
        f"export {name}={safe}\n"
        f"# Persist across sessions by adding to ~/.bashrc (or ~/.zshrc):\n"
        f"# echo 'export {name}={safe}' >> ~/.bashrc"
    )


def fish_snippet(name: str, value: str) -> str:
    """Return a fish shell snippet to set the env var."""
    safe = shlex.quote(value)
    return (
        f"set -Ux {name} {safe}\n"
        f"# The -U flag persists across sessions; remove with: set -U --erase {name}"
    )


def snippet_for_current_platform(name: str, value: str) -> str:
    """Return the most useful persistence snippet for the host OS.

    Args:
        name: Env var name.
        value: Env var value.

    Returns:
        One of ``powershell_snippet``, ``bash_snippet``, or ``fish_snippet``
        depending on the current platform.
    """
    system = platform.system()
    if system == "Windows":
        return powershell_snippet(name, value)
    shell = os.environ.get("SHELL", "")
    if shell.endswith("fish"):
        return fish_snippet(name, value)
    return bash_snippet(name, value)


def all_snippets(name: str, value: str) -> dict[str, str]:
    """Return every persistence snippet, keyed by shell name.

    Useful for a dialog that lets the user copy whichever matches their setup.
    """
    return {
        "PowerShell": powershell_snippet(name, value),
        "bash / zsh": bash_snippet(name, value),
        "fish": fish_snippet(name, value),
    }
