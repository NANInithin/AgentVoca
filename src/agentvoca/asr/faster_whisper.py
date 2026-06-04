"""Faster-Whisper ASR provider.

Inference is performed locally using the faster-whisper library (CTranslate2).
Supports both batch (v1) and streaming (v2) modes.
"""

import asyncio
import io
import logging
import os
import sys
import time
from typing import AsyncIterator, Optional

import ctranslate2
import numpy as np
from faster_whisper import WhisperModel

from agentvoca.asr.base import ASRProvider
from agentvoca.config.schema import ASRConfig
from agentvoca.core.types import ASRContext, TranscriptSegment
from agentvoca.utils.errors import ASRError

logger = logging.getLogger(__name__)


def _register_cuda_dlls() -> None:
    """Register pip-installed NVIDIA DLL directories with the Windows DLL loader.

    nvidia-cublas-cu12 and friends install cublas64_12.dll etc. under
    site-packages/nvidia/*/bin.  Windows does not search there automatically
    so ctranslate2 cannot find them at inference time.

    The original approach used importlib.util.find_spec which silently returns
    a spec with origin=None for namespace packages (nvidia.*), so no directory
    was ever registered.  This version walks site-packages directly.
    """
    if sys.platform != "win32":
        return
    import site

    search_roots: list[str] = []
    try:
        search_roots.extend(site.getsitepackages())
    except AttributeError:
        pass
    user_site = site.getusersitepackages()
    if user_site and user_site not in search_roots:
        search_roots.append(user_site)

    for root in search_roots:
        nvidia_dir = os.path.join(root, "nvidia")
        if not os.path.isdir(nvidia_dir):
            continue
        try:
            for name in os.listdir(nvidia_dir):
                bin_dir = os.path.join(nvidia_dir, name, "bin")
                if os.path.isdir(bin_dir):
                    try:
                        os.add_dll_directory(bin_dir)
                        logger.debug("Registered CUDA DLL directory: %s", bin_dir)
                    except Exception:
                        pass
        except Exception:
            pass


_register_cuda_dlls()

# Preference order for compute types, best (fastest/most accurate trade-off)
# first. Probed against what the installed CTranslate2 + hardware actually
# support so we never request a type that fails to load.
_CUDA_COMPUTE_PREFS = ["float16", "int8_float16", "bfloat16", "int8", "float32"]
_CPU_COMPUTE_PREFS = ["int8", "int8_float32", "float32"]


def _probe_compute_type(device: str) -> str:
    """Return the best CTranslate2 compute type supported on ``device``.

    Queries ``ctranslate2.get_supported_compute_types`` and picks the first
    entry from the device's preference list that is actually supported. Falls
    back to the historical hard-coded default (``float16`` on CUDA, ``int8`` on
    CPU) if the probe is unavailable or raises.
    """
    prefs = _CUDA_COMPUTE_PREFS if device == "cuda" else _CPU_COMPUTE_PREFS
    fallback = "float16" if device == "cuda" else "int8"
    try:
        supported = set(ctranslate2.get_supported_compute_types(device))
    except Exception:
        return fallback
    for compute in prefs:
        if compute in supported:
            return compute
    return fallback


class FasterWhisperProvider(ASRProvider):
    """Local ASR provider using faster-whisper.

    Supports v1 batch transcription via ``transcribe_audio`` and v2 streaming
    via ``stream_transcribe`` with rolling-window partials.
    """

    def __init__(self, config: ASRConfig) -> None:
        """Initialize the provider.

        Args:
            config: The ASR configuration block.
        """
        self._config = config
        self._model_size = config.model or "base"
        self._model: Optional[WhisperModel] = None
        self._streaming_model: Optional[WhisperModel] = None
        # "auto" tries CUDA first and falls back to CPU automatically.
        self._device = config.extra.get("device", "auto")
        self._compute_type = config.extra.get("compute_type", "default")
        self._warmed_up = False

    _SIZE_HINTS: dict[str, str] = {
        "tiny": "~75 MB",
        "base": "~145 MB",
        "small": "~460 MB",
        "medium": "~1.5 GB",
        "large": "~3 GB",
        "large-v2": "~3 GB",
        "large-v3": "~3 GB",
    }

    # ── v2 additions ──────────────────────────────────────────────────

    def supports_streaming(self) -> bool:
        """Return True when streaming is enabled in config."""
        return self._config.streaming

    async def warm_up(self) -> None:
        """Preload both accurate and streaming models at startup.

        Also runs a tiny inference probe so that CUDA kernel initialisation
        (cublas, cudnn) happens now, not during the user's first dictation.
        If the probe times out or raises a CUDA error the provider resets to
        CPU immediately, making every subsequent operation fast and reliable.
        """
        if self._warmed_up:
            return
        logger.info("Warming up FasterWhisperProvider…")
        t0 = time.perf_counter()

        model = self._get_model()

        # Inference probe — 300 ms of silence is enough to trigger cublas.
        loop = asyncio.get_running_loop()
        dummy = np.zeros(int(0.3 * 16000), dtype=np.float32)
        try:
            await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: list(model.transcribe(dummy, beam_size=1, vad_filter=False)[0]),
                ),
                timeout=15.0,
            )
            logger.debug("CUDA inference probe succeeded")
        except asyncio.TimeoutError:
            logger.warning(
                "CUDA inference probe timed out — switching to CPU. "
                "Install CUDA toolkit or set asr.extra.device: cpu to suppress this."
            )
            self._model = None
            self._device = "cpu"
            self._compute_type = "int8"
            self._streaming_model = None
            _ = self._get_model()
        except Exception as exc:
            err = str(exc).lower()
            if any(kw in err for kw in ("cuda", "cublas", "cudnn", "cublaslt")):
                logger.warning("CUDA inference probe failed (%s) — switching to CPU.", exc)
                self._model = None
                self._device = "cpu"
                self._compute_type = "int8"
                self._streaming_model = None
                _ = self._get_model()
            else:
                logger.debug("Inference probe non-CUDA error (ignored): %s", exc)

        # Preload the streaming model (uses whichever device survived the probe)
        if self._config.streaming:
            _ = self._get_streaming_model()

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        self._warmed_up = True
        logger.info("FasterWhisperProvider warm-up complete in %d ms", elapsed_ms)

    # ── Model loading ─────────────────────────────────────────────────

    def _get_model(self) -> WhisperModel:
        """Lazy load the accurate Whisper model, with automatic CPU fallback."""
        if self._model is not None:
            return self._model

        hint = self._SIZE_HINTS.get(self._model_size, "")
        hint_str = f" ({hint})" if hint else ""

        # When compute_type is "default", probe what the installed CTranslate2
        # build + hardware actually support and pick the best, instead of
        # hard-coding float16/int8.
        if self._device == "auto":
            devices = [
                ("cuda", _probe_compute_type("cuda")),
                ("cpu", _probe_compute_type("cpu")),
            ]
        else:
            compute = (
                self._compute_type
                if self._compute_type != "default"
                else _probe_compute_type(self._device)
            )
            devices = [(self._device, compute)]

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
                break

        raise ASRError(f"Failed to load faster-whisper model '{self._model_size}': {last_error}")

    def _get_streaming_model(self) -> WhisperModel:
        """Lazy load the streaming (small/fast) Whisper model."""
        if self._streaming_model is not None:
            return self._streaming_model

        streaming_size = self._config.streaming_model or "base.en"
        device = "cpu" if self._device == "cpu" else ("cuda" if self._device != "auto" else "cuda")

        logger.info("Loading streaming model '%s' on %s", streaming_size, device)
        try:
            self._streaming_model = WhisperModel(
                streaming_size,
                device=device,
                compute_type="float16" if device == "cuda" else "int8",
            )
            logger.info("Streaming model '%s' ready", streaming_size)
        except Exception as exc:
            # Fall back to CPU for streaming if CUDA fails
            logger.warning("Streaming model on %s failed (%s); falling back to CPU", device, exc)
            self._streaming_model = WhisperModel(
                streaming_size,
                device="cpu",
                compute_type="int8",
            )
            logger.info("Streaming model '%s' ready on CPU (fallback)", streaming_size)

        return self._streaming_model

    # ── v1 interface ──────────────────────────────────────────────────

    def get_name(self) -> str:
        """Return the registry key for this provider."""
        return "faster_whisper"

    def is_available(self) -> bool:
        """Return True if the model can be loaded."""
        return True

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> TranscriptSegment:
        """Transcribe a complete audio buffer (v1 batch path)."""
        if not audio_bytes:
            return TranscriptSegment(text="", is_final=True)

        model = self._get_model()

        audio_array = np.frombuffer(audio_bytes, dtype=np.float32)

        try:
            loop = asyncio.get_running_loop()
            segments, info = await loop.run_in_executor(
                None,
                lambda: model.transcribe(
                    audio_array,
                    language=context.language_hint if context else self._config.language_hint,
                    beam_size=self._config.extra.get("beam_size", 5),
                    vad_filter=True,
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
                logger.warning(
                    "CUDA inference failed (%s) — reloading model on CPU for next attempt. "
                    "Install nvidia-cublas-cu12 / nvidia-cudnn-cu12 for GPU acceleration.",
                    e,
                )
                self._model = None
                self._device = "cpu"
                self._compute_type = "int8"
            raise ASRError(f"Faster-Whisper transcription failed: {e}")

    # ── v2 streaming ──────────────────────────────────────────────────

    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        sample_rate: int,
        context: Optional[ASRContext] = None,
    ) -> AsyncIterator[TranscriptSegment]:
        """Yield rolling partials then one accurate final segment.

        Streaming strategy (pseudo-streaming for faster-whisper which has
        no native streaming API):
        - Buffer all audio as it arrives.
        - Every chunk, run a fast pass with the small streaming model on
          the rolling window and yield a partial (``is_final=False``).
        - When the stream ends, run one accurate pass with the configured
          model on the full audio and yield a final (``is_final=True``).

        If streaming is disabled in config, falls back to the v1 behavior:
        buffer all and yield one final segment.
        """
        if not self._config.streaming:
            # v1 fallback: buffer and yield one final segment
            buffer = io.BytesIO()
            async for chunk in audio_stream:
                buffer.write(chunk)
            final_segment = await self.transcribe_audio(buffer.getvalue(), sample_rate, context)
            yield final_segment
            return

        # v2 streaming path. The chunk cadence is driven upstream by the
        # AudioChunker; here we only consume chunks and re-transcribe the window.
        full_buffer = bytearray()
        window_s = self._config.streaming_window_s

        streaming_model = self._get_streaming_model()

        loop = asyncio.get_running_loop()
        partial_index = 0

        # Fire-and-forget partial transcription.
        # Using a blocking `await run_in_executor` inside `async for` caused a
        # queue backlog on slow hardware: each CPU transcription (1-3 s) blocked
        # queue reads while chunks arrived every 500 ms, so 10+ jobs piled up
        # after recording stopped.  Instead we submit the job, keep reading
        # chunks eagerly, and only start a new partial when the previous one
        # finishes.  Partials are throwaway previews; skipping frames is fine.
        _partial_fut: asyncio.Future | None = None

        async for chunk in audio_stream:
            full_buffer.extend(chunk)

            min_partial_bytes = int(0.5 * sample_rate) * 4  # 500 ms minimum
            if len(full_buffer) < min_partial_bytes:
                continue

            # Build the rolling window
            audio_array = np.frombuffer(bytes(full_buffer), dtype=np.float32)
            if window_s > 0:
                window_samples = window_s * sample_rate
                if len(audio_array) > window_samples:
                    audio_array = audio_array[-window_samples:]

            # Yield any completed partial result (non-blocking check)
            if _partial_fut is not None and _partial_fut.done():
                try:
                    segs, _ = _partial_fut.result()
                    partial_text = "".join([s.text for s in segs]).strip()
                    if partial_text:
                        partial_index += 1
                        yield TranscriptSegment(
                            text=partial_text,
                            is_final=False,
                            language_detected=None,
                        )
                except Exception:
                    pass
                _partial_fut = None

            # Start a new partial only when no other is running
            if _partial_fut is None:
                snapshot = audio_array.copy()
                lang = context.language_hint if context else self._config.language_hint
                _partial_fut = loop.run_in_executor(
                    None,
                    lambda a=snapshot, lg=lang: streaming_model.transcribe(
                        a, language=lg, beam_size=1, vad_filter=False
                    ),
                )
            # If _partial_fut is still running, skip this chunk — no backlog.

        # Stream ended: yield any still-pending partial, then do the final pass.
        if _partial_fut is not None and not _partial_fut.done():
            try:
                segs, _ = await asyncio.wait_for(_partial_fut, timeout=15.0)
                partial_text = "".join([s.text for s in segs]).strip()
                if partial_text:
                    yield TranscriptSegment(
                        text=partial_text, is_final=False, language_detected=None
                    )
            except Exception:
                pass
        elif _partial_fut is not None and _partial_fut.done():
            try:
                segs, _ = _partial_fut.result()
                partial_text = "".join([s.text for s in segs]).strip()
                if partial_text:
                    yield TranscriptSegment(
                        text=partial_text, is_final=False, language_detected=None
                    )
            except Exception:
                pass

        # Stream ended — run accurate pass on full audio.
        # Mirror the retry/reset logic from transcribe_audio: if the CUDA
        # model fails at inference, reset to CPU and retry once so the caller
        # gets a result instead of a hang or an unhandled error.
        if full_buffer:
            audio_array = np.frombuffer(bytes(full_buffer), dtype=np.float32)
            # Generous timeout: 4× real-time for CPU int8, minimum 30 s.
            # Prevents an indefinite hang when CUDA inference deadlocks.
            audio_duration_s = len(audio_array) / sample_rate
            inference_timeout = max(30.0, audio_duration_s * 4)

            for _attempt in range(2):
                try:
                    accurate_model = self._get_model()  # re-fetch in case reset
                    segments, info = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda a=audio_array: accurate_model.transcribe(
                                a,
                                language=(
                                    context.language_hint if context else self._config.language_hint
                                ),
                                beam_size=self._config.extra.get("beam_size", 5),
                                vad_filter=True,
                            ),
                        ),
                        timeout=inference_timeout,
                    )
                    full_text = "".join([s.text for s in segments]).strip()
                    yield TranscriptSegment(
                        text=full_text,
                        is_final=True,
                        language_detected=info.language,
                        confidence=info.language_probability,
                    )
                    break  # success
                except asyncio.TimeoutError:
                    if _attempt == 0:
                        logger.warning("Streaming final pass timed out — reloading model on CPU.")
                        self._model = None
                        self._device = "cpu"
                        self._compute_type = "int8"
                        continue
                    raise ASRError("Faster-Whisper final transcription timed out.")
                except Exception as e:
                    err_lower = str(e).lower()
                    is_cuda = any(kw in err_lower for kw in ("cuda", "cublas", "cudnn", "cublaslt"))
                    if is_cuda and _attempt == 0:
                        logger.warning(
                            "Streaming final pass: CUDA inference failed (%s) "
                            "— reloading model on CPU.",
                            e,
                        )
                        self._model = None
                        self._device = "cpu"
                        self._compute_type = "int8"
                        continue
                    raise ASRError(f"Faster-Whisper final transcription failed: {e}")
        else:
            yield TranscriptSegment(text="", is_final=True)
