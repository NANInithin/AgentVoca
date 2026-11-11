"""Saved API keys backed by the OS credential store.

Providers read API keys from environment variables (``api_key_env``). This
module lets the UI save a key once and have it back on every launch: the value
goes into the OS credential store via ``keyring`` (Windows Credential Manager,
macOS Keychain, Secret Service on Linux) and is copied into ``os.environ`` at
startup. A variable already set in the user's environment always wins.

Key values are never written to a plain file. ``~/.agentvoca/keys.json`` only
records which names are saved, when, and how long to keep them, because the
credential store cannot be enumerated.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE = "agentvoca"

KEEP_FOREVER = "forever"
KEEP_SESSION = "session"
_DAY_S = 86_400
_RETENTION_DAYS = {"1d": 1, "7d": 7, "30d": 30, "90d": 90}

RETENTION_CHOICES: list[tuple[str, str]] = [
    ("Keep until I delete it", KEEP_FOREVER),
    ("Delete when AgentVoca closes", KEEP_SESSION),
    ("Delete after 1 day", "1d"),
    ("Delete after 7 days", "7d"),
    ("Delete after 30 days", "30d"),
    ("Delete after 90 days", "90d"),
]

_KNOWN_HOST_KEYS = {
    "api.openai.com": "OPENAI_API_KEY",
    "openrouter.ai": "OPENROUTER_API_KEY",
    "groq.com": "GROQ_API_KEY",
    "anthropic.com": "ANTHROPIC_API_KEY",
}
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "[::1]")

# Names this process put into os.environ (saved keys loaded at startup or keys
# saved from the UI), so deleting a key never removes a variable the user set
# in their own shell.
_injected: set[str] = set()
_session_only: set[str] = set()


@dataclass
class SavedKey:
    name: str
    retention: str = KEEP_FOREVER
    saved_at: float = 0.0

    @property
    def expires_at(self) -> float | None:
        days = _RETENTION_DAYS.get(self.retention)
        return self.saved_at + days * _DAY_S if days else None


@dataclass
class KeyStatus:
    """Where the key for ``name`` currently comes from.

    ``source`` is ``"saved"`` (credential store), ``"session"`` (this run
    only), ``"environment"`` (the user's own env var) or ``None`` (missing).
    """

    name: str
    source: str | None
    preview: str = ""
    retention: str | None = None
    expires_at: float | None = None


# ── Helpers ───────────────────────────────────────────────────────────


def default_key_env(endpoint: str | None, role: str) -> str | None:
    """Pick an env var name for a provider endpoint.

    Well-known hosts get their conventional name so a key the user already
    exported keeps working. Local servers (Ollama, LM Studio) need no key.
    """
    ep = (endpoint or "https://api.openai.com/v1").lower()
    if any(host in ep for host in _LOCAL_HOSTS):
        return None
    for host, name in _KNOWN_HOST_KEYS.items():
        if host in ep:
            return name
    return f"AGENTVOCA_{role.upper()}_API_KEY"


def _index_path() -> Path:
    return Path.home() / ".agentvoca" / "keys.json"


def _read_index() -> dict[str, SavedKey]:
    path = _index_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("Ignoring unreadable %s (%s)", path, exc)
        return {}
    entries: dict[str, SavedKey] = {}
    for item in raw.get("keys", []) if isinstance(raw, dict) else []:
        try:
            key = SavedKey(
                name=str(item["name"]),
                retention=str(item.get("retention", KEEP_FOREVER)),
                saved_at=float(item.get("saved_at", 0.0)),
            )
        except (KeyError, TypeError, ValueError):
            continue
        entries[key.name] = key
    return entries


def _write_index(entries: dict[str, SavedKey]) -> None:
    path = _index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = {"keys": [asdict(e) for e in entries.values()]}
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _keyring():
    """Return the ``keyring`` module if a usable backend exists, else None."""
    try:
        import keyring  # noqa: PLC0415
        from keyring.backends import fail  # noqa: PLC0415

        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
        return keyring
    except Exception:
        logger.debug("No usable credential store", exc_info=True)
        return None


def secure_storage_available() -> bool:
    return _keyring() is not None


def _remove_from_store(name: str) -> None:
    kr = _keyring()
    if kr is None:
        return
    try:
        kr.delete_password(SERVICE, name)
    except Exception:
        logger.debug("Credential store had no entry for %s", name, exc_info=True)


def _preview(value: str) -> str:
    return value[-4:] if len(value) >= 4 else ""


# ── Public API ────────────────────────────────────────────────────────


def save_key(name: str, value: str, retention: str = KEEP_FOREVER) -> bool:
    """Save ``value`` as the key for env var ``name`` and apply it now.

    Returns True when the key will survive a restart. Returns False when it
    is only kept for this session, either by choice or because no credential
    store is available.
    """
    if not name or not value:
        raise ValueError("Both the key name and value are required")
    os.environ[name] = value
    _injected.add(name)
    entries = _read_index()

    if retention == KEEP_SESSION:
        if entries.pop(name, None) is not None:
            _write_index(entries)
        _remove_from_store(name)
        _session_only.add(name)
        return False

    kr = _keyring()
    if kr is None:
        _session_only.add(name)
        return False
    try:
        kr.set_password(SERVICE, name, value)
    except Exception:
        logger.warning("Could not save %s to the credential store", name, exc_info=True)
        _session_only.add(name)
        return False
    _session_only.discard(name)
    entries[name] = SavedKey(name=name, retention=retention, saved_at=time.time())
    _write_index(entries)
    return True


def delete_key(name: str) -> None:
    """Remove a saved key from the credential store and from this session."""
    entries = _read_index()
    if entries.pop(name, None) is not None:
        _write_index(entries)
    _remove_from_store(name)
    _session_only.discard(name)
    if name in _injected:
        os.environ.pop(name, None)
        _injected.discard(name)


def key_status(name: str) -> KeyStatus:
    value = os.environ.get(name, "") if name else ""
    entry = _read_index().get(name) if name else None
    if name in _session_only and value:
        return KeyStatus(name, "session", _preview(value), KEEP_SESSION)
    if entry is not None and (value or name not in os.environ):
        return KeyStatus(name, "saved", _preview(value), entry.retention, entry.expires_at)
    if value:
        return KeyStatus(name, "environment", _preview(value))
    return KeyStatus(name, None)


def purge_expired(now: float | None = None) -> list[str]:
    """Delete saved keys whose retention period has passed."""
    now = time.time() if now is None else now
    expired = [
        e.name for e in _read_index().values() if e.expires_at is not None and e.expires_at <= now
    ]
    for name in expired:
        delete_key(name)
        logger.info("Deleted expired API key %s", name)
    return expired


def load_saved_keys() -> list[str]:
    """Copy saved keys into ``os.environ``; return the names applied.

    Expired keys are purged first. Names already set in the environment are
    left untouched so a user's own env var takes precedence.
    """
    purge_expired()
    entries = _read_index()
    if not entries:
        return []
    kr = _keyring()
    if kr is None:
        logger.warning("Saved API keys exist but no credential store is available")
        return []
    applied: list[str] = []
    stale: list[str] = []
    for name in entries:
        if name in os.environ:
            continue
        try:
            value = kr.get_password(SERVICE, name)
        except Exception:
            logger.warning("Could not read %s from the credential store", name, exc_info=True)
            continue
        if not value:
            stale.append(name)
            continue
        os.environ[name] = value
        _injected.add(name)
        applied.append(name)
    if stale:
        for name in stale:
            entries.pop(name, None)
        _write_index(entries)
    return applied


def forget_session_keys() -> None:
    """Drop keys that were only meant to last for this session."""
    for name in list(_session_only):
        if name in _injected:
            os.environ.pop(name, None)
            _injected.discard(name)
    _session_only.clear()
