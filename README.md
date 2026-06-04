# AgentVoca

A developer-first, model-agnostic voice dictation desktop app for macOS and Windows.

Pair **any ASR provider** with **any cleanup/LLM provider** — local or remote — and have the
result inserted directly at the cursor in the active application.

---

## Features

- **Model-agnostic** — swap ASR or LLM providers with a one-line config change
- **Local-first** — runs entirely offline with faster-whisper; no data leaves the machine
- **Live streaming transcription** — partial text appears in the overlay as you speak _(v2)_
- **Context-aware formatting** — pick a cleanup style based on the active app _(v2)_
- **Voice commands** — "new paragraph", "scratch that", and friends _(v2)_
- **Adaptive vocabulary** — the app learns your corrections and applies them automatically _(v2)_
- **Technical text preservation** — code identifiers, URLs, file paths, and CLI flags are never mangled by the LLM
- **Vocabulary substitution** — teach the app correct casing for your domain terms
- **Snippet expansion** — expand short triggers into full phrases
- **Push-to-talk, toggle, and VAD auto-stop** recording modes
- **Keyboard or clipboard insertion** with automatic fallback
- **System tray** integration with overlay indicator

> **v2 features are opt-in.** Each is an independent config flag that defaults to
> off, so an existing v1 `config.yaml` keeps working unchanged. See
> [What's new in v2](#whats-new-in-v2).

---

## Installation

Choose one of the two paths below depending on how you want to use AgentVoca.

---

### Option A — Download the `.exe` (Windows, no Python needed)

This is the recommended path for most users.

**Step 1 — Download the release**

Go to the [Releases page](https://github.com/NANInithin/AgentVoca/releases) and download
the latest `AgentVoca-vX.X.X-windows-x64.zip`. Extract it anywhere on your machine.

**Step 2 — Create the config folder**

AgentVoca looks for its config file at a fixed location. You need to create this folder
once before running the app for the first time.

Open PowerShell and run:

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agentvoca"
```

**Step 3 — Create your config file**

Download [`config.example.yaml`](https://github.com/NANInithin/AgentVoca/blob/main/config.example.yaml)
from the repo and save it as `config.yaml` inside the folder you just created:

```
C:\Users\<YourName>\.agentvoca\config.yaml
```

Or do it in one PowerShell command:

```powershell
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/NANInithin/AgentVoca/main/config.example.yaml" `
  -OutFile "$env:USERPROFILE\.agentvoca\config.yaml"
```

**Step 4 — Run the app**

Double-click `AgentVoca.exe` inside the extracted folder. The app starts in the system tray.
Press **Ctrl+Space** to start and stop recording.

> No API key is needed by default. The app uses local faster-whisper + rules-based cleanup
> out of the box. See [Cleanup Providers](#cleanup-providers) if you want LLM-powered cleanup.

---

### Option B — Run from source (Python, all platforms)

This path is for developers or macOS/Linux users.

**Step 1 — Clone the repo**

```bash
git clone https://github.com/NANInithin/AgentVoca.git
cd AgentVoca
```

**Step 2 — Install dependencies**

```bash
# requires Python 3.11+ and uv (https://docs.astral.sh/uv/)
uv sync
```

**Step 3 — Create a config file**

**macOS / Linux**

```bash
mkdir -p ~/.agentvoca
cp config.example.yaml ~/.agentvoca/config.yaml
```

**Windows (PowerShell)**

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agentvoca" | Out-Null
Copy-Item config.example.yaml "$env:USERPROFILE\.agentvoca\config.yaml"
```

**Step 4 — Run**

```bash
uv run agentvoca
```

The app starts in the system tray. Press **Ctrl+Space** (default) to start and stop recording.

---

## Config file location

Regardless of install method, AgentVoca always reads config from:

| OS | Path |
|---|---|
| Windows | `C:\Users\<YourName>\.agentvoca\config.yaml` |
| macOS / Linux | `~/.agentvoca/config.yaml` |

You can override this with the `-c` flag: `agentvoca -c /path/to/my-config.yaml`

---

## Zero-config / No API Key

AgentVoca works **out of the box with no API key**. The default `config.yaml` uses:

- **faster-whisper** for local, offline transcription
- **rules-based cleanup** for deterministic filler removal and punctuation — no LLM, no API key needed

```yaml
asr:
  provider: faster_whisper
  model: base.en        # fast and offline — swap for large-v3 for higher accuracy

cleanup:
  provider: rules       # no API key required
```

The first run downloads the Whisper model (~145 MB for `base.en`, ~3 GB for `large-v3`).

> **Troubleshooting:** If you see `Config validation failed: ... requires an API key`, your
> config has `cleanup.provider: openai_compatible` set. Either set the required environment
> variable or switch to `cleanup.provider: rules` to run without any API key.

---

## Cleanup Providers

### Rules (default — no API key)

```yaml
cleanup:
  provider: rules
  style: standard
```

Deterministic filler removal and punctuation. Works offline. No key needed.

### OpenAI

```yaml
cleanup:
  provider: openai_compatible
  endpoint: https://api.openai.com/v1
  api_key_env: OPENAI_API_KEY
  style: standard
```

```powershell
# Windows — set permanently for your user account
[System.Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-...", "User")
```

### OpenRouter (200+ models, one key)

```yaml
cleanup:
  provider: openai_compatible
  endpoint: https://openrouter.ai/api/v1
  api_key_env: OPENROUTER_API_KEY
  model: openai/gpt-4o-mini
  style: standard
```

### Ollama (local LLM, no API key)

```yaml
cleanup:
  provider: openai_compatible
  endpoint: http://localhost:11434/v1
  api_key_env: ""          # leave empty — Ollama needs no key
  model: llama3
  style: standard
```

### Groq

```yaml
cleanup:
  provider: openai_compatible
  endpoint: https://api.groq.com/openai/v1
  api_key_env: GROQ_API_KEY
  model: llama3-8b-8192
  style: standard
```

See `examples/` for more configuration examples.

---

## All Providers

### ASR

| Name | Config value | Notes |
|---|---|---|
| faster-whisper (local) | `faster_whisper` | Default. Runs on CPU or GPU. Requires model download on first use. |
| OpenAI-compatible API | `openai_compatible` | Works with OpenAI Whisper API, Groq, self-hosted endpoints. |

### Cleanup

| Name | Config value | Notes |
|---|---|---|
| Rules-based | `rules` | **Default. No API key needed.** Deterministic filler removal + punctuation. |
| OpenAI-compatible LLM | `openai_compatible` | Sends transcript to any chat-completions endpoint. Requires API key env var. |
| None (pass-through) | `none` | Inserts the raw transcript exactly as transcribed. |

### Insertion

| Name | Config value | Notes |
|---|---|---|
| Keyboard simulation | `keyboard` | Default. Uses pyautogui to type at the cursor. |
| Clipboard paste | `clipboard` | Writes to clipboard and sends Ctrl+V / Cmd+V. |

---

## CLI options

```
usage: agentvoca [-h] [-c CONFIG] [--debug] [--version]

  -c, --config PATH   Path to config YAML (default: ~/.agentvoca/config.yaml)
  --debug             Enable debug logging
  --version           Print version and exit
```

---

## Development

```bash
# install dev dependencies
uv sync

# run tests
uv run pytest

# lint
uv run ruff check src/ tests/

# format
uv run ruff format src/ tests/
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on adding new providers.

---

## What's new in v2

v2 is a latency-and-intelligence layer on top of the v1 pipeline. Everything is
additive and opt-in; the v1 batch path remains the always-available fallback.

### Live streaming transcription

Turn on `asr.streaming` to see partial text in the overlay as you talk — dim and
italic to make clear it is a preview. The accurate model still produces the final
inserted text on stop.

```yaml
asr:
  provider: faster_whisper
  model: base               # accurate final pass (inserted text)
  streaming: true
  streaming_model: base     # fast model for the live preview only
  warm_up: true             # preloads models at startup (default)
```

**GPU note:** if you see `CUDA inference probe failed — switching to CPU` at startup,
your machine cannot run ctranslate2 CUDA inference. Add `extra: {device: cpu}` to skip
the GPU attempt and start faster:

```yaml
asr:
  provider: faster_whisper
  model: base
  extra:
    device: cpu
```

For proper GPU acceleration, install the [CUDA Toolkit 12.x](https://developer.nvidia.com/cuda-toolkit).

### Undo last insertion

Press the configured `hotkeys.undo` key (default `ctrl+shift+z`) after a dictation to
remove the inserted text. The app re-focuses the window where text was inserted and
removes exactly the characters it typed — no clipboard needed, works even if you have
switched focus to the terminal to watch logs.

> **Note:** `ctrl+alt+z` is captured by NVIDIA drivers on most systems. Use `ctrl+shift+z`
> or a function-key combination instead.

### Context, commands & adaptive vocabulary

```yaml
context:                   # per-app cleanup style (glob patterns, "*" = fallback)
  enabled: true
  profiles:
    "Code.exe": technical   # Windows: use exe name
    "Code": technical       # macOS: use app name
    "*": standard

commands:                  # "new line", "new paragraph", "scratch that", ...
  enabled: true

adaptive:                  # learn corrections, auto-apply after promote_threshold repeats
  enabled: true
  promote_threshold: 2      # correct the same mis-recognition twice to lock it in
```

**Adaptive vocab timing:** with streaming + CPU the correction window is 30 seconds
(undo hotkey → speak the correction → pipeline finishes). You need to complete the
undo + re-dictation within that window.

A complete example lives in [examples/config.streaming.yaml](examples/config.streaming.yaml).
Full details: [docs/context-and-commands.md](docs/context-and-commands.md) and
[docs/performance.md](docs/performance.md).

### Benchmarking

A pipeline latency harness ships in `scripts/benchmark.py`:

```bash
uv run python scripts/benchmark.py --mode mock   # CI-gated orchestration budgets
uv run python scripts/benchmark.py --mode real   # real local models over WAV fixtures
```

---

## Documentation

| Document | Description |
|---|---|
| [docs/config-reference.md](docs/config-reference.md) | Every config key, type, default, and constraint |
| [docs/performance.md](docs/performance.md) | Latency budgets, streaming/warm-up tuning, benchmark harness |
| [docs/context-and-commands.md](docs/context-and-commands.md) | Context profiles, voice commands, adaptive vocab, privacy |
| [docs/providers.md](docs/providers.md) | How to implement and register a new provider |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common issues and fixes |

---

## License

MIT — see [LICENSE](LICENSE).
