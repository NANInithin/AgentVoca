"""Unit tests for the provider registry and abstract base classes.

Tests cover:
- Registration and lookup for all three provider types.
- ``ProviderNotFoundError`` for unknown providers.
- Listing registered names.
- ABC contract enforcement (cannot instantiate ABCs directly).
- v0.4.0 Observer OCR + compiler namespaces (lazy dotted-path resolve,
  ProviderNotFoundError, list_* methods).
"""

from typing import Optional

import pytest

from agentvoca.asr.base import ASRProvider
from agentvoca.cleanup.base import CleanupProvider
from agentvoca.config.schema import (
    ASRConfig,
    CleanupConfig,
    InsertionConfig,
    ObserverCompileConfig,
    ObserverOCRConfig,
)
from agentvoca.core.registry import ProviderRegistry
from agentvoca.core.types import (
    ASRContext,
    CleanupContext,
    InsertionResult,
    TranscriptSegment,
)
from agentvoca.insertion.base import InsertionStrategy
from agentvoca.utils.errors import ProviderNotFoundError
from agentvoca.vision.base import VisionProvider

# ── Concrete Mock Providers ──────────────────────────────────────────


class MockASRProvider(ASRProvider):
    """Minimal ASRProvider stub for testing."""

    def __init__(self, config: ASRConfig) -> None:
        self.config = config

    def get_name(self) -> str:
        return "mock_asr"

    def is_available(self) -> bool:
        return True

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> TranscriptSegment:
        return TranscriptSegment(text="mock transcript", is_final=True)

    async def stream_transcribe(
        self,
        audio_stream,  # noqa: ANN001
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> "MockAsyncIterator":  # type: ignore[override]
        return MockAsyncIterator()


class MockAsyncIterator:
    """Minimal async iterator stub for stream_transcribe tests."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class MockCleanupProvider(CleanupProvider):
    """Minimal CleanupProvider stub for testing."""

    def __init__(self, config: CleanupConfig) -> None:
        self.config = config

    def get_name(self) -> str:
        return "mock_cleanup"

    def is_available(self) -> bool:
        return True

    async def rewrite(
        self,
        transcript: str,
        context: Optional[CleanupContext] = None,
    ) -> str:
        return transcript


class MockInsertionStrategy(InsertionStrategy):
    """Minimal InsertionStrategy stub for testing."""

    def __init__(self, config: InsertionConfig) -> None:
        self.config = config

    def get_name(self) -> str:
        return "mock_insert"

    def is_available(self) -> bool:
        return True

    async def insert(self, text: str) -> InsertionResult:
        return InsertionResult(success=True, method_used="keyboard")

    async def undo_last(self) -> bool:
        return True


# ── Registry Tests ───────────────────────────────────────────────────


class TestProviderRegistry:
    """Tests for the ProviderRegistry class."""

    def test_register_and_get_asr(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        registry.register_asr("mock_asr", MockASRProvider)

        config = ASRConfig(provider="mock_asr")
        provider = registry.get_asr(config)

        assert isinstance(provider, ASRProvider)
        assert provider.get_name() == "mock_asr"

    def test_register_and_get_cleanup(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        registry.register_cleanup("mock_cleanup", MockCleanupProvider)

        config = CleanupConfig(provider="mock_cleanup")
        provider = registry.get_cleanup(config)

        assert isinstance(provider, CleanupProvider)
        assert provider.get_name() == "mock_cleanup"

    def test_register_and_get_insertion(self) -> None:
        """InsertionConfig.strategy is a Literal['keyboard','clipboard'];

        so we register the mock under a valid literal key name and verify
        the factory returns it.
        """
        registry = ProviderRegistry(register_builtins=False)
        registry.register_insertion("keyboard", MockInsertionStrategy)

        config = InsertionConfig(strategy="keyboard")
        strategy = registry.get_insertion(config)

        assert isinstance(strategy, InsertionStrategy)
        assert strategy.get_name() == "mock_insert"

    def test_get_asr_unknown(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        config = ASRConfig(provider="nonexistent")

        with pytest.raises(ProviderNotFoundError) as exc:
            registry.get_asr(config)
        assert "nonexistent" in str(exc.value)

    def test_get_cleanup_unknown(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        config = CleanupConfig(provider="nonexistent")

        with pytest.raises(ProviderNotFoundError) as exc:
            registry.get_cleanup(config)
        assert "nonexistent" in str(exc.value)

    def test_get_insertion_unknown(self) -> None:
        """Use a valid literal key that is NOT registered."""
        registry = ProviderRegistry(register_builtins=False)
        # "clipboard" is a valid literal but we haven't registered it
        config = InsertionConfig(strategy="clipboard")

        with pytest.raises(ProviderNotFoundError) as exc:
            registry.get_insertion(config)
        assert "clipboard" in str(exc.value)

    def test_list_asr_empty(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        assert registry.list_asr() == []

    def test_list_asr(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        registry.register_asr("z_provider", MockASRProvider)
        registry.register_asr("a_provider", MockASRProvider)
        assert registry.list_asr() == ["a_provider", "z_provider"]

    def test_list_cleanup(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        registry.register_cleanup("b_cleanup", MockCleanupProvider)
        registry.register_cleanup("a_cleanup", MockCleanupProvider)
        assert registry.list_cleanup() == ["a_cleanup", "b_cleanup"]

    def test_list_insertion(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        registry.register_insertion("b_insert", MockInsertionStrategy)
        registry.register_insertion("a_insert", MockInsertionStrategy)
        assert registry.list_insertion() == ["a_insert", "b_insert"]

    def test_get_asr_passes_config(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        registry.register_asr("mock_asr", MockASRProvider)

        config = ASRConfig(provider="mock_asr", model="base.en")
        provider = registry.get_asr(config)

        assert provider.config.model == "base.en"

    def test_get_cleanup_passes_config(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        registry.register_cleanup("mock_cleanup", MockCleanupProvider)

        config = CleanupConfig(provider="mock_cleanup", style="technical")
        provider = registry.get_cleanup(config)

        assert provider.config.style == "technical"

    def test_get_insertion_passes_config(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        registry.register_insertion("keyboard", MockInsertionStrategy)

        config = InsertionConfig(strategy="keyboard", clipboard_fallback=False)
        strategy = registry.get_insertion(config)

        assert strategy.config.clipboard_fallback is False

    def test_multiple_providers_isolated(self) -> None:
        """Each registry namespace is independent."""
        registry = ProviderRegistry(register_builtins=False)
        registry.register_asr("asr_a", MockASRProvider)
        registry.register_cleanup("clean_a", MockCleanupProvider)
        registry.register_insertion("ins_a", MockInsertionStrategy)

        assert registry.list_asr() == ["asr_a"]
        assert registry.list_cleanup() == ["clean_a"]
        assert registry.list_insertion() == ["ins_a"]


# ── ABC Contract Tests ───────────────────────────────────────────────


class TestABCContracts:
    """Ensure ABCs cannot be instantiated without subclassing."""

    def test_cannot_instantiate_asr_provider_directly(self) -> None:
        with pytest.raises(TypeError):
            ASRProvider()  # type: ignore[abstract]

    def test_cannot_instantiate_cleanup_provider_directly(self) -> None:
        with pytest.raises(TypeError):
            CleanupProvider()  # type: ignore[abstract]

    def test_cannot_instantiate_insertion_strategy_directly(self) -> None:
        with pytest.raises(TypeError):
            InsertionStrategy()  # type: ignore[abstract]

    def test_mock_provider_satisfies_asr_contract(self) -> None:
        """Mocks with all abstract methods implemented can be instantiated."""
        provider = MockASRProvider(config=ASRConfig(provider="test"))
        assert provider.get_name() == "mock_asr"

    def test_mock_provider_satisfies_cleanup_contract(self) -> None:
        provider = MockCleanupProvider(config=CleanupConfig(provider="test"))
        assert provider.get_name() == "mock_cleanup"

    def test_mock_provider_satisfies_insertion_contract(self) -> None:
        """Use a valid literal strategy key that matches registration."""
        strategy = MockInsertionStrategy(config=InsertionConfig(strategy="keyboard"))
        assert strategy.get_name() == "mock_insert"


# ── v0.4.0 Observer OCR + compiler namespaces ──────────────────────
# The ABCs (``OCRProvider``, ``SessionCompiler``) are owned by Tracks
# 2 and 3 respectively, so we test the registry with stand-in classes
# that satisfy the *call shape* — they accept a config and return
# something. This is enough to exercise the registry's machinery;
# Track 2/3 own their own contract tests.

# These names are chosen so an accidental collision with future real
# built-ins is immediately visible.
_OCR_REG_NAME = "mock_observer_ocr"
_COMPILER_REG_NAME = "mock_observer_compiler"


class _MockOCR:
    """Stand-in for an ``OCRProvider`` that just records the config."""

    def __init__(self, config: ObserverOCRConfig) -> None:
        self.config = config

    def get_name(self) -> str:
        return _OCR_REG_NAME


class _MockCompiler:
    """Stand-in for a ``SessionCompiler`` that just records the config."""

    def __init__(self, config: ObserverCompileConfig) -> None:
        self.config = config

    def get_name(self) -> str:
        return _COMPILER_REG_NAME


class TestObserverRegistryNamespaces:
    def test_register_and_get_ocr(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        registry.register_ocr(_OCR_REG_NAME, _MockOCR)
        config = ObserverOCRConfig(provider=_OCR_REG_NAME)
        provider = registry.get_ocr(config)
        assert isinstance(provider, _MockOCR)
        assert provider.config is config

    def test_register_and_get_compiler(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        registry.register_compiler(_COMPILER_REG_NAME, _MockCompiler)
        config = ObserverCompileConfig(provider=_COMPILER_REG_NAME)
        compiler = registry.get_compiler(config)
        assert isinstance(compiler, _MockCompiler)
        assert compiler.config is config

    def test_get_ocr_unknown_raises(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        with pytest.raises(ProviderNotFoundError) as exc:
            registry.get_ocr(ObserverOCRConfig(provider="nonexistent_ocr"))
        assert "Unknown Observer OCR provider" in str(exc.value)
        # Available list is empty here so the suffix may be empty; just
        # assert the unknown name appears.
        assert "nonexistent_ocr" in str(exc.value)

    def test_get_compiler_unknown_raises(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        with pytest.raises(ProviderNotFoundError) as exc:
            registry.get_compiler(ObserverCompileConfig(provider="nonexistent_compiler"))
        assert "Unknown Observer compiler" in str(exc.value)
        assert "nonexistent_compiler" in str(exc.value)

    def test_list_ocr_empty(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        assert registry.list_ocr() == []

    def test_list_ocr(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        registry.register_ocr("b_ocr", _MockOCR)
        registry.register_ocr("a_ocr", _MockOCR)
        assert registry.list_ocr() == ["a_ocr", "b_ocr"]

    def test_list_compiler_empty(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        assert registry.list_compiler() == []

    def test_list_compiler(self) -> None:
        registry = ProviderRegistry(register_builtins=False)
        registry.register_compiler("b_compiler", _MockCompiler)
        registry.register_compiler("a_compiler", _MockCompiler)
        assert registry.list_compiler() == ["a_compiler", "b_compiler"]

    def test_namespaces_isolated_from_other_providers(self) -> None:
        """The OCR + compiler namespaces are independent of each other
        and of the existing ASR / cleanup / insertion / vision ones."""
        registry = ProviderRegistry(register_builtins=False)
        registry.register_asr("only_asr", MockASRProvider)
        registry.register_cleanup("only_cleanup", MockCleanupProvider)
        registry.register_insertion("only_insertion", MockInsertionStrategy)
        registry.register_vision("only_vision", _MockVision)
        registry.register_ocr(_OCR_REG_NAME, _MockOCR)
        registry.register_compiler(_COMPILER_REG_NAME, _MockCompiler)
        # All six namespaces independent.
        assert registry.list_asr() == ["only_asr"]
        assert registry.list_cleanup() == ["only_cleanup"]
        assert registry.list_insertion() == ["only_insertion"]
        assert registry.list_vision() == ["only_vision"]
        assert registry.list_ocr() == [_OCR_REG_NAME]
        assert registry.list_compiler() == [_COMPILER_REG_NAME]


class _MockVision(VisionProvider):
    def __init__(self, config):  # type: ignore[no-untyped-def]
        self.config = config

    def get_name(self) -> str:
        return "mock_vision"

    def is_available(self) -> bool:
        return True

    async def extract(self, image_data, instruction, context=None, mime_type="image/png"):  # type: ignore[no-untyped-def,override]
        return ""
