# Provider Guide

AgentVoca uses interface-based adapters for ASR, cleanup, and insertion. All providers are
registered by name in the `ProviderRegistry` and instantiated from config at startup.

---

## Built-in providers

### ASR

| Name | Class | Location |
|---|---|---|
| `faster_whisper` | `FasterWhisperProvider` | `src/agentvoca/asr/faster_whisper.py` |
| `openai_compatible` | `OpenAICompatibleASRProvider` | `src/agentvoca/asr/openai_compatible.py` |

### Cleanup

| Name | Class | Location |
|---|---|---|
| `rules` | `RulesCleanupProvider` | `src/agentvoca/cleanup/rules.py` |
| `openai_compatible` | `OpenAICompatibleCleanupProvider` | `src/agentvoca/cleanup/openai_compatible.py` |
| `none` | `NoneCleanupProvider` | `src/agentvoca/cleanup/none.py` |

### Insertion

| Name | Class | Location |
|---|---|---|
| `keyboard` | `KeyboardInsertionStrategy` | `src/agentvoca/insertion/keyboard.py` |
| `clipboard` | `ClipboardInsertionStrategy` | `src/agentvoca/insertion/clipboard.py` |

---

## General rules

- Do not change the abstract base class interfaces without an architecture review.
- Raise domain errors from `src/agentvoca/utils/errors.py` — never let raw exceptions
  propagate out of a provider method.
- Keep provider constructors compatible with the registry: the only required parameter is
  the matching config object (`ASRConfig`, `CleanupConfig`, or `InsertionConfig`).
- Do not add new package dependencies without explicit approval.

---

## Add an ASR provider

1. Create a file in `src/agentvoca/asr/`.
2. Subclass `ASRProvider` from `src/agentvoca/asr/base.py`.
3. Implement all four abstract methods.
4. Convert all provider-specific errors to `ASRError`.
5. Register the provider in `src/agentvoca/asr/__init__.py` by adding it to
   `BUILTIN_ASR_PROVIDERS`.

```python
# src/agentvoca/asr/my_provider.py
from src.agentvoca.asr.base import ASRProvider
from src.agentvoca.config.schema import ASRConfig
from src.agentvoca.core.types import ASRContext, TranscriptSegment
from src.agentvoca.utils.errors import ASRError


class MyASRProvider(ASRProvider):
    def __init__(self, config: ASRConfig) -> None:
        self._config = config

    def get_name(self) -> str:
        return "my_asr"

    def is_available(self) -> bool:
        # Return False if a required dependency or credential is missing.
        return True

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        context: ASRContext | None = None,
    ) -> TranscriptSegment:
        try:
            text = ...  # call your backend
            return TranscriptSegment(text=text, is_final=True)
        except Exception as exc:
            raise ASRError(f"Transcription failed: {exc}") from exc

    async def stream_transcribe(self, audio_stream, sample_rate, context=None):
        # Collect the stream and delegate to transcribe_audio if streaming
        # is not natively supported by the backend.
        import io
        buf = io.BytesIO()
        async for chunk in audio_stream:
            buf.write(chunk)
        yield await self.transcribe_audio(buf.getvalue(), sample_rate, context)
```

Then register it:

```python
# src/agentvoca/asr/__init__.py
from src.agentvoca.asr.my_provider import MyASRProvider

BUILTIN_ASR_PROVIDERS = {
    "faster_whisper": FasterWhisperProvider,
    "openai_compatible": OpenAICompatibleASRProvider,
    "my_asr": MyASRProvider,          # add this line
}
```

---

## Add a cleanup provider

1. Create a file in `src/agentvoca/cleanup/`.
2. Subclass `CleanupProvider` from `src/agentvoca/cleanup/base.py`.
3. Use `get_cleanup_prompt()` from `src/agentvoca/cleanup/prompts.py` for the system
   prompt if you are calling an LLM.
4. Never return an empty string for non-empty input — fall back to returning the raw
   transcript on error.
5. Convert all errors to `CleanupError`.
6. Register in `src/agentvoca/cleanup/__init__.py`.

```python
# src/agentvoca/cleanup/my_provider.py
from src.agentvoca.cleanup.base import CleanupProvider
from src.agentvoca.cleanup.prompts import get_cleanup_prompt
from src.agentvoca.config.schema import CleanupConfig
from src.agentvoca.core.types import CleanupContext
from src.agentvoca.utils.errors import CleanupError


class MyCleanupProvider(CleanupProvider):
    def __init__(self, config: CleanupConfig) -> None:
        self._config = config

    def get_name(self) -> str:
        return "my_cleanup"

    def is_available(self) -> bool:
        return True

    async def rewrite(
        self,
        transcript: str,
        context: CleanupContext | None = None,
    ) -> str:
        style = context.style if context else "standard"
        preserve_code = context.preserve_code if context else True
        prompt = get_cleanup_prompt(style=style, preserve_code=preserve_code)
        try:
            result = ...  # call your backend with `prompt` and `transcript`
            return result or transcript
        except Exception as exc:
            raise CleanupError(f"Cleanup failed: {exc}") from exc
```

---

## Add an insertion strategy

1. Create a file in `src/agentvoca/insertion/`.
2. Subclass `InsertionStrategy` from `src/agentvoca/insertion/base.py`.
3. Return `InsertionResult(success=False, ...)` instead of raising — the orchestrator
   handles fallback logic based on the return value.
4. Implement `undo_last()` to send Ctrl+Z / Cmd+Z where possible.
5. Register in `src/agentvoca/insertion/__init__.py`.

```python
# src/agentvoca/insertion/my_strategy.py
from src.agentvoca.config.schema import InsertionConfig
from src.agentvoca.core.types import InsertionResult
from src.agentvoca.insertion.base import InsertionStrategy


class MyInsertionStrategy(InsertionStrategy):
    def __init__(self, config: InsertionConfig) -> None:
        self._config = config

    def get_name(self) -> str:
        return "my_strategy"

    def is_available(self) -> bool:
        return True

    async def insert(self, text: str) -> InsertionResult:
        try:
            ...  # perform insertion
            return InsertionResult(success=True, method_used="my_strategy")
        except Exception as exc:
            return InsertionResult(
                success=False, method_used="my_strategy", error=str(exc)
            )

    async def undo_last(self) -> bool:
        return False  # implement if undo is supported
```

---

## Testing providers

- Add a `tests/unit/test_<provider_name>.py` file.
- Mock all network calls and OS APIs — no real API requests in CI.
- Cover: happy path, error path (raises domain error), `is_available()` returning False.
- For insertion strategies, mock `pyautogui` and `pyperclip`.

```python
from unittest.mock import patch
from src.agentvoca.config.schema import ASRConfig
from src.agentvoca.utils.errors import ASRError

async def test_transcription_success():
    config = ASRConfig(provider="my_asr")
    provider = MyASRProvider(config)
    with patch.object(provider, "_call_backend", return_value="hello world"):
        result = await provider.transcribe_audio(b"audio", 16000)
    assert result.text == "hello world"
    assert result.is_final is True

async def test_transcription_wraps_exception():
    config = ASRConfig(provider="my_asr")
    provider = MyASRProvider(config)
    with patch.object(provider, "_call_backend", side_effect=RuntimeError("boom")):
        with pytest.raises(ASRError):
            await provider.transcribe_audio(b"audio", 16000)
```
