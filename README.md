# AgentVoca

A developer-first, model-agnostic voice dictation desktop app for macOS and Windows.

Pair **any ASR provider** with **any cleanup/LLM provider** — local or remote — and have the
result inserted directly at the cursor in the active application.

---

## Features

- **Model-agnostic** — swap ASR or LLM providers with a one-line config change
- **Local-first** — runs entirely offline with faster-whisper; no data leaves the machine
- **Technical text preservation** — code identifiers, URLs, file paths, and CLI flags are
  never mangled by the LLM
- **Vocabulary substitution** — teach the app correct casing for your domain terms
- **Snippet expansion** — expand short triggers into full phrases
- **Push-to-talk, toggle, and VAD auto-stop** recording modes
- **Keyboard or clipboard insertion** with automatic fallback
- **System tray** integration with overlay indicator

---

## Quickstart

### 1. Install

```bash
# requires Python 3.11+ and uv (https://docs.astral.sh/uv/)
uv sync
```

### 2. Create a config file

**macOS / Linux**

```bash
mkdir -p ~/.agentvoca
cp config.example.yaml ~/.agentvoca/config.yaml
# edit ~/.agentvoca/config.yaml
```

**Windows (PowerShell)**

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.agentvoca" | Out-Null
Copy-Item config.example.yaml "$env:USERPROFILE\.agentvoca\config.yaml"
# edit $env:USERPROFILE\.agentvoca\config.yaml
```

### 3. Run

```bash
uv run agentvoca
```

The app starts in the system tray. Press **Ctrl+Space** (default) to start and stop recording.

---

## Zero-config / No API Key

AgentVoca works **out of the box with no API key**. The default configuration uses:

- **faster-whisper** for local, offline transcription
- **rules-based cleanup** for deterministic filler removal and punctuation — no LLM, no API key needed

Use this minimal config to get started immediately:

```yaml
asr:
  provider: faster_whisper
  model: base.en        # fast, offline — swap for large-v3 for higher accuracy

cleanup:
  provider: rules       # no API key required
```

The first run downloads the Whisper model (~145 MB for `base.en`, ~3 GB for `large-v3`).
Use `base` or `small` for faster startup and lower memory use.

> **Troubleshooting:** If you see `Config validation failed: ... requires an API key`, your
> config has `cleanup.provider: openai_compatible` set. Either set the required environment
> variable (see [Config with LLM cleanup](#config-with-llm-cleanup) below) or switch to
> `cleanup.provider: rules` to run without any API key.

---

## Config with LLM cleanup

To upgrade cleanup quality with an LLM, set `cleanup.provider: openai_compatible` and point
it at any OpenAI-compatible endpoint. The app will refuse to start if the required API key
environment variable is missing.

**OpenAI**

```yaml
asr:
  provider: faster_whisper
  model: large-v3

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

**OpenRouter** (access 200+ models with one key)

```yaml
cleanup:
  provider: openai_compatible
  endpoint: https://openrouter.ai/api/v1
  api_key_env: OPENROUTER_API_KEY
  model: openai/gpt-4o-mini
  style: standard
```

**Ollama (local LLM, no API key)**

```yaml
cleanup:
  provider: openai_compatible
  endpoint: http://localhost:11434/v1
  api_key_env: ""          # leave empty — Ollama needs no key
  model: llama3
  style: standard
```

**Groq**

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

## Providers

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

## Documentation

| Document | Description |
|---|---|
| [docs/config-reference.md](docs/config-reference.md) | Every config key, type, default, and constraint |
| [docs/providers.md](docs/providers.md) | How to implement and register a new provider |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common issues and fixes |

---

## License

MIT — see [LICENSE](LICENSE).
