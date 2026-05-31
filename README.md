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

## Providers

### ASR

| Name | Config value | Notes |
|---|---|---|
| faster-whisper (local) | `faster_whisper` | Default. Runs on CPU or GPU. Requires model download on first use. |
| OpenAI-compatible API | `openai_compatible` | Works with OpenAI Whisper API, Groq, self-hosted endpoints. |

### Cleanup

| Name | Config value | Notes |
|---|---|---|
| Rules-based | `rules` | Default. Deterministic filler removal + punctuation. No API key needed. |
| OpenAI-compatible LLM | `openai_compatible` | Sends transcript to any chat-completions endpoint. |
| None (pass-through) | `none` | Inserts the raw transcript exactly as transcribed. |

### Insertion

| Name | Config value | Notes |
|---|---|---|
| Keyboard simulation | `keyboard` | Default. Uses pyautogui to type at the cursor. |
| Clipboard paste | `clipboard` | Writes to clipboard and sends Ctrl+V / Cmd+V. |

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

## Minimal config

```yaml
asr:
  provider: faster_whisper
  model: large-v3
```

The first run downloads the model (~3 GB for large-v3). Use `base` or `small` for faster
startup and lower memory use at the cost of accuracy.

---

## Config with OpenAI cleanup

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

Set `OPENAI_API_KEY` in your environment before running. See `examples/` for more
configuration examples including Ollama and local API servers.

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
