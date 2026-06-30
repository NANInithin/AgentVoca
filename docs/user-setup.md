# First-time setup

agentvoca v0.3.5 ships with an **interactive setup wizard** so you no longer
need to hand-edit `~/.agentvoca/config.yaml`. The wizard walks you through
every setting in roughly five minutes.

> **The wizard opens automatically every time you launch agentvoca.** Uncheck
> "Show this wizard every time I launch agentvoca" on the Welcome page if you
> prefer to launch straight into the dictation overlay.

## Quick start

1. Launch agentvoca (double-click the .exe, or `uv run agentvoca`).
2. The wizard appears. Choose one of:
   - **Use defaults** — faster-whisper (local) + rules cleanup + no API key.
   - **Customize** — recommended; walk through every page.
   - **Restore from backup** — load a `config.yaml.bak.*` file.
3. Work through the pages. Anything you skip can be changed later from
   **Settings** in the tray menu.
4. Click **Save** on the final page. agentvoca writes `config.yaml`,
   takes a timestamped backup, and (where possible) hot-applies your changes
   without restarting.

## What each page does

| # | Page | What you set |
|---|---|---|
| 1 | Welcome | Defaults / customize / restore; auto-open preference |
| 2 | App basics | Language, recording mode, cleanup style, debug logging |
| 3 | Microphone | Input device, sample rate, VAD, silence timeout |
| 4 | Speech-to-text | faster-whisper (local) **or** OpenAI-compatible API |
| 5 | Cleanup | Off / Rules (offline) / LLM (cloud) |
| 6 | Hotkeys | One preset dropdown per action; `(disabled)` to turn one off |
| 7 | Vocabulary & snippets | Inline terms + file paths |
| 8 | Advanced | Context, voice commands, adaptive vocab, vision, insertion |
| 9 | Review & save | Summary of your changes; click **Save** |

## API keys

The wizard never writes your API key to disk. On the Speech-to-text and
Cleanup pages, click **Set API key…** to:

1. See whether the env var is currently set in this session.
2. Set it for the current process (so saving the config takes effect
   immediately).
3. Copy a shell snippet to make it permanent:

   ```powershell
   # PowerShell (Windows)
   [System.Environment]::SetEnvironmentVariable(
       "OPENAI_API_KEY", "sk-...", "User")
   ```

   ```bash
   # bash / zsh (macOS / Linux)
   export OPENAI_API_KEY="sk-..."
   echo 'export OPENAI_API_KEY="sk-..."' >> ~/.zshrc
   ```

   ```fish
   # fish
   set -Ux OPENAI_API_KEY "sk-..."
   ```

## Hot-reload vs restart

Some settings apply immediately; others need a restart. The settings window
surfaces a banner listing every field that needs a relaunch.

| Hot-applied (no restart) | Requires restart |
|---|---|
| Cleanup provider / style | ASR provider / model |
| Hotkeys | Audio device / sample rate / VAD |
| Vocabulary & snippets | Insertion strategy |
| Adaptive vocab | Vision enable / provider |
| Context profiles | App mode / language / profile |
| Voice commands | Debug logging |
| Vision anchors / output format | |

## Reopening the wizard

The wizard auto-opens every launch unless you disabled it. To re-run it on
demand:

- **Tray menu → Setup Wizard…**
- **Hotkey**: `Ctrl+Alt+,` opens Settings; the toolbar includes a "Reopen
  setup wizard" link.

## Backing up your config

Every save creates a timestamped backup next to `config.yaml`:

```
~/.agentvoca/
├── config.yaml
├── config.yaml.bak.20260630_153022
└── state.json     ← wizard preferences (auto-open, etc.)
```

To restore, use the wizard's **Restore from backup** button, or just copy a
backup file over `config.yaml` and restart agentvoca.
