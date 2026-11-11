# First-time setup

agentvoca opens a short setup the first time you launch it (and again only if
your saved config cannot be loaded). It asks about models and API keys only;
everything else starts on sensible defaults and lives in **Settings**.

## Install

```bash
uv tool install "agentvoca @ git+https://github.com/NANInithin/AgentVoca"
agentvoca
```

## Quick start

1. Launch agentvoca (`agentvoca`, the .exe, or `uv run agentvoca` from source).
2. **Speech-to-text** — pick a local faster-whisper model (offline, free) or
   a cloud model. For cloud, choose the provider (OpenAI, Groq, OpenRouter or
   Custom), the model, and paste your API key.
3. **Cleanup** — Off, Rules (offline) or an LLM. For an LLM, choose the
   provider (OpenAI, OpenRouter, Groq, Anthropic, Ollama or Custom), the model,
   and paste your API key.
4. Click **Save**. agentvoca writes `config.yaml`, takes a timestamped backup,
   and starts.

Audio, hotkeys, vocabulary, streaming, prompts, vision, Observer and every
other option are in **Tray menu → Settings…**.

## API keys

Paste a key once and it is kept after you close the app. The key is stored in
the operating system's secure credential store (Windows Credential Manager,
macOS Keychain, Secret Service on Linux) via `keyring`, never in
`config.yaml` or any other plain file. `~/.agentvoca/keys.json` only lists
which keys are saved and when they expire.

Each key field has:

- **Save key** — store the pasted key (also happens when you click Save /
  Next with a pasted key).
- **Delete key** — remove the key from the credential store and from the
  running app.
- **Keep** choice — *Keep until I delete it* (default), *Delete when AgentVoca
  closes*, or *Delete after 1 / 7 / 30 / 90 days*. Expired keys are removed at
  startup and checked hourly while the app runs.

Saved keys are loaded into the matching environment variable (for example
`OPENAI_API_KEY`) at startup. If you already set that variable yourself, your
value wins. When no credential store is available (some headless Linux
machines), keys are kept for the current session only and the app tells you.

## Hot-reload vs restart

Some settings apply immediately; others need a restart. The settings window
surfaces a banner listing every field that needs a relaunch.

| Hot-applied (no restart) | Requires restart |
|---|---|
| Speech-to-text provider / model / endpoint / key | Speech-to-text streaming (live preview) |
| Cleanup provider / style | Audio device / sample rate / VAD |
| Hotkeys | |
| Vocabulary & snippets | Insertion strategy |
| Adaptive vocab | Vision enable / provider |
| Context profiles | App mode / language / profile |
| Voice commands | Debug logging |
| Vision anchors / output format | |

## Reopening the wizard

To re-run the setup on demand:

- **Tray menu → Setup Wizard…**
- **Hotkey**: `Ctrl+Alt+,` opens Settings; the toolbar includes a "Reopen
  setup wizard" link.

## Backing up your config

Every save creates a timestamped backup next to `config.yaml`:

```
~/.agentvoca/
├── config.yaml
├── config.yaml.bak.20260630_153022
├── keys.json      ← names + expiry of saved API keys (no key values)
└── state.json     ← first-run state
```

To restore, use the wizard's **Restore from backup** button, or just copy a
backup file over `config.yaml` and restart agentvoca.
