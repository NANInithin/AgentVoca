"""Provider registry for ASR, cleanup, and insertion modules.

The registry maps string names to provider classes. The orchestrator (or tests)
construct instances by calling ``get_*`` with a config object.

R14: built-in entries are registered as ``"module:ClassName"`` dotted paths
and resolved on first lookup. This keeps ``ctranslate2`` / numpy / heavy
provider imports out of the cold-start import path.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Type, Union

from agentvoca.config.schema import (
    ASRConfig,
    CleanupConfig,
    InsertionConfig,
    ObserverCompileConfig,
    ObserverOCRConfig,
    VisionConfig,
)
from agentvoca.utils.errors import ProviderNotFoundError

if TYPE_CHECKING:
    from ..asr.base import ASRProvider
    from ..cleanup.base import CleanupProvider
    from ..insertion.base import InsertionStrategy

    # v0.4.0 Observer namespaces — the ABCs live in modules owned by
    # Track 2 (observer/ocr/base.py) and Track 3 (observer/compile/base.py).
    # TYPE_CHECKING-only import keeps this module importable before those
    # packages exist; a runtime get_ocr / get_compiler call resolves
    # the dotted path lazily.
    from ..observer.compile.base import SessionCompiler
    from ..observer.ocr.base import OCRProvider
    from ..vision.base import VisionProvider

# A registered entry is either an already-imported class (the public
# contract for plugins and tests) or a "module:Class" string for lazy
# built-ins. Resolved entries are cached back into the same dict so the
# import runs at most once per name.
_ProviderEntry = Union[Type, str]


class ProviderRegistry:
    """Central registry for provider and strategy classes.

    Each provider type (ASR, cleanup, insertion) has its own namespace.
    Registering a class does not instantiate it — instances are created on
    demand via ``get_*`` methods.
    """

    def __init__(self, register_builtins: bool = True) -> None:
        self._asr: dict[str, _ProviderEntry] = {}
        self._cleanup: dict[str, _ProviderEntry] = {}
        self._insertion: dict[str, _ProviderEntry] = {}
        self._vision: dict[str, _ProviderEntry] = {}
        # v0.4.0 Observer namespaces. Built-ins are registered by Tracks
        # 2 and 3 respectively, in disjoint _register_builtins lines below.
        self._ocr: dict[str, _ProviderEntry] = {}
        self._compiler: dict[str, _ProviderEntry] = {}
        if register_builtins:
            self._register_builtins()

    def _register_builtins(self) -> None:
        """Register all built-in providers and strategies as dotted paths.

        No provider package is imported here — the dotted paths are
        resolved on the first ``get_*`` call that needs them. This keeps
        ``faster_whisper.py`` (which imports ctranslate2 and runs
        ``_register_cuda_dlls``) and other heavy modules out of the
        cold-start import graph.
        """
        self.register_asr("faster_whisper", "agentvoca.asr.faster_whisper:FasterWhisperProvider")
        self.register_asr(
            "openai_compatible",
            "agentvoca.asr.openai_compatible:OpenAICompatibleASRProvider",
        )
        self.register_cleanup("none", "agentvoca.cleanup.none:NoneCleanupProvider")
        self.register_cleanup(
            "openai_compatible",
            "agentvoca.cleanup.openai_compatible:OpenAICompatibleCleanupProvider",
        )
        self.register_cleanup("rules", "agentvoca.cleanup.rules:RulesCleanupProvider")
        self.register_vision(
            "openai_compatible",
            "agentvoca.vision.openai_compatible:OpenAICompatibleVisionProvider",
        )
        # Insertion strategies are light (pyautogui only) but register
        # lazily too for symmetry.
        self.register_insertion(
            "keyboard", "agentvoca.insertion.keyboard:KeyboardInsertionStrategy"
        )
        self.register_insertion(
            "clipboard", "agentvoca.insertion.clipboard:ClipboardInsertionStrategy"
        )
        # v0.4.0 Observer OCR providers — registered by Track 2
        self.register_ocr("rapidocr", "agentvoca.observer.ocr.rapidocr:RapidOCRProvider")
        self.register_ocr("none", "agentvoca.observer.ocr.none:NoneOCRProvider")
        self.register_ocr(
            "openai_compatible",
            "agentvoca.observer.ocr.openai_compatible:OpenAICompatibleOCRProvider",
        )
        # v0.4.0 Observer compilers — registered by Track 3

    def _resolve(self, entry: _ProviderEntry) -> type:
        """Resolve a lazily-registered ``"module:Class"`` path to a class."""
        if isinstance(entry, str):
            module_name, _, class_name = entry.partition(":")
            module = importlib.import_module(module_name)
            return getattr(module, class_name)
        return entry

    # ── Registration ──────────────────────────────────────────────────

    def register_asr(self, name: str, cls: Type[ASRProvider]) -> None:
        """Register an ASR provider class under the given name.

        Args:
            name: Unique registry key (e.g., ``"faster_whisper"``).
            cls: A concrete subclass of ``ASRProvider`` or a
                ``"module:Class"`` dotted path.
        """
        self._asr[name] = cls

    def register_cleanup(self, name: str, cls: Type[CleanupProvider]) -> None:
        """Register a cleanup provider class under the given name.

        Args:
            name: Unique registry key (e.g., ``"rules"``).
            cls: A concrete subclass of ``CleanupProvider`` or a
                ``"module:Class"`` dotted path.
        """
        self._cleanup[name] = cls

    def register_insertion(self, name: str, cls: Type[InsertionStrategy]) -> None:
        """Register an insertion strategy class under the given name.

        Args:
            name: Unique registry key (e.g., ``"keyboard"``).
            cls: A concrete subclass of ``InsertionStrategy`` or a
                ``"module:Class"`` dotted path.
        """
        self._insertion[name] = cls

    def register_vision(self, name: str, cls: Type[VisionProvider]) -> None:
        """Register a vision provider class under the given name.

        Args:
            name: Unique registry key (e.g., ``"openai_compatible"``).
            cls: A concrete subclass of ``VisionProvider`` or a
                ``"module:Class"`` dotted path.
        """
        self._vision[name] = cls

    def register_ocr(self, name: str, cls: Type["OCRProvider"]) -> None:
        """Register an Observer OCR provider class under the given name.

        Args:
            name: Unique registry key (e.g., ``"rapidocr"``).
            cls: A concrete subclass of ``OCRProvider`` or a
                ``"module:Class"`` dotted path. Registered by Track 2.
        """
        self._ocr[name] = cls

    def register_compiler(self, name: str, cls: Type["SessionCompiler"]) -> None:
        """Register an Observer session-compiler class under the given name.

        Args:
            name: Unique registry key (e.g., ``"rules"``).
            cls: A concrete subclass of ``SessionCompiler`` or a
                ``"module:Class"`` dotted path. Registered by Track 3.
        """
        self._compiler[name] = cls

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
        entry = self._asr.get(name)
        if entry is None:
            available = ", ".join(sorted(self._asr.keys()))
            raise ProviderNotFoundError(
                f"Unknown ASR provider '{name}'. Available: {available}. Check docs/providers.md."
            )
        cls = self._resolve(entry)
        self._asr[name] = cls  # cache the resolved class
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
        entry = self._cleanup.get(name)
        if entry is None:
            available = ", ".join(sorted(self._cleanup.keys()))
            raise ProviderNotFoundError(
                f"Unknown cleanup provider '{name}'. Available: {available}."
            )
        cls = self._resolve(entry)
        self._cleanup[name] = cls
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
        entry = self._insertion.get(name)
        if entry is None:
            available = ", ".join(sorted(self._insertion.keys()))
            raise ProviderNotFoundError(
                f"Unknown insertion strategy '{name}'. Available: {available}."
            )
        cls = self._resolve(entry)
        self._insertion[name] = cls
        return cls(config=config)

    def get_vision(self, config: VisionConfig) -> VisionProvider:
        """Construct and return a vision provider from config.

        Args:
            config: The vision configuration block.

        Returns:
            A new ``VisionProvider`` instance.

        Raises:
            ProviderNotFoundError: If ``config.provider`` is not registered.
        """
        name = config.provider
        entry = self._vision.get(name)
        if entry is None:
            available = ", ".join(sorted(self._vision.keys()))
            raise ProviderNotFoundError(
                f"Unknown vision provider '{name}'. Available: {available}."
            )
        cls = self._resolve(entry)
        self._vision[name] = cls
        return cls(config=config)

    def get_ocr(self, config: ObserverOCRConfig) -> "OCRProvider":
        """Construct and return an Observer OCR provider from config.

        Args:
            config: The Observer OCR configuration block.

        Returns:
            A new ``OCRProvider`` instance.

        Raises:
            ProviderNotFoundError: If ``config.provider`` is not registered.
        """
        name = config.provider
        entry = self._ocr.get(name)
        if entry is None:
            available = ", ".join(sorted(self._ocr.keys()))
            raise ProviderNotFoundError(
                f"Unknown Observer OCR provider '{name}'. Available: {available}."
            )
        cls = self._resolve(entry)
        self._ocr[name] = cls
        return cls(config=config)

    def get_compiler(self, config: ObserverCompileConfig) -> "SessionCompiler":
        """Construct and return an Observer session compiler from config.

        Args:
            config: The Observer compile configuration block.

        Returns:
            A new ``SessionCompiler`` instance.

        Raises:
            ProviderNotFoundError: If ``config.provider`` is not registered.
        """
        name = config.provider
        entry = self._compiler.get(name)
        if entry is None:
            available = ", ".join(sorted(self._compiler.keys()))
            raise ProviderNotFoundError(
                f"Unknown Observer compiler '{name}'. Available: {available}."
            )
        cls = self._resolve(entry)
        self._compiler[name] = cls
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

    def list_vision(self) -> list[str]:
        """Return a sorted list of registered vision provider names."""
        return sorted(self._vision.keys())

    def list_ocr(self) -> list[str]:
        """Return a sorted list of registered Observer OCR provider names."""
        return sorted(self._ocr.keys())

    def list_compiler(self) -> list[str]:
        """Return a sorted list of registered Observer compiler names."""
        return sorted(self._compiler.keys())
