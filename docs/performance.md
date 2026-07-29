# Performance & Latency

AgentVoca v2 is built around one goal: text should appear the moment you stop
talking. This page documents the latency budgets, the knobs that affect them,
hardware-tier recommendations, and how to run the benchmark harness.

---

## Latency budgets

These are the **targets** for the local default stack (faster-whisper +
`rules` cleanup). Remote providers are network-bound and not enforced.

| Stage | v1 (batch) | v2 target | What moves it |
|---|---|---|---|
| First partial visible | none | ≤ 500 ms after first speech | `asr.streaming` (chunker) |
| Key-up → final inserted (short utterance) | full ASR + cleanup, serial | ≤ 800 ms | warm-up + pipelined cleanup |
| Cold-start penalty (first dictation) | seconds | 0 (amortized at startup) | `warm_up()` |
| Cleanup tail after stop (multi-sentence) | full pass | ≤ 40% of v1 | `cleanup.streaming` |
| Audio callback p99 (per 64 ms block) | unbounded (silero inference inline) | ≤ 5 ms | dedicated VAD worker thread (R2) |
| Streaming-ASR memory churn (per 500 ms partial) | `O(N)` per partial (full copy) | bounded by window (≈ `window_s * sample_rate * 4 B` per partial) | memoryview + single copy (R4) |
| Audio buffer (peak) | grows with recording | bounded — chunker compacts after each emit | chunker `_get_delta` deletes emitted bytes (R5) |
| Auto-stop join + publish | blocks the audio callback (multi-MB `b"".join`) | runs on the loop thread, callback returns in < 5 ms | `stop_recording` defers finalization (R3) |

The CI benchmark does **not** measure these real-model numbers (CI has no GPU).
It measures *orchestration overhead* with mock providers, so a regression in
the pipeline glue (an accidental blocking call, an O(n²) loop) fails the build.

---

## The benchmark harness

`scripts/benchmark.py` replays audio through the full orchestrator and records
the per-stage `TimingEvent` durations plus an end-to-end wall-clock time.

### Mock mode (default, CI-gated)

```bash
uv run python scripts/benchmark.py --mode mock
```

- Mock ASR / cleanup / insertion providers with ~0 simulated latency.
- Exercises the real orchestration path (state machine, event bus, vocab /
  snippet / command stages) while isolating it from model variance.
- **Enforces budgets by default** and exits non-zero on a breach — this is the
  gate CI runs on every push.

Useful flags:

```bash
# simulate a slow provider to see the budget table react
uv run python scripts/benchmark.py --mode mock --latency-ms 50

# write a machine-readable report
uv run python scripts/benchmark.py --mode mock --json report.json

# report only, never fail
uv run python scripts/benchmark.py --mode mock --no-enforce
```

### Real mode (manual / nightly)

```bash
uv run python scripts/benchmark.py --mode real
```

- Uses real local `faster_whisper` (`base.en`) + `rules` over the WAV fixtures
  in `tests/fixtures/audio/`.
- Requires the model to be present (first run downloads it).
- Reports only (no enforced budgets) because numbers depend on your hardware.

Sample output:

```
stage                     mean       p50       p95       max    budget  status
----------------------------------------------------------------------------------
asr                       0.01      0.00      0.02      0.03        75  ok
cleanup                   0.00      0.00      0.00      0.01        75  ok
insertion                 0.00      0.00      0.00      0.01        75  ok
end_to_end                0.06      0.05      0.08      0.09       250  ok
```

The mock budgets live in `MOCK_BUDGETS_MS` at the top of `scripts/benchmark.py`.
Change them only with a deliberate reason — they exist to catch gross
regressions, not to micro-benchmark.

---

## Tuning knobs

All of these are config keys (see `docs/config-reference.md` for the full list).

### Streaming (live partials)

```yaml
asr:
  provider: faster_whisper
  model: large-v3          # accurate final pass
  streaming: true          # turn on live partial transcripts
  streaming_model: base.en # fast model used only for the live preview
  streaming_chunk_ms: 500  # how often a partial is produced (100–2000)
  streaming_window_s: 8    # rolling window re-transcribed for each partial
```

- A smaller `streaming_model` (`tiny`, `base.en`) keeps partials cheap.
- A smaller `streaming_window_s` lowers per-chunk cost but shortens the context
  the preview can see.
- The **final** inserted text always comes from the accurate `model`, so
  partials being rough is fine — they are throwaway previews.

> **Cost note:** with `streaming: true` the streaming and accurate models can be
> resident at the same time. On a low-VRAM GPU prefer a small `streaming_model`
> or keep `streaming: false`.

### Warm-up

```yaml
asr:
  warm_up: true     # preload the model + init CUDA at startup (default)
cleanup:
  warm_up: true     # prime the HTTP pool / load a local LLM at startup
```

Warm-up runs in the background after the tray appears, so it never blocks
startup. It removes the first-dictation penalty. Disable it only if startup
memory pressure is a concern.

### Audio callback budget (R2)

The sounddevice callback runs every ~64 ms (`frames_per_buffer=1024` @
16 kHz). It must do **near-zero work** so audio is never underrun on a
loaded system. Since v0.3.6, silero VAD inference runs on a dedicated
daemon thread (`agentvoca-vad`); the callback only enqueues a tuple and
reads a cached bool. The budget is enforced by
`tests/unit/test_capture_vad_worker.py::test_callback_p99_under_5ms_with_slow_inference`.

### Streaming-ASR memory churn (R4)

Each `asr.streaming_chunk_ms` tick used to allocate a full copy of the
recording (`np.frombuffer(bytes(full_buffer))`) plus another full copy
into the window. Over a 2-minute dictation that was ~0.9 GB of churn and
a small per-block stall on the loop. Since v0.3.6, the window is built
with a `memoryview` slice and exactly one `.copy()`, and the buffer is
only snapshotted when a new partial is actually being submitted. The
peak-per-iteration bound is `window_s * sample_rate * 4 B` (one window).
Enforced by `tests/unit/test_streaming_no_quadratic_copy.py`.

### Audio buffer footprint (R5)

`AudioChunker._buffer` used to grow for the entire recording — a second
copy of the audio alongside the orchestrator's full buffer and the
sounddevice port's own copies. Since v0.3.6, `_get_delta` deletes the
bytes it just emitted (`del self._buffer[:end]`) so peak usage is the
chunker-cadence window, not the full recording.

### Auto-stop and Cancel (R3, R6)

`stop_recording()` no longer runs `b"".join(self._audio_buffer)` on the
audio thread; the join + `RecordingStoppedEvent` publish are scheduled
on the asyncio loop. The Cancel hotkey is now wired to a new
`Orchestrator.cancel()` that tracks and cancels the in-flight pipeline
task, so a cancel landing before `_run_insertion` prevents insertion
entirely. (Cancelling mid-`typewrite` cannot un-type — accepted
limitation, documented in the parent proposal.)

### Compute type (quantization)

`faster_whisper` auto-probes the best compute type for your device via
CTranslate2 (`float16` on a capable GPU, `int8` on CPU). Override it only if
you have a reason:

```yaml
asr:
  provider: faster_whisper
  extra:
    device: cuda          # auto | cuda | cpu
    compute_type: int8_float16
```

| Hardware tier | device | compute_type | model | notes |
|---|---|---|---|---|
| Modern NVIDIA GPU (≥ 6 GB) | cuda | float16 (auto) | large-v3 | best accuracy, fast |
| Entry GPU / low VRAM | cuda | int8_float16 | medium / base.en | lower memory |
| CPU only (modern laptop) | cpu | int8 (auto) | base.en | usable, offline |
| CPU only (older) | cpu | int8 | tiny / base.en | prioritize a small model |

Leave `compute_type` unset (`default`) to let the probe choose — that is the
recommended setting.

---

## Where the time goes

Per-stage timing is emitted as `TimingEvent` on the event bus for **every**
dictation cycle and written to the log (`~/.agentvoca/agentvoca.log`). Run with
`--debug` to see stage timings live. If a stage is slow, the log tells you
which one before you start guessing.

---

## Observer resource budget (v0.4.0)

The Observer subsystem is a background process, so it has its own
resource envelope on top of the dictation pipeline. The numbers
below are the **hard acceptance gate** for a session running on a
4-core laptop with the default config.

| Metric | Budget | What moves it |
|---|---|---|
| Added idle CPU while a session is open | **< 5 %** | Foreground poll (2 Hz), token-bucket keyframe cap, phash dedup *before* OCR |
| Added RSS while a session is open | **< 400 MB** | Single shared ASR model, bounded queues, JPEG-on-write |
| Sustained keyframes | **≤ 4 / minute** | `observer.triggers.max_keyframes_per_min` |
| Audio callback p99 | unchanged (< 5 ms) | The ambient tap is one `put_nowait` + `except Full: pass` — nothing else |
| Disk per hour, typical | < 40 MB | 1280 px JPEG q75, deduped, ~4/min |

### Tuning knobs

If the budget is breached on a particular machine, the right
response is to reduce the capture rate, **never** to exceed the
budget.

| Knob | Effect |
|---|---|
| `observer.triggers.max_keyframes_per_min` | Token-bucket cap; lower for fewer keyframes. |
| `observer.triggers.min_interval_ms` | Minimum time between two keyframes; raise for fewer. |
| `observer.triggers.scroll_settle_ms` | Quiet period before a scroll counts as "settled". |
| `observer.triggers.speech_onset` | The most valuable trigger; turning it off roughly halves the keyframe rate. |
| `observer.ocr.provider` | `none` skips OCR entirely (saves ~50–150 ms/keyframe and OCR memory). |
| `observer.ocr.max_queue` | Bounded OCR queue; overflow drops the oldest. |
| `observer.screen.max_width_px` | Smaller images encode/decode faster; below 1280 OCR accuracy suffers. |
| `observer.screen.dedup_phash_distance` | Raise to dedup more aggressively; lower to let through more. |
| `observer.compile.provider` | `rules` is offline; `openai_compatible` adds a per-block LLM round-trip. |

### What the numbers do not cover

- A long session can fill the per-session disk cap
  (`observer.storage.max_session_mb`, default 500 MB). Once hit,
  keyframe capture stops, a `gap` is recorded, and audio continues.
- The `openai_compatible` compiler is network-bound. A 30-block
  session is 30 parallel LLM calls + 1 session-summary call. The
  budget assumes a fast network; on a slow network the compile
  latency grows linearly with the number of blocks, but the
  per-block degradation contract means a failed call falls back to
  the rules render for that block, so a partial network failure
  never blocks the artifact.

### Crash-recovery cost

On startup, the controller queries the store for sessions left
`status='open'`. The query is a single indexed SELECT and
completes in < 5 ms. The recovery dialog is non-modal and does not
block startup.
