# AgentVoca Release Notes

## v0.3.6 — Performance, Stability, and I/O Reliability Pass

**Released:** 2026-07-12  
**Version:** 0.3.6

### 🎯 Overview

AgentVoca v0.3.6 is a focused **performance, stability, and I/O reliability** release. It does not introduce a new user-facing feature or change the config schema. Instead, it removes hot-path bottlenecks that were most visible during longer dictations, cloud-provider use, and multi-screenshot vision workflows.

> **No new features. No config-schema changes. No new runtime dependencies.**  
> v0.3.6 optimizes the existing v2 streaming and v3 vision paths so AgentVoca feels smoother, more responsive, and more reliable during real usage.

### ✨ New Features & Improvements

#### Audio Capture and Streaming Performance
- **Dedicated VAD worker thread:** Silero VAD inference now runs off the sounddevice callback, keeping the audio callback near-zero work.
- **Single VAD inference per block:** Removed duplicate VAD inference in the audio callback path.
- **Auto-stop finalization moved off the callback:** Buffer joining and event publishing now run on the asyncio loop thread instead of the real-time audio thread.
- **O(N²) streaming ASR copy fixed:** Streaming transcription now snapshots only the rolling window with a memoryview-based single copy instead of copying the full recording every 500 ms.
- **Chunker buffer compaction:** `AudioChunker` now compacts emitted audio so the buffer footprint stays bounded by recent audio, not the full recording.
- **Dead frame queue removed:** Removed unused `_frame_queue` / `_frame_task` state from `AudioCapture`.

#### Cancel and Pipeline Reliability
- **Cancel hotkey now aborts the in-flight pipeline:** `Orchestrator.cancel()` now cancels the streaming task and tracked pipeline task, preventing ghost partials and cancel-after-stop insertion.
- **Streaming state reset hardening:** Streaming state is reset more reliably after pipeline completion, cancellation, or next-recording preparation.
- **Better hot-reload routing:** Config hot-apply is routed through the loop thread to avoid mutating async-owned state from the Qt thread.

#### Cloud Provider and Vision I/O Improvements
- **Persistent HTTP clients:** Cleanup and vision providers now reuse `httpx.AsyncClient` instances with explicit keepalive behavior.
- **Provider lifecycle shutdown:** Provider `shutdown()` methods are now used for cleanup and vision clients, including hot-reload replacement.
- **Warm-up actually warms the shared client:** `warm_up()` now runs through the persistent provider client.
- **Parallel multi-screenshot vision extraction:** Multi-screenshot vision extraction now uses `asyncio.gather`, preserving order while avoiding serial VLM round trips.
- **Per-shot error isolation:** Vision extraction failures no longer prevent the rest of the batch from being processed.

#### Text, Vocabulary, and Startup Improvements
- **Serialized OS input injection:** Keyboard and clipboard insertion now share a single worker executor so pyautogui/pyperclip operations cannot interleave during insert/undo races.
- **O(1) vocabulary casing lookup:** Vocabulary substitution now maintains a lowercase casing lookup alongside the compiled regex pattern.
- **Bulk adaptive vocabulary merges:** Learned mappings are promoted in bulk, reducing full regex rebuilds from one per mapping to one per merge.
- **Custom cleanup prompt cache:** `custom_prompt_path` is now cached by mtime, removing synchronous file reads from every cleanup rewrite.
- **Lazy provider imports:** Built-in providers are registered as dotted paths and imported only when needed, avoiding cold-start imports such as `ctranslate2` for cloud-provider users.
- **Input executor shutdown:** The single OS-input executor is shut down during app exit to avoid non-daemon thread exit delays.

### 🔧 Technical Details

#### Audio Hot Path
1. **Callback path:** The sounddevice callback now appends audio, feeds the chunker, and either enqueues VAD work or reads a cached VAD boolean.
2. **VAD worker:** A dedicated daemon thread runs silero inference and publishes speech/silence transitions.
3. **Auto-stop:** `stop_recording()` now schedules buffer finalization on the asyncio loop instead of performing the full join inside the audio callback.
4. **Streaming ASR:** `_window_snapshot()` copies only the active rolling window using a memoryview slice, avoiding repeated full-buffer copies.
5. **Chunker:** `_get_delta()` returns new audio and compacts the internal buffer after each emission.

#### Provider I/O and Vision
- Cleanup and vision providers now keep a shared `httpx.AsyncClient`.
- `warm_up()` sends a lightweight request through the shared client.
- `shutdown()` closes the client and is safe to call more than once.
- Multi-screenshot extraction is batched with `asyncio.gather`, preserving screenshot order while allowing parallel VLM calls.

#### Text and Startup
- `ProviderRegistry` resolves built-in providers lazily via `module:Class` dotted paths.
- `faster_whisper.py` remains importable when the local ASR provider is actually selected, but cloud-provider users no longer import `ctranslate2` during cold start.
- Adaptive vocabulary merges now use a bulk mapping API so large learned-mapping sets rebuild the regex once.
- Keyboard and clipboard insertion use one shared executor to serialize pyautogui/pyperclip calls.

### 📋 What's New in v0.3.6

#### Major Improvements
- **Audio & streaming performance:** R1–R7 from the v0.3.6 Track 1 plan
- **I/O, text, and startup optimizations:** R8–R14 from the v0.3.6 Track 2 plan
- **Persistent cleanup/vision HTTP clients**
- **Parallel multi-screenshot vision extraction**
- **Serialized keyboard/clipboard insertion**
- **Lazy provider imports for faster cold start**
- **Bulk adaptive vocabulary promotion**
- **Custom prompt mtime cache**

#### Files Added/Modified
- **New:** `src/agentvoca/audio/vad.py` - Dedicated VAD worker support and transition publishing
- **New:** `src/agentvoca/insertion/_executor.py` - Shared single-worker OS input executor
- **New:** `tests/unit/test_capture_vad_worker.py` - R1/R2 audio callback and VAD worker tests
- **New:** `tests/unit/test_capture_stop_offthread.py` - R3 auto-stop finalization tests
- **New:** `tests/unit/test_streaming_no_quadratic_copy.py` - R4 streaming memory-churn tests
- **New:** `tests/unit/test_cleanup_prompt_cache.py` - R9 custom prompt cache tests
- **New:** `tests/unit/test_cleanup_persistent_client.py` - R8 cleanup client lifecycle tests
- **New:** `tests/unit/test_vision_persistent_client.py` - R8 vision client lifecycle tests
- **New:** `tests/unit/test_insertion_serialized.py` - R11 serialized input injection tests
- **New:** `tests/unit/test_vocab_lookup.py` - R12 vocabulary lookup tests
- **New:** `tests/unit/test_vocab_bulk_mappings.py` - R13 bulk vocabulary mapping tests
- **New:** `tests/unit/test_lazy_provider_imports.py` - R14 lazy provider import tests
- **New:** `tests/integration/test_cancel_semantics.py` - R6 cancel semantics tests
- **New:** `tests/integration/test_vision_parallel.py` - R10 parallel vision extraction tests
- **Updated:** `src/agentvoca/audio/capture.py` - VAD worker, callback cleanup, auto-stop finalization, cancel handling
- **Updated:** `src/agentvoca/audio/chunker.py` - Bounded delta emission and buffer compaction
- **Updated:** `src/agentvoca/asr/faster_whisper.py` - O(N) streaming window snapshot and streaming partial scheduling
- **Updated:** `src/agentvoca/cleanup/openai_compatible.py` - Persistent client and prompt cache
- **Updated:** `src/agentvoca/vision/openai_compatible.py` - Persistent client
- **Updated:** `src/agentvoca/insertion/keyboard.py` and `clipboard.py` - Serialized pyautogui/pyperclip calls
- **Updated:** `src/agentvoca/vocab/dictionary.py` - O(1) casing lookup and bulk mappings
- **Updated:** `src/agentvoca/core/orchestrator.py` - Cancel tracking, provider shutdown, vision batching, hot-apply routing
- **Updated:** `src/agentvoca/core/registry.py` - Lazy built-in provider registry
- **Updated:** `src/agentvoca/main.py` - Cancel hotkey wiring, hot-reload routing, lazy registry usage, executor shutdown
- **Updated:** `docs/performance.md` - Performance table and v0.3.6 audio/ASR/I/O notes
- **Updated:** `docs/proposals/v0.3.6-optimization.md` - Optimization proposal
- **Updated:** `docs/proposals/v0.3.6-plan-agent1-audio-streaming.md` - Track 1 execution plan
- **Updated:** `docs/proposals/v0.3.6-plan-agent2-io-text-startup.md` - Track 2 execution plan

### 🧪 Testing

- **Audio Capture VAD Worker Tests:** `tests/unit/test_capture_vad_worker.py`
- **Auto-Stop Off-Thread Tests:** `tests/unit/test_capture_stop_offthread.py`
- **Streaming No Quadratic Copy Tests:** `tests/unit/test_streaming_no_quadratic_copy.py`
- **Chunker Tests:** `tests/unit/test_chunker.py`
- **Cancel Semantics Tests:** `tests/integration/test_cancel_semantics.py`
- **Cleanup Persistent Client Tests:** `tests/unit/test_cleanup_persistent_client.py`
- **Vision Persistent Client Tests:** `tests/unit/test_vision_persistent_client.py`
- **Vision Parallel Extraction Tests:** `tests/integration/test_vision_parallel.py`
- **Cleanup Prompt Cache Tests:** `tests/unit/test_cleanup_prompt_cache.py`
- **Serialized Insertion Tests:** `tests/unit/test_insertion_serialized.py`
- **Vocabulary Lookup Tests:** `tests/unit/test_vocab_lookup.py`
- **Bulk Vocabulary Mapping Tests:** `tests/unit/test_vocab_bulk_mappings.py`
- **Lazy Provider Import Tests:** `tests/unit/test_lazy_provider_imports.py`

Validation includes:

```bash
uv run pytest -q
uv run ruff check src/ tests/
uv run python scripts/benchmark.py --mode mock
```

All tests pass successfully ✅

### 🔄 Migration

- **Backward Compatible:** v0.3.6 is fully backward compatible with existing configurations.
- **No Config Changes Required:** Existing `config.yaml` files work unchanged.
- **No Breaking Changes:** Existing v2 streaming and v3 vision workflows continue as before, but with better performance and reliability.
- **Hot-Reload Safe:** Provider client replacement and config hot-apply are now safer during app runtime.

### 📚 Documentation

- **Performance Guide:** `docs/performance.md` - Updated latency and memory-budget notes
- **Optimization Proposal:** `docs/proposals/v0.3.6-optimization.md` - Root-cause analysis and release plan
- **Audio/Streaming Plan:** `docs/proposals/v0.3.6-plan-agent1-audio-streaming.md` - Track 1 execution details
- **I/O/Text/Startup Plan:** `docs/proposals/v0.3.6-plan-agent2-io-text-startup.md` - Track 2 execution details

### 📈 Performance Impact

#### Audio and Streaming
- Callback inference cost is cut by removing duplicate VAD inference.
- Auto-stop no longer performs multi-MB buffer joins on the audio callback.
- Streaming partials no longer copy the full recording on every 500 ms tick.
- Chunker memory is bounded by recent audio rather than total recording length.

#### Cloud and Vision
- Cleanup and vision providers reuse HTTP clients across dictations.
- Multi-screenshot extraction avoids serial VLM round trips.
- Warm-up now primes the actual shared provider client.

#### Startup and Text
- Cloud-provider users avoid importing local ASR dependencies during cold start.
- Large adaptive vocabulary sets rebuild once per merge instead of once per mapping.
- Keyboard and clipboard insertion no longer interleave OS input events.

### 🎨 User Experience Improvements

#### During Recording
- Smoother audio capture under load.
- Auto-stop no longer stalls the audio callback.
- Streaming partials avoid large memory churn during long dictations.

#### During Vision Sessions
- Multi-screenshot extraction feels faster because screenshot extractions run in parallel.
- One failed screenshot extraction does not block the rest of the batch.

#### During App Use
- Cancel behaves predictably, including cancel-after-stop and cancel during cleanup/insertion.
- Settings hot-apply is safer and less likely to race the pipeline.
- App exit is less likely to hang behind pyautogui/pyperclip work.

### 📢 Feedback Wanted

This release is primarily a reliability and performance pass rather than a feature release. We'd love to hear whether it improves the day-to-day experience:

- Did long dictations feel smoother?
- Did Cancel behave as expected after auto-stop?
- Did multi-screenshot vision extraction feel faster?
- Did cloud-provider startup feel quicker?

### 🙏 Acknowledgements

Special thanks to all contributors and users who reported performance issues, cancel bugs, vision batching delays, and startup concerns. This release consolidates the v0.3.6 optimization work into a stable, backward-compatible update.
