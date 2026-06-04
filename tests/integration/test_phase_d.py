import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agentvoca.config.schema import FullConfig
from agentvoca.core.event_bus import EventBus
from agentvoca.core.events import (
    CommandRecognizedEvent,
    CorrectionLearnedEvent,
    RecordingStoppedEvent,
)
from agentvoca.core.orchestrator import Orchestrator
from agentvoca.core.registry import ProviderRegistry


@pytest.fixture
def mock_config(tmp_path):
    # Load a minimal valid config and enable Phase D.
    # learned_vocab_path is pinned to a tmp file so the test never reads or
    # writes the real ~/.agentvoca/learned_vocab.txt (test isolation).
    config_dict = {
        "asr": {"provider": "faster-whisper", "model": "tiny"},
        "commands": {"enabled": True},
        "adaptive": {
            "enabled": True,
            "promote_threshold": 2,
            "learned_vocab_path": str(tmp_path / "learned_vocab.txt"),
        },
    }
    return FullConfig.model_validate(config_dict)


@pytest.mark.asyncio
async def test_voice_command_newline(mock_config):
    event_bus = EventBus()
    registry = ProviderRegistry()

    # Mock providers
    asr = MagicMock()
    asr.get_name.return_value = "mock-asr"
    asr.is_available.return_value = True
    asr.supports_streaming.return_value = False
    # Mock transcribe_audio to return "new line"
    segment = MagicMock()
    segment.text = "new line"
    asr.transcribe_audio = AsyncMock(return_value=segment)

    insertion = MagicMock()
    insertion.get_name.return_value = "mock-insertion"
    insertion.insert = AsyncMock(return_value=MagicMock(success=True))

    registry.get_asr = MagicMock(return_value=asr)
    registry.get_insertion = MagicMock(return_value=insertion)
    registry.get_cleanup = MagicMock(
        return_value=MagicMock(is_available=lambda: True, get_name=lambda: "mock-cleanup")
    )

    orchestrator = Orchestrator(mock_config, registry, event_bus)
    await orchestrator.start()

    # Track events
    command_events = []
    event_bus.subscribe(CommandRecognizedEvent, lambda e: command_events.append(e))

    # Simulate recording stop
    event = RecordingStoppedEvent(audio_bytes=b"fake", duration_ms=1000, sample_rate=16000)
    event_bus.publish(event)

    # Wait for pipeline
    await asyncio.sleep(0.5)

    assert len(command_events) == 1
    assert command_events[0].action == "newline"
    # Verify "\n" was inserted instead of "new line"
    insertion.insert.assert_called_with("\n")


@pytest.mark.asyncio
async def test_adaptive_vocabulary_learning(mock_config):
    event_bus = EventBus()
    registry = ProviderRegistry()

    # Mock providers
    asr = MagicMock()
    asr.get_name.return_value = "mock-asr"
    asr.is_available.return_value = True
    asr.supports_streaming.return_value = False

    insertion = MagicMock()
    insertion.get_name.return_value = "mock-insertion"
    insertion.insert = AsyncMock(return_value=MagicMock(success=True))
    insertion.undo_last = AsyncMock(return_value=True)

    registry.get_asr = MagicMock(return_value=asr)
    registry.get_insertion = MagicMock(return_value=insertion)
    registry.get_cleanup = MagicMock(
        return_value=MagicMock(
            is_available=lambda: True, rewrite=AsyncMock(side_effect=lambda t, context: t)
        )
    )

    orchestrator = Orchestrator(mock_config, registry, event_bus)
    await orchestrator.start()

    # Track events
    correction_events = []
    event_bus.subscribe(CorrectionLearnedEvent, lambda e: correction_events.append(e))

    # 1. First dictation: "nini"
    asr.transcribe_audio = AsyncMock(return_value=MagicMock(text="nini"))
    event_bus.publish(
        RecordingStoppedEvent(audio_bytes=b"fake", duration_ms=1000, sample_rate=16000)
    )
    await asyncio.sleep(0.1)

    # 2. User undos
    await orchestrator.undo_last_insertion()

    # 3. Second dictation (correction): "NANI"
    asr.transcribe_audio = AsyncMock(return_value=MagicMock(text="NANI"))
    event_bus.publish(
        RecordingStoppedEvent(audio_bytes=b"fake", duration_ms=1000, sample_rate=16000)
    )
    await asyncio.sleep(0.1)

    # Should have learned one correction, but not promoted yet (threshold=2)
    assert len(correction_events) == 1
    assert correction_events[0].wrong == "nini"
    assert correction_events[0].right == "NANI"
    assert not correction_events[0].promoted

    # 4. Repeat correction: must have another "wrong" occurrence first
    asr.transcribe_audio = AsyncMock(return_value=MagicMock(text="nini"))
    event_bus.publish(
        RecordingStoppedEvent(audio_bytes=b"fake", duration_ms=1000, sample_rate=16000)
    )
    await asyncio.sleep(0.1)

    await orchestrator.undo_last_insertion()
    asr.transcribe_audio = AsyncMock(return_value=MagicMock(text="NANI"))
    event_bus.publish(
        RecordingStoppedEvent(audio_bytes=b"fake", duration_ms=1000, sample_rate=16000)
    )
    await asyncio.sleep(0.1)

    assert len(correction_events) == 2
    assert correction_events[1].wrong == "nini"
    assert correction_events[1].right == "NANI"
    assert correction_events[1].promoted

    # 5. Verify it's now in vocab
    asr.transcribe_audio = AsyncMock(return_value=MagicMock(text="Hello nini"))
    event_bus.publish(
        RecordingStoppedEvent(audio_bytes=b"fake", duration_ms=1000, sample_rate=16000)
    )
    await asyncio.sleep(0.1)

    # "nini" should be replaced by "NANI" because it's a vocab term now
    insertion.insert.assert_called_with("Hello NANI")
