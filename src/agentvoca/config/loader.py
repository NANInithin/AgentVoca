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


def load_config_lenient(path: str | Path) -> tuple[FullConfig, str | None]:
    """Load a YAML config and *do not* raise on validation failures.

    Used by the application entry point: if the on-disk config is malformed
    (typically a missing API-key env var from a previous remote setup), we
    still want to start the app so the wizard can guide the user to fix it,
    rather than crashing before the UI ever appears.

    Validation against the pydantic schema is still attempted; if it fails
    the loader falls back to a permissive parse that fills in defaults and
    reports the error message via the second return value. The returned
    ``FullConfig`` is best-effort: it has the fields the user saved, with
    defaults substituted for anything missing, but the API-key check has
    been skipped. Saving the draft will re-run the strict validator.

    Args:
        path: Path to the YAML config file.

    Returns:
        ``(config, error_message)``. ``error_message`` is ``None`` on
        success and a human-readable string when the loader had to fall back.

    Raises:
        ConfigError: Only for file-not-found or YAML parse errors. Validation
            errors are caught and reported via the tuple.
    """
    config_path = Path(path).expanduser().resolve()
    raw = _load_yaml(config_path)
    expanded = _expand_env_vars(raw)
    try:
        return _validate_and_build(expanded), None
    except ConfigError as exc:
        # Strict validation failed. The most common reason is a missing
        # API-key env var (the ``_validate_api_key_env`` model-validator),
        # but it could be anything (e.g. an enum value the user typoed).
        # In either case the wizard needs the parsed fields so the user
        # can see and fix the problem.
        config = _construct_lenient(expanded)
        return config, str(exc)


def _construct_lenient(expanded: dict[str, Any]) -> FullConfig:
    """Build a ``FullConfig`` without running the model validators.

    The pydantic ``_validate_api_key_env`` model-validator refuses to let
    a remote provider reach a state where the env var is unset. We want
    to do exactly that here so the wizard can show the user the broken
    config, so we bypass the validator by setting an env-var *flag* and
    falling back to ``model_validate(strict=False)`` after the bypass.

    The bypass works by temporarily setting every ``api_key_env`` the user
    referenced in their config so the validator sees a green light. We
    never use these fake values; we just need them to exist for the
    duration of the validate call. The real env-var checks at runtime
    (``OpenAICompatibleCleanupProvider.is_available`` and friends) are
    unaffected — they read ``os.environ`` directly.

    Args:
        expanded: The env-var-expanded raw dict from ``_load_yaml``.

    Returns:
        A best-effort ``FullConfig``. Falls back to a hard default if even
        the permissive construct fails (e.g. malformed types).
    """
    sentinel_keys: list[str] = []
    try:
        # Find every api_key_env referenced anywhere in the config and
        # set a sentinel value if it isn't already in os.environ. This
        # makes the strict validator see a green light for the duration
        # of this call, without mutating the user's real key.
        for section in ("asr", "cleanup", "vision"):
            block = expanded.get(section) or {}
            env_name = block.get("api_key_env") if isinstance(block, dict) else None
            if env_name and env_name not in os.environ:
                os.environ[env_name] = "__lenient_loader_placeholder__"
                sentinel_keys.append(env_name)
        return FullConfig.model_validate(expanded, strict=False)
    except Exception:
        from agentvoca.config.schema import ASRConfig  # noqa: PLC0415

        return FullConfig(asr=ASRConfig(provider="faster_whisper", model="base"))
    finally:
        for key in sentinel_keys:
            os.environ.pop(key, None)


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
