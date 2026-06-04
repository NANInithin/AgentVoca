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
