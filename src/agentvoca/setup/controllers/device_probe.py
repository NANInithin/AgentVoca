"""Device probe — thin wrapper around ``audio.devices`` for the UI layer.

The wizard and settings window need an input device dropdown that updates
without recreating the audio stream. ``DeviceProbe`` returns a friendly
``(label, value)`` pair per device and caches the result so repeated calls
in the same UI render are cheap.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


def _devices_module():
    """Return ``agentvoca.audio.devices``, importing lazily.

    Imported lazily so headless CI environments without PortAudio can still
    import the wizard — the probe will return an empty list at call time.
    """
    try:
        from agentvoca.audio import devices  # noqa: PLC0415
    except OSError as exc:
        logger.debug("PortAudio unavailable: %s", exc)
        return None
    return devices


def _safe_call(fn, *args, **kwargs):
    """Call a sounddevice-backed helper, returning ``[]`` / ``None`` on failure.

    Headless CI environments often lack PortAudio. We log at debug and return
    an empty result so the wizard and settings window still render — the
    user can then install PortAudio or pick ``"default"``.
    """
    list_fn = _devices_module().list_input_devices
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # OSError, sounddevice.PortAudioError, …
        logger.debug("sounddevice call %s failed: %s", fn.__name__, exc)
        return [] if fn is list_fn else None


@dataclass(frozen=True)
class DeviceEntry:
    """One row in the audio-input dropdown.

    Attributes:
        name: Device name as reported by ``sounddevice`` (used as the config
            value because it matches the existing ``audio.input_device``
            semantics).
        label: Friendly label, with the default marker.
        is_default: True for the system's default input device.
    """

    name: str
    label: str
    is_default: bool


class DeviceProbe:
    """Caches the device list so multiple combo-box renders reuse one probe.

    Usage::

        probe = DeviceProbe()
        for entry in probe.entries():
            combo.addItem(entry.label, entry.name)
    """

    def __init__(self) -> None:
        self._cached: list[DeviceEntry] | None = None

    def refresh(self) -> list[DeviceEntry]:
        """Re-read the device list, replacing the cache."""
        devs = _devices_module()
        if devs is None:
            self._cached = self._fallback_entries()
            return self._cached
        default = _safe_call(devs.get_default_input_device)
        default_name = default["name"] if default else None
        devices = _safe_call(devs.list_input_devices) or []
        entries: list[DeviceEntry] = []
        seen_defaults: set[str] = set()
        for dev in devices:
            name = str(dev["name"])
            is_default = name == default_name
            label = f"{name} (default)" if is_default else name
            entries.append(DeviceEntry(name=name, label=label, is_default=is_default))
            if is_default:
                seen_defaults.add(name)

        # If the system has a default we did not see, surface it explicitly so
        # the user can still pick "default" semantically.
        if default_name and default_name not in seen_defaults:
            entries.insert(
                0,
                DeviceEntry(
                    name="default",
                    label=f"{default_name} (default)",
                    is_default=True,
                ),
            )

        # Always offer the literal "default" entry so users can fall back to
        # the OS-selected device without us hard-coding its name.
        if not any(e.name == "default" for e in entries):
            entries.insert(0, DeviceEntry(name="default", label="System default", is_default=True))

        self._cached = entries
        return entries

    @staticmethod
    def _fallback_entries() -> list[DeviceEntry]:
        """Return at least the 'default' entry when PortAudio is unavailable."""
        return [DeviceEntry(name="default", label="System default", is_default=True)]

    def entries(self) -> list[DeviceEntry]:
        """Return the cached entries, refreshing once on first call."""
        if self._cached is None:
            return self.refresh()
        return self._cached

    @staticmethod
    def resolve_name(value: Optional[str]) -> Optional[str]:
        """Resolve a config value to a concrete device info dict, or None.

        Used by tests and any code path that wants to verify a configured
        device name still exists.
        """
        try:
            return _devices_module().select_device(value)
        except Exception as exc:
            logger.debug("select_device(%r) failed: %s", value, exc)
            return None
