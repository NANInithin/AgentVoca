"""Unit tests for the provider registry and abstract base classes.

Tests cover:
- Registration and lookup for all three provider types.
- ``ProviderNotFoundError`` for unknown providers.
- Listing registered names.
- ABC contract enforcement (cannot instantiate ABCs directly).
"""

from typing import Optional

import pytest

from agentvoca.asr.base import ASRProvider
from agentvoca.cleanup.base import CleanupProvider
from agentvoca.config.schema import ASRConfig, CleanupConfig, InsertionConfig
from agentvoca.core.registry import ProviderRegistry
from agentvoca.core.types import (
    ASRContext,
    CleanupContext,
    InsertionResult,
    TranscriptSegment,
)
from agentvoca.insertion.base import InsertionStrategy
from agentvoca.utils.errors import ProviderNotFoundError

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
