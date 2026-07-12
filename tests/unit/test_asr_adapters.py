"""Unit tests for ASR adapters."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agentvoca.asr.faster_whisper import FasterWhisperProvider
from agentvoca.asr.openai_compatible import OpenAICompatibleASRProvider
from agentvoca.config.schema import ASRConfig
from agentvoca.utils.errors import ASRError


@pytest.fixture
def fw_config():
    return ASRConfig(provider="faster_whisper", model="tiny")


@pytest.fixture
def openai_config():
    return ASRConfig(
        provider="openai_compatible",
        endpoint="https://api.openai.com/v1",
        model="whisper-1",
        api_key_env="OPENAI_API_KEY",
    )


@pytest.mark.asyncio
async def test_faster_whisper_transcribe(fw_config):
    """Test FasterWhisperProvider transcription with a mock model."""
    provider = FasterWhisperProvider(fw_config)

    mock_model = MagicMock()
    # Mocking segments and info returned by faster-whisper
    mock_segment = MagicMock()
    mock_segment.text = "Hello world"
    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.language_probability = 0.99

    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    # Must be a multiple of 4 bytes (float32) — "audio data" is 9 bytes which fails
    audio_bytes = b"\x00" * 16000 * 4  # 1 second of silent float32 audio at 16 kHz

    with patch("agentvoca.asr.faster_whisper.WhisperModel", return_value=mock_model):
        result = await provider.transcribe_audio(audio_bytes, 16000)

        assert result.text == "Hello world"
        assert result.is_final is True
        assert result.language_detected == "en"
        assert result.confidence == 0.99
        mock_model.transcribe.assert_called_once()


# One second of silent float32 PCM at 16 kHz — the exact shape the audio
# pipeline hands the provider (what faster-whisper reads via np.frombuffer).
_PCM_F32 = b"\x00" * 16000 * 4


@pytest.mark.asyncio
async def test_openai_asr_transcribe(openai_config, monkeypatch):
    """Test OpenAICompatibleASRProvider transcription with mock httpx."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAICompatibleASRProvider(openai_config)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"text": "Hello from API", "language": "en"}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await provider.transcribe_audio(_PCM_F32, 16000)

        assert result.text == "Hello from API"
        assert result.is_final is True
        assert result.language_detected == "en"
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_openai_asr_uploads_a_real_wav_file(openai_config, monkeypatch):
    """Regression: raw PCM must be wrapped in a valid WAV before upload.

    Previously the headerless float32 PCM was uploaded labelled ``audio.wav``,
    which every Whisper-compatible endpoint rejects with 400. The uploaded
    bytes must now start with the RIFF/WAVE magic.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAICompatibleASRProvider(openai_config)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"text": "ok"}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        await provider.transcribe_audio(_PCM_F32, 16000)

    files = mock_post.call_args.kwargs["files"]
    _name, uploaded_bytes, _mime = files["file"]
    assert uploaded_bytes[:4] == b"RIFF", "upload is not a WAV container"
    assert uploaded_bytes[8:12] == b"WAVE", "upload is missing the WAVE tag"


@pytest.mark.asyncio
async def test_openai_asr_failure(openai_config, monkeypatch):
    """Test OpenAICompatibleASRProvider error handling."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAICompatibleASRProvider(openai_config)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPError("API Error")

        with pytest.raises(ASRError) as exc:
            await provider.transcribe_audio(_PCM_F32, 16000)
        assert "OpenAI-compatible ASR request failed" in str(exc.value)


@pytest.mark.asyncio
async def test_openai_asr_surfaces_provider_error_body(openai_config, monkeypatch):
    """A 4xx must include the provider's response body for diagnosis."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    provider = OpenAICompatibleASRProvider(openai_config)

    error_response = MagicMock()
    error_response.status_code = 400
    error_response.text = '{"error": "audio file could not be decoded"}'

    def _raise():
        raise httpx.HTTPStatusError("400", request=MagicMock(), response=error_response)

    error_response.raise_for_status = _raise

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = error_response

        with pytest.raises(ASRError) as exc:
            await provider.transcribe_audio(_PCM_F32, 16000)
        msg = str(exc.value)
        assert "400" in msg
        assert "could not be decoded" in msg


@pytest.mark.asyncio
async def test_faster_whisper_stream_fallback(fw_config):
    """Test FasterWhisperProvider's buffering stream implementation."""
    provider = FasterWhisperProvider(fw_config)

    async def mock_audio_stream():
        # Chunks must be multiples of 4 bytes (float32 element size)
        yield b"\x00" * 8000 * 4
        yield b"\x00" * 8000 * 4

    mock_model = MagicMock()
    mock_segment = MagicMock()
    mock_segment.text = "chunk1 chunk2"
    mock_info = MagicMock()
    mock_info.language = "en"
    mock_model.transcribe.return_value = ([mock_segment], mock_info)

    with patch("agentvoca.asr.faster_whisper.WhisperModel", return_value=mock_model):
        segments = []
        async for s in provider.stream_transcribe(mock_audio_stream(), 16000):
            segments.append(s)

        assert len(segments) == 1
        assert segments[0].text == "chunk1 chunk2"
        assert segments[0].is_final is True
