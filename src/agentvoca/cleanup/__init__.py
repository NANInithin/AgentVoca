"""Cleanup providers module.

Exports all built-in cleanup providers.
"""

from .none import NoneCleanupProvider
from .openai_compatible import OpenAICompatibleCleanupProvider
from .rules import RulesCleanupProvider

BUILTIN_CLEANUP_PROVIDERS = {
    "none": NoneCleanupProvider,
    "openai_compatible": OpenAICompatibleCleanupProvider,
    "rules": RulesCleanupProvider,
}

__all__ = [
    "NoneCleanupProvider",
    "OpenAICompatibleCleanupProvider",
    "RulesCleanupProvider",
    "BUILTIN_CLEANUP_PROVIDERS",
]
