"""Config loader: YAML parsing, environment variable expansion, validation.

Usage::

    config = load_config("path/to/config.yaml")
    config = load_config_from_dict({"asr": {"provider": "faster_whisper"}})
"""

import os
import re
from pathlib import Path
from typing import Any

import yaml

from agentvoca.config.schema import FullConfig
from agentvoca.utils.errors import ConfigError

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _expand_env_vars(value: Any) -> Any:
    """Recursively expand ``${VAR_NAME}`` patterns in string values.

    Environment variables that are not set are replaced with an empty string.
    """
    if isinstance(value, str):

        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            return os.environ.get(var_name, "")

        return _ENV_VAR_RE.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load and parse a YAML config file.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed dictionary.

    Raises:
        ConfigError: If the file does not exist or is not valid YAML.
    """
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in config file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Config file {path} must contain a top-level mapping (dictionary).")

    return data


def load_config(path: str | Path) -> FullConfig:
    """Load, expand, and validate a YAML config file.

    Steps:
        1. Read and parse the YAML file.
        2. Expand ``${ENV_VAR}`` patterns.
        3. Validate against the pydantic schema.

    Args:
        path: Path to the YAML config file (string or Path).

    Returns:
        Validated FullConfig instance.

    Raises:
        ConfigError: On file-not-found, parse errors, or validation failures.
    """
    config_path = Path(path).expanduser().resolve()
    raw = _load_yaml(config_path)
    return _validate_and_build(raw)


def load_config_from_dict(data: dict[str, Any]) -> FullConfig:
    """Load config from an in-memory dictionary (useful for testing).

    Environment variable expansion is still applied.

    Args:
        data: Raw config dictionary.

    Returns:
        Validated FullConfig instance.

    Raises:
        ConfigError: On validation failures.
    """
    return _validate_and_build(data)


def _validate_and_build(raw: dict[str, Any]) -> FullConfig:
    """Expand env vars in the raw dict and validate against FullConfig.

    Args:
        raw: Raw config dictionary (possibly already parsed from YAML).

    Returns:
        Validated FullConfig instance.
    """
    expanded = _expand_env_vars(raw)

    try:
        return FullConfig.model_validate(expanded, strict=False)
    except Exception as exc:
        # pydantic ValidationError is the most common case
        from pydantic import ValidationError

        if isinstance(exc, ValidationError):
            messages = []
            for err in exc.errors():
                field_path = ".".join(str(loc) for loc in err["loc"])
                msg = err["msg"]
                messages.append(f"  {field_path}: {msg}")
            raise ConfigError("Config validation failed:\n" + "\n".join(messages)) from exc
        raise ConfigError(f"Config validation failed: {exc}") from exc
