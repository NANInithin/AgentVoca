"""Provider registry for ASR, cleanup, and insertion modules.

The registry maps string names to provider classes. The orchestrator (or tests)
construct instances by calling ``get_*`` with a config object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Type

from agentvoca.config.schema import ASRConfig, CleanupConfig, InsertionConfig
from agentvoca.utils.errors import ProviderNotFoundError

if TYPE_CHECKING:
    from ..asr.base import ASRProvider
    from ..cleanup.base import CleanupProvider
    from ..insertion.base import InsertionStrategy


class ProviderRegistry:
    """Central registry for provider and strategy classes.

    Each provider type (ASR, cleanup, insertion) has its own namespace.
    Registering a class does not instantiate it — instances are created on
    demand via ``get_*`` methods.
    """

    def __init__(self, register_builtins: bool = True) -> None:
        self._asr: dict[str, Type[ASRProvider]] = {}
        self._cleanup: dict[str, Type[CleanupProvider]] = {}
        self._insertion: dict[str, Type[InsertionStrategy]] = {}
        if register_builtins:
            self._register_builtins()

    def _register_builtins(self) -> None:
        """Register all built-in providers and strategies."""
        # We import locally to avoid circular dependencies if any providers
        # were to ever import the registry.
        from agentvoca.asr import BUILTIN_ASR_PROVIDERS
        from agentvoca.cleanup import BUILTIN_CLEANUP_PROVIDERS

        for name, cls in BUILTIN_ASR_PROVIDERS.items():
            self.register_asr(name, cls)
        for name, cls in BUILTIN_CLEANUP_PROVIDERS.items():
            self.register_cleanup(name, cls)

    # ── Registration ──────────────────────────────────────────────────

    def register_asr(self, name: str, cls: Type[ASRProvider]) -> None:
        """Register an ASR provider class under the given name.

        Args:
            name: Unique registry key (e.g., ``"faster_whisper"``).
            cls: A concrete subclass of ``ASRProvider``.
        """
        self._asr[name] = cls

    def register_cleanup(self, name: str, cls: Type[CleanupProvider]) -> None:
        """Register a cleanup provider class under the given name.

        Args:
            name: Unique registry key (e.g., ``"rules"``).
            cls: A concrete subclass of ``CleanupProvider``.
        """
        self._cleanup[name] = cls

    def register_insertion(self, name: str, cls: Type[InsertionStrategy]) -> None:
        """Register an insertion strategy class under the given name.

        Args:
            name: Unique registry key (e.g., ``"keyboard"``).
            cls: A concrete subclass of ``InsertionStrategy``.
        """
        self._insertion[name] = cls

    # ── Lookup / Factory ──────────────────────────────────────────────

    def get_asr(self, config: ASRConfig) -> ASRProvider:
        """Construct and return an ASR provider from config.

        Args:
            config: The ASR configuration block.

        Returns:
            A new ``ASRProvider`` instance.

        Raises:
            ProviderNotFoundError: If ``config.provider`` is not registered.
        """
        name = config.provider
        cls = self._asr.get(name)
        if cls is None:
            available = ", ".join(sorted(self._asr.keys()))
            raise ProviderNotFoundError(
                f"Unknown ASR provider '{name}'. Available: {available}. Check docs/providers.md."
            )
        return cls(config=config)

    def get_cleanup(self, config: CleanupConfig) -> CleanupProvider:
        """Construct and return a cleanup provider from config.

        Args:
            config: The cleanup configuration block.

        Returns:
            A new ``CleanupProvider`` instance.

        Raises:
            ProviderNotFoundError: If ``config.provider`` is not registered.
        """
        name = config.provider
        cls = self._cleanup.get(name)
        if cls is None:
            available = ", ".join(sorted(self._cleanup.keys()))
            raise ProviderNotFoundError(
                f"Unknown cleanup provider '{name}'. Available: {available}."
            )
        return cls(config=config)

    def get_insertion(self, config: InsertionConfig) -> InsertionStrategy:
        """Construct and return an insertion strategy from config.

        Args:
            config: The insertion configuration block.

        Returns:
            A new ``InsertionStrategy`` instance.

        Raises:
            ProviderNotFoundError: If ``config.strategy`` is not registered.
        """
        name = config.strategy
        cls = self._insertion.get(name)
        if cls is None:
            available = ", ".join(sorted(self._insertion.keys()))
            raise ProviderNotFoundError(
                f"Unknown insertion strategy '{name}'. Available: {available}."
            )
        return cls(config=config)

    # ── Listing ───────────────────────────────────────────────────────

    def list_asr(self) -> list[str]:
        """Return a sorted list of registered ASR provider names."""
        return sorted(self._asr.keys())

    def list_cleanup(self) -> list[str]:
        """Return a sorted list of registered cleanup provider names."""
        return sorted(self._cleanup.keys())

    def list_insertion(self) -> list[str]:
        """Return a sorted list of registered insertion strategy names."""
        return sorted(self._insertion.keys())
