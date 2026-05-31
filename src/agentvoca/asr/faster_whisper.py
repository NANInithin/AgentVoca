"""Faster-Whisper ASR provider.

Inference is performed locally using the faster-whisper library (CTranslate2).
"""

import asyncio
import importlib.util
import io
import logging
import os
import sys
from typing import AsyncIterator, Optional

import numpy as np
from faster_whisper import WhisperModel

from agentvoca.asr.base import ASRProvider
from agentvoca.config.schema import ASRConfig
from agentvoca.core.types import ASRContext, TranscriptSegment
from agentvoca.utils.errors import ASRError

logger = logging.getLogger(__name__)


def _register_cuda_dlls() -> None:
    """Register pip-installed NVIDIA DLL directories with the Windows DLL loader.

    nvidia-cublas-cu12 and friends put cublas64_12.dll etc. under
    site-packages/nvidia/*/bin. Windows doesn't search there automatically, so
    ctranslate2 cannot find them. os.add_dll_directory() fixes this.
    """
    if sys.platform != "win32":
        return
    for pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_runtime", "nvidia.cufft"):
        try:
            spec = importlib.util.find_spec(pkg)
            if spec and spec.origin:
                bin_dir = os.path.join(os.path.dirname(spec.origin), "bin")
                if os.path.isdir(bin_dir):
                    os.add_dll_directory(bin_dir)
                    logger.debug("Registered CUDA DLL directory: %s", bin_dir)
        except Exception:
            pass


_register_cuda_dlls()


class FasterWhisperProvider(ASRProvider):
    """Local ASR provider using faster-whisper."""

    def __init__(self, config: ASRConfig) -> None:
        """Initialize the provider.

        Args:
            config: The ASR configuration block.
        """
        self._config = config
        self._model_size = config.model or "base"
        self._model: Optional[WhisperModel] = None
        # "auto" tries CUDA first and falls back to CPU automatically.
        self._device = config.extra.get("device", "auto")
        self._compute_type = config.extra.get("compute_type", "default")

    _SIZE_HINTS: dict[str, str] = {
        "tiny": "~75 MB",
        "base": "~145 MB",
        "small": "~460 MB",
        "medium": "~1.5 GB",
        "large": "~3 GB",
        "large-v2": "~3 GB",
        "large-v3": "~3 GB",
    }

    def _get_model(self) -> WhisperModel:
        """Lazy load the Whisper model, with automatic CPU fallback."""
        if self._model is not None:
            return self._model

        hint = self._SIZE_HINTS.get(self._model_size, "")
        hint_str = f" ({hint})" if hint else ""

        # Build the list of devices to try in order.
        # "auto" → try cuda first, then cpu.
        # Any explicit value → try only that device.
        if self._device == "auto":
            devices = [("cuda", "float16"), ("cpu", "int8")]
        else:
            compute = (
                self._compute_type
                if self._compute_type != "default"
                else ("float16" if self._device == "cuda" else "int8")
            )
            devices = [(self._device, compute)]

        import os

        cache_dir = os.path.join(
            os.path.expanduser("~"),
            ".cache",
            "huggingface",
            "hub",
            f"models--Systran--faster-whisper-{self._model_size}",
        )
        already_cached = os.path.isdir(cache_dir)
        loading_note = (
            "loading from cache…"
            if already_cached
            else (f"first run downloads {hint_str.strip('() ')} of model weights, please wait…")
        )

        last_error: Exception | None = None
        for device, compute_type in devices:
            logger.info(
                "Loading faster-whisper '%s' on %s (%s) — %s",
                self._model_size,
                device,
                compute_type,
                loading_note,
            )
            try:
                self._model = WhisperModel(
                    self._model_size, device=device, compute_type=compute_type
                )
                logger.info("Model '%s' ready on %s", self._model_size, device)
                return self._model
            except Exception as exc:
                last_error = exc
                err_lower = str(exc).lower()
                is_cuda_error = any(
                    kw in err_lower for kw in ("cuda", "cublas", "cudnn", "gpu", "cublaslt")
                )
                if is_cuda_error and device != "cpu":
                    logger.warning(
                        "GPU unavailable (%s) — falling back to CPU. "
                        "Install CUDA libraries or set asr.extra.device: cpu to silence this.",
                        exc,
                    )
                    continue
                # Non-CUDA error or already on CPU — do not retry
                break

        raise ASRError(f"Failed to load faster-whisper model '{self._model_size}': {last_error}")

    def get_name(self) -> str:
        """Return the registry key for this provider."""
        return "faster_whisper"

    def is_available(self) -> bool:
        """Return True if the model can be loaded."""
        try:
            # We don't want to load it just to check availability as it's slow,
            # but we should at least check if it *could* be loaded.
            # For now, always return True if configured.
            return True
        except Exception:
            return False

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> TranscriptSegment:
        """Transcribe a complete audio buffer."""
        if not audio_bytes:
            return TranscriptSegment(text="", is_final=True)

        model = self._get_model()

        # AudioCapture produces raw float32 PCM bytes. faster-whisper's
        # transcribe() accepts a numpy float32 array directly; passing a
        # BytesIO of headerless PCM would cause an ffmpeg decode error.
        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)

        try:
            # transcription is CPU/GPU intensive, run in thread executor
            loop = asyncio.get_running_loop()
            segments, info = await loop.run_in_executor(
                None,
                lambda: model.transcribe(
                    audio_array,
                    language=context.language_hint if context else self._config.language_hint,
                    beam_size=self._config.extra.get("beam_size", 5),
                    vad_filter=True,  # Use faster-whisper's built-in VAD if possible
                ),
            )

            full_text = "".join([s.text for s in segments]).strip()

            return TranscriptSegment(
                text=full_text,
                is_final=True,
                language_detected=info.language,
                confidence=info.language_probability,
            )
        except Exception as e:
            err_lower = str(e).lower()
            is_cuda_error = any(kw in err_lower for kw in ("cuda", "cublas", "cudnn", "cublaslt"))
            if is_cuda_error:
                # Model loaded on CUDA but inference libs are missing at runtime.
                # Reset so _get_model() reloads on CPU on the next attempt.
                logger.warning(
                    "CUDA inference failed (%s) — reloading model on CPU for next attempt. "
                    "Install nvidia-cublas-cu12 / nvidia-cudnn-cu12 for GPU acceleration.",
                    e,
                )
                self._model = None
                self._device = "cpu"
                self._compute_type = "int8"
            raise ASRError(f"Faster-Whisper transcription failed: {e}")

    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> AsyncIterator[TranscriptSegment]:
        """Buffer all audio and return a single final segment."""
        buffer = io.BytesIO()
        async for chunk in audio_stream:
            buffer.write(chunk)

        final_segment = await self.transcribe_audio(buffer.getvalue(), sample_rate, context)
        yield final_segment
