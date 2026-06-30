"""First-run detection and ``state.json`` management.

The wizard auto-opens on every launch by user choice (v0.3.5 decision). A
small JSON file at ``~/.agentvoca/state.json`` records user preferences that
are not part of the YAML config:

- ``wizard_auto_open`` — whether to pop the wizard at startup (default True).
- ``last_wizard_version`` — version string; used to re-prompt on schema-breaking
  upgrades. Not used by v0.3.5 but reserved.
- ``first_run_complete`` — set after the user successfully saves a config so
  telemetry-style features can distinguish new installs. Not load-bearing for
  the wizard itself.

The wizard writes this file via ``write_state``. ``load_state`` always returns
a populated ``AppState`` (with defaults) even if the file is absent or
malformed, so callers do not need to handle the missing case separately.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Defaults ──────────────────────────────────────────────────────────

_DEFAULTS = {
    "wizard_auto_open": True,
    "last_wizard_version": "",
    "first_run_complete": False,
}


@dataclass
class AppState:
    """In-memory view of ``state.json``.

    Attributes:
        wizard_auto_open: Whether to show the wizard at startup.
        last_wizard_version: Version string of the wizard last run.
        first_run_complete: True after the user has saved a config once.
    """

    wizard_auto_open: bool = True
    last_wizard_version: str = ""
    first_run_complete: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppState":
        """Build an ``AppState`` from a raw dict, ignoring unknown keys."""
        return cls(
            wizard_auto_open=bool(data.get("wizard_auto_open", _DEFAULTS["wizard_auto_open"])),
            last_wizard_version=str(data.get("last_wizard_version", "")),
            first_run_complete=bool(
                data.get("first_run_complete", _DEFAULTS["first_run_complete"])
            ),
        )


# ── Paths ────────────────────────────────────────────────────────────


def state_path() -> Path:
    """Return the canonical ``state.json`` path, ensuring the dir exists."""
    p = Path.home() / ".agentvoca" / "state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    """Return the canonical ``config.yaml`` path (does not create the dir)."""
    return Path.home() / ".agentvoca" / "config.yaml"


# ── Load / save ───────────────────────────────────────────────────────


def load_state() -> AppState:
    """Read ``state.json`` from disk.

    Returns a populated ``AppState`` with defaults if the file is absent,
    unreadable, or malformed. Errors are logged at debug level — the wizard
    must always be able to launch.
    """
    path = state_path()
    if not path.is_file():
        return AppState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Failed to load state.json (%s); using defaults", exc)
        return AppState()
    if not isinstance(raw, dict):
        return AppState()
    return AppState.from_dict(raw)


def write_state(state: AppState) -> None:
    """Persist ``state`` to ``state.json``.

    Best-effort: failures are logged but never raised — losing state.json
    should not break the app.
    """
    path = state_path()
    try:
        path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
    except OSError as exc:
        logger.debug("Failed to write state.json (%s)", exc)


def mark_first_run_complete(version: str = "") -> None:
    """Update state.json to mark first-run complete and bump version."""
    state = load_state()
    state.first_run_complete = True
    if version:
        state.last_wizard_version = version
    write_state(state)


def set_wizard_auto_open(enabled: bool) -> None:
    """Persist the user's preference for showing the wizard at startup."""
    state = load_state()
    state.wizard_auto_open = enabled
    write_state(state)


# ── Sentinel helpers ──────────────────────────────────────────────────


def config_exists() -> bool:
    """Return True if ``config.yaml`` is present at the canonical location."""
    return config_path().is_file() or bool(os.environ.get("AGENTVOCA_CONFIG"))
