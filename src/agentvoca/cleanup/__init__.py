"""Cleanup providers module.

Provider classes are imported lazily (PEP 562) so that importing this
package does not pull in httpx / heavy cleanup-provider dependencies.
"""

from __future__ import annotations

import importlib

from agentvoca.cleanup.base import CleanupProvider

_LAZY = {
    "NoneCleanupProvider": "agentvoca.cleanup.none",
    "OpenAICompatibleCleanupProvider": "agentvoca.cleanup.openai_compatible",
    "RulesCleanupProvider": "agentvoca.cleanup.rules",
}


_REGISTRY_KEYS = {
    "NoneCleanupProvider": "none",
    "OpenAICompatibleCleanupProvider": "openai_compatible",
    "RulesCleanupProvider": "rules",
}


def __getattr__(name: str):
    if name == "BUILTIN_CLEANUP_PROVIDERS":
        return {
            _REGISTRY_KEYS[cls]: getattr(importlib.import_module(mod), cls)
            for cls, mod in _LAZY.items()
        }
    if name in _LAZY:
        return getattr(importlib.import_module(_LAZY[name]), name)
    raise AttributeError(name)


__all__ = [
    "CleanupProvider",
    "NoneCleanupProvider",
    "OpenAICompatibleCleanupProvider",
    "RulesCleanupProvider",
    "BUILTIN_CLEANUP_PROVIDERS",
]
