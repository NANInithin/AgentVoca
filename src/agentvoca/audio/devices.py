"""Audio device enumeration and selection.

Wraps sounddevice to enumerate input devices and select the default
or user-configured device.
"""

from __future__ import annotations

import logging
from typing import Optional

import sounddevice as sd

logger = logging.getLogger(__name__)


def list_input_devices() -> list[dict[str, object]]:
    """List all audio input devices available on the system.

    Returns:
        A list of device info dicts with at least one input channel.
        Each dict contains keys such as ``name``, ``index``,
        ``max_input_channels``, ``default_samplerate``.
    """
    devices: list[dict[str, object]] = []
    for i in range(len(sd.query_devices())):
        info = sd.query_devices(i)
        if info["max_input_channels"] > 0:
            devices.append(
                {
                    "index": i,
                    "name": info["name"],
                    "max_input_channels": info["max_input_channels"],
                    "default_samplerate": info["default_samplerate"],
                }
            )
    return devices


def get_default_input_device() -> Optional[dict[str, object]]:
    """Return the default input device info, or None if none available.

    Returns:
        Device info dict, or None.
    """
    try:
        info = sd.query_devices(kind="input")
        return {
            "index": info["index"],
            "name": info["name"],
            "max_input_channels": info["max_input_channels"],
            "default_samplerate": info["default_samplerate"],
        }
    except sd.PortAudioError:
        logger.warning("No default input device found")
        return None


def select_device(device_name: Optional[str] = None) -> Optional[dict[str, object]]:
    """Select an audio input device by name or return the default.

    Args:
        device_name: Optional device name substring to match.
            If None, the default input device is returned.

    Returns:
        Device info dict, or None if no matching device is found.
    """
    if device_name is None or device_name == "default":
        return get_default_input_device()

    name_lower = device_name.lower()
    for dev in list_input_devices():
        if name_lower in str(dev["name"]).lower():
            return dev

    logger.warning("No input device matching '%s' found", device_name)
    return None
