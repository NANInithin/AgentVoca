"""Shared pytest fixtures for the agentvoca test suite."""

from __future__ import annotations

import pytest

from agentvoca.config.schema import ASRConfig, CleanupConfig, FullConfig, InsertionConfig
from agentvoca.core.event_bus import EventBus
from agentvoca.core.registry import ProviderRegistry


@pytest.fixture
def event_bus() -> EventBus:
    """Return a fresh EventBus for each test."""
    return EventBus()


@pytest.fixture
def minimal_config() -> FullConfig:
    """Return a minimal valid FullConfig suitable for unit tests."""
    return FullConfig(
        asr=ASRConfig(provider="faster_whisper", model="base"),
        cleanup=CleanupConfig(provider="rules"),
        insertion=InsertionConfig(strategy="keyboard"),
    )


@pytest.fixture
def registry() -> ProviderRegistry:
    """Return a ProviderRegistry with all built-in providers registered."""
    from agentvoca.asr import BUILTIN_ASR_PROVIDERS
    from agentvoca.cleanup import BUILTIN_CLEANUP_PROVIDERS
    from agentvoca.insertion import BUILTIN_INSERTION_STRATEGIES

    reg = ProviderRegistry()
    for name, cls in BUILTIN_ASR_PROVIDERS.items():
        reg.register_asr(name, cls)
    for name, cls in BUILTIN_CLEANUP_PROVIDERS.items():
        reg.register_cleanup(name, cls)
    for name, cls in BUILTIN_INSERTION_STRATEGIES.items():
        reg.register_insertion(name, cls)
    return reg
