"""Persistence helpers for the interactive setup wizard / settings window.

The wizard and the tabbed settings window both write the user's ``FullConfig``
to ``~/.agentvoca/config.yaml``. This module owns that round-trip so both UIs
behave identically:

- ``serialize(config)`` — pydantic → plain Python (yaml-safe) dict.
- ``save_to_disk(config, path)`` — write the config, take a timestamped backup
  of any previous file, and ensure the parent directory exists.
- ``save_to_disk_preserving(config, path)`` — merge the new config on top of
  any existing YAML so unknown keys survive. Used when first writing a brand
  new file from a partial draft so users do not lose prior settings they added
  by hand.

The round-trip is intentionally plain ``yaml.safe_dump`` / ``yaml.safe_load``:
AgentVoca v0.3.5 has committed to the wizard owning configuration, so
preserving hand-written comments is no longer required.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from agentvoca.config.schema import FullConfig
from agentvoca.utils.errors import ConfigError

# ── Serialization ────────────────────────────────────────────────────


def serialize(config: FullConfig) -> dict[str, Any]:
    """Serialize ``FullConfig`` to a yaml-safe dict.

    Args:
        config: A validated ``FullConfig`` instance.

    Returns:
        A plain-dict representation suitable for ``yaml.safe_dump``.
    """
    return config.model_dump(mode="json", exclude_defaults=False)


# ── Disk I/O ─────────────────────────────────────────────────────────


def _ensure_parent(path: Path) -> None:
    """Create the parent directory of ``path`` if it does not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _backup_existing(path: Path) -> Path | None:
    """If ``path`` exists, copy it to ``<path>.bak.<timestamp>``.

    Returns the backup path, or ``None`` if there was nothing to back up.
    """
    if not path.is_file():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak.{stamp}")
    backup.write_bytes(path.read_bytes())
    return backup


def save_to_disk(config: FullConfig, path: str | Path) -> Path:
    """Write ``config`` to ``path`` as YAML, replacing any existing file.

    The previous file (if any) is preserved as ``<path>.bak.<timestamp>``.

    Args:
        config: The validated ``FullConfig`` to write.
        path: Destination path (string or ``Path``).

    Returns:
        The backup path, or an empty ``Path`` if nothing was backed up.

    Raises:
        ConfigError: If serialization or the disk write fails.
    """
    return _write_yaml(serialize(config), Path(path).expanduser().resolve())


def save_to_disk_preserving(config: FullConfig, path: str | Path) -> Path:
    """Merge ``config`` into any existing YAML at ``path`` and write the result.

    Useful when the wizard only knows about a subset of keys and we must not
    destroy keys the user wrote by hand (e.g. provider-specific ``extra``
    blocks we do not model in the UI). The merge is shallow at the section
    level: top-level keys in ``config`` replace the corresponding keys in the
    existing file; other top-level keys are left untouched.

    Args:
        config: The validated ``FullConfig`` to write.
        path: Destination path.

    Returns:
        The backup path, or an empty ``Path`` if nothing was backed up.
    """
    dest = Path(path).expanduser().resolve()
    existing: dict[str, Any] = {}
    try:
        if dest.is_file():
            loaded = yaml.safe_load(dest.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                existing = loaded
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Failed to read config file {dest}: {exc}") from exc

    new_dump = serialize(config)

    def merge(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
        result = dict(old)
        for key, value in new.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = merge(result[key], value)
            else:
                result[key] = value
        return result

    merged = merge(existing, new_dump)

    # Validate to catch any drift the wizard might have introduced, but
    # write the merged dict directly so unknown top-level keys survive.
    known_subset = {k: v for k, v in merged.items() if k in new_dump}
    FullConfig.model_validate(known_subset, strict=False)
    return _write_yaml(merged, dest)


def _write_yaml(data: dict[str, Any], dest: Path) -> Path:
    """Backup + write helper shared by the two save paths."""
    temporary: Path | None = None
    try:
        _ensure_parent(dest)
        dumped = yaml.safe_dump(
            data,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=dest.parent,
            prefix=f".{dest.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(dumped)
            handle.flush()
            os.fsync(handle.fileno())
        backup = _backup_existing(dest)
        os.replace(temporary, dest)
        temporary = None
    except OSError as exc:
        raise ConfigError(f"Failed to write config file {dest}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to serialize config to YAML: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return backup or Path()


# ── Reading ──────────────────────────────────────────────────────────


def load_from_disk(path: str | Path) -> FullConfig:
    """Load and validate a YAML config from disk.

    Thin wrapper around ``load_config`` so wizard/symmetric code reads from
    one helper.

    Args:
        path: Path to the YAML file.

    Returns:
        The validated ``FullConfig``.

    Raises:
        ConfigError: On file-not-found, parse errors, or validation failures.
    """
    from agentvoca.config.loader import load_config  # noqa: PLC0415

    return load_config(path)
