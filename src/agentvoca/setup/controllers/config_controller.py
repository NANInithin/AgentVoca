"""ConfigController — the wizard and settings window's source of truth.

A ``ConfigController`` owns an in-memory ``FullConfig`` draft, validates it on
demand, and writes it to disk on save. It also computes the set of changed
paths between the draft and the originally-loaded config, so the UI can
display a "restart required" banner with the exact field names.

Threading: the controller is intended to be touched from the Qt GUI thread
only. Saving synchronously writes to disk, which is fast for a YAML file of
this size.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from agentvoca.config.schema import FullConfig
from agentvoca.setup import persistence
from agentvoca.setup.controllers import restart_policy
from agentvoca.utils.errors import ConfigError

logger = logging.getLogger(__name__)


# ── Result types ──────────────────────────────────────────────────────


@dataclass
class SaveResult:
    """Result of a save attempt.

    Attributes:
        success: True if the config was written.
        backup_path: Path to the timestamped backup, if any.
        changed_paths: Dotted paths of every config field that differs from
            the originally-loaded config.
        restart_paths: Subset of ``changed_paths`` that require an app restart.
        hot_paths: Subset of ``changed_paths`` that can be applied live.
        error: ``ConfigError`` message if ``success`` is False.
    """

    success: bool
    backup_path: Path = field(default_factory=Path)
    changed_paths: list[str] = field(default_factory=list)
    restart_paths: list[str] = field(default_factory=list)
    hot_paths: list[str] = field(default_factory=list)
    error: str | None = None


# ── Controller ────────────────────────────────────────────────────────


class ConfigController:
    """In-memory editable copy of ``FullConfig`` with validation and save.

    The controller is constructed with a path and an initial config (typically
    loaded from disk by ``main.py``). Pages mutate the draft via ``set_value``
    / nested helper methods; on ``save()`` the draft is validated and written.
    """

    def __init__(self, config_path: Path, initial: FullConfig) -> None:
        self._path = Path(config_path).expanduser().resolve()
        self._original = initial
        self._draft = initial.model_copy(deep=True)
        # Pre-serialise to dicts once so ``_diff_paths`` can walk them without
        # caring about pydantic model instances.
        self._original_dump = self._original.model_dump()
        self._draft_dump = self._draft.model_dump()

    # ── Accessors ──────────────────────────────────────────────────────

    @property
    def path(self) -> Path:
        """The on-disk path this controller writes to."""
        return self._path

    @property
    def draft(self) -> FullConfig:
        """The current draft (do not mutate directly; use setter helpers)."""
        return self._draft

    @property
    def original(self) -> FullConfig:
        """The config as it was when this controller was created."""
        return self._original

    def is_dirty(self) -> bool:
        """Return True if the draft differs from the original."""
        return bool(self.changed_paths())

    def changed_paths(self) -> list[str]:
        """Return dotted paths of every field that differs between draft and original."""
        return list(_diff_paths(self._original_dump, self._draft_dump))

    # ── Mutation helpers ───────────────────────────────────────────────

    def replace_draft(self, new_draft: FullConfig) -> None:
        """Replace the entire draft (used by "Restore defaults" and similar)."""
        self._draft = new_draft.model_copy(deep=True)
        self._draft_dump = self._draft.model_dump()

    def update_section(self, **kwargs: Any) -> None:
        """Mutate the draft by passing keyword args to ``FullConfig.model_copy``.

        Only the keys present in ``kwargs`` are replaced. Example::

            controller.update_section(app={"profile": "technical", "language": "en"})

        Args:
            **kwargs: Top-level section names mapped to new values (dicts or
                pydantic models).
        """
        data = dict(self._draft_dump)
        for section, value in kwargs.items():
            if value is None:
                continue
            if isinstance(value, dict):
                data[section] = {**(data.get(section) or {}), **value}
            else:
                data[section] = value.model_dump() if hasattr(value, "model_dump") else value
        self._draft = FullConfig.model_validate(data, strict=False)
        self._draft_dump = data

    # ── Validation ─────────────────────────────────────────────────────

    def validate(self) -> tuple[bool, str | None]:
        """Re-validate the draft against the pydantic schema.

        Returns:
            (ok, error_message). ``error_message`` is ``None`` on success.
        """
        try:
            # Round-tripping through model_validate catches drift even if the
            # user typed invalid combinations interactively.
            FullConfig.model_validate(self._draft_dump, strict=False)
            return True, None
        except Exception as exc:  # pydantic.ValidationError
            return False, str(exc)

    # ── Persistence ────────────────────────────────────────────────────

    def save(self) -> SaveResult:
        """Validate, persist, and compute the change set.

        On success, the original is updated so subsequent ``changed_paths()``
        returns paths since this save (not since construction).
        """
        ok, err = self.validate()
        if not ok:
            return SaveResult(success=False, error=err or "validation failed")

        try:
            backup = persistence.save_to_disk(self._draft, self._path)
        except ConfigError as exc:
            return SaveResult(success=False, error=str(exc))

        changed = self.changed_paths()
        hot, restart = restart_policy.partition(changed)

        logger.info(
            "Config saved to %s (changed=%d, hot=%d, restart=%d)",
            self._path,
            len(changed),
            len(hot),
            len(restart),
        )

        # Promote the draft to original so the diff is measured against the
        # just-saved file on subsequent edits.
        self._original = self._draft.model_copy(deep=True)
        self._original_dump = dict(self._draft_dump)

        return SaveResult(
            success=True,
            backup_path=backup,
            changed_paths=changed,
            hot_paths=hot,
            restart_paths=restart,
        )

    def revert(self) -> None:
        """Discard all draft changes and restore the originally-loaded config."""
        self._draft = self._original.model_copy(deep=True)
        self._draft_dump = dict(self._original_dump)

    # ── Diff utilities ─────────────────────────────────────────────────

    def restart_paths(self) -> list[str]:
        """Return the subset of ``changed_paths()`` that require a restart."""
        return [p for p in self.changed_paths() if restart_policy.is_restart_field(p)]


# ── Diff helpers ──────────────────────────────────────────────────────


_PRIMITIVE = (str, int, float, bool, type(None))


def _values_equal(a: Any, b: Any) -> bool:
    """Compare two values that may be dicts/lists/primitives."""
    if type(a) is not type(b) and not (isinstance(a, _PRIMITIVE) and isinstance(b, _PRIMITIVE)):
        # pydantic may surface str vs Path etc.; fall back to repr compare
        return repr(a) == repr(b)
    if isinstance(a, dict):
        if a.keys() != b.keys():
            return False
        return all(_values_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(_values_equal(x, y) for x, y in zip(a, b))
    return a == b


def _diff_paths(a: Any, b: Any, prefix: str = "") -> Iterable[str]:
    """Yield dotted paths where ``a`` and ``b`` differ.

    Walks dicts and lists recursively. Scalars are compared directly.
    """
    if _values_equal(a, b):
        return

    if isinstance(a, dict) and isinstance(b, dict):
        for key in set(a) | set(b):
            yield from _diff_paths(a.get(key), b.get(key), _join(prefix, key))
        return

    if isinstance(a, list) and isinstance(b, list):
        # Treat lists as opaque if both are present and length differs; this
        # matches the user's expectation of "I added a vocab term" being a
        # change at the vocabulary.inline path, not inside the list.
        yield prefix or "."
        return

    yield prefix or "."


def _join(prefix: str, key: Any) -> str:
    """Join a dotted prefix with a list/dict key."""
    key_str = str(key)
    if not prefix:
        return key_str
    return f"{prefix}.{key_str}"


# ── Convenience ───────────────────────────────────────────────────────


def load_controller(path: str | Path) -> ConfigController:
    """Build a ``ConfigController`` from a YAML file on disk.

    Falls back to the v1 zero-config defaults if the file does not exist,
    matching the behavior in ``main.py`` so the wizard sees the same starting
    point the running app would.
    """
    p = Path(path).expanduser().resolve()
    if p.is_file():
        config = persistence.load_from_disk(p)
    else:
        from agentvoca.config.schema import ASRConfig  # noqa: PLC0415

        config = FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))
    return ConfigController(config_path=p, initial=config)


def defaults_controller(path: str | Path) -> ConfigController:
    """Build a controller seeded with the v1 zero-config defaults.

    Used by the wizard's "Restore defaults" button and the settings window's
    "Reset" action.
    """
    from agentvoca.config.schema import ASRConfig  # noqa: PLC0415

    p = Path(path).expanduser().resolve()
    config = FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))
    return ConfigController(config_path=p, initial=config)
