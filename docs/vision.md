# Screenshot-to-text (vision) — v3

AgentVoca v3 lets you fold the *content* of a screenshot into your dictation
instead of pasting the image. While you talk, you snip a region of the screen;
a vision-language model (VLM) extracts the useful parts — tables, values, a
description — as markdown or plain text, and the result is spliced into your
dictated text. Markdown is far cheaper in tokens than an image when the text
later goes to another AI tool, and it lands as editable text at your cursor.

> **Opt-in and API-based.** Vision is off by default. When enabled it sends
> the captured screenshot to the configured endpoint, so it requires a
> vision-capable model and an API key. The rest of AgentVoca still runs
> locally; only screenshots you explicitly snip leave the machine.

---

## How it works

1. You start recording (default `ctrl+space`) and dictate normally.
2. At any point during the dictation you press **`hotkeys.capture_screenshot`**
   (e.g. `ctrl+shift+s`). Your OS region-snip tool opens; drag out a selection.
   - **Windows:** Snip & Sketch (`ms-screenclip:`) → clipboard.
   - **macOS:** `screencapture -i` → temp file.
   - **Linux:** `gnome-screenshot` / `spectacle` / `maim` if present.
   You can snip multiple times in one dictation.
3. You stop recording. For each screenshot, the VLM extracts content, using
   **your spoken words as the instruction** — so "make a table of the expenses"
   yields a markdown table, while "describe the chart" yields prose.
4. Extractions are spliced into your transcript at **anchor phrases** in
   capture order (1st snip → 1st anchor, etc.). Anything left over is appended
   at the end.
5. The merged text passes through cleanup (with code/number preservation forced
   on, so tables survive) and is inserted at the cursor. Use the undo hotkey to
   revert if needed.

### Anchor phrases

An anchor phrase marks *where* an extraction goes. Built-in defaults include:

```
the attached screenshot, this screenshot, the screenshot, attached screenshot,
this image, the attached image, as shown, as shown above, as shown below,
as in the screenshot   (and "screen shot" spellings)
```

Example — you say:

> "There's a client submission today. We need a table of all the expenses **as
> in the attached screenshot**, ready for review."

…and snip the spreadsheet. The phrase "as in the attached screenshot" is
replaced by the extracted markdown table; cleanup smooths the surrounding
prose. If you don't speak an anchor, the table is simply appended at the end.

Override the phrase list with `vision.anchor_phrases` in config.

---

## Configuration

```yaml
vision:
  enabled: true
  endpoint: https://openrouter.ai/api/v1   # any OpenAI-compatible vision endpoint
  api_key_env: OPENROUTER_API_KEY          # env var name (not the key itself)
  model: openai/gpt-4o-mini                # vision-capable model id
  output_format: auto                      # auto | markdown | plain
  capture_timeout_s: 30                    # seconds to wait while you snip
  # anchor_phrases: ["the attached screenshot", "as shown"]

hotkeys:
  capture_screenshot: ctrl+shift+s
```

| Key | Type | Default | Notes |
|---|---|---|---|
| `enabled` | bool | `false` | Master switch for the feature. |
| `provider` | str | `openai_compatible` | The only built-in vision provider. |
| `endpoint` | str | OpenAI | Any OpenAI-compatible `/v1` base URL. |
| `api_key_env` | str | – | Name of the env var holding your key. |
| `model` | str | `gpt-4o-mini` | Must be a vision-capable model. |
| `output_format` | enum | `auto` | `auto` lets the model infer from your words. |
| `capture_timeout_s` | int | `30` | Max wait for you to finish snipping (1–300). |
| `anchor_phrases` | list | built-ins | Override the splice-point phrases. |

`hotkeys.capture_screenshot` is only active when `vision.enabled` is true.

---

## Choosing a model

Any OpenAI-compatible endpoint that accepts image content blocks works — the
same adapter serves remote APIs and local servers.

| Provider | `endpoint` | Example `model` |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini`, `gpt-4o` |
| OpenRouter | `https://openrouter.ai/api/v1` | `anthropic/claude-opus-4-8`, `openai/gpt-4o-mini`, `google/gemini-2.0-flash` |
| Anthropic (OpenAI-compat) | `https://api.anthropic.com/v1` | a Claude vision model |
| Ollama (local) | `http://localhost:11434/v1` | `qwen2.5-vl`, `minicpm-v` (leave `api_key_env` empty) |

For structured extraction (tables, values), a strong general VLM such as
Claude or GPT-4o gives the most reliable markdown.

---

## Local / offline (planned)

v3 ships API-only. A future release adds an in-process local VLM (similar to
how faster-whisper runs ASR offline), with **GOT-OCR 2.0** as the default
download — a compact, document-focused model that turns images straight into
markdown/LaTeX tables. Until then, the Ollama route above gives a local option
through the same `openai_compatible` provider.

---

## Privacy

When vision is enabled, the bytes of each screenshot you snip are sent to the
configured `endpoint`. Treat that endpoint the same way you would any cloud
service: it may log or cache requests. Keep `vision.enabled: false` (the
default) if you don't want screenshots to leave the machine.

---

## Troubleshooting

- **"Vision enabled but no native screenshot tool was found"** — install your
  platform's snip tool (Linux: `gnome-screenshot`/`spectacle`/`maim`).
- **Nothing gets spliced** — confirm you pressed the capture hotkey *while
  recording*, finished the snip before stopping, and that the model is
  vision-capable. Check logs for `Vision: N screenshot(s) extracted`.
- **`Config validation failed: ... Vision provider requires an API key`** — set
  the env var named by `vision.api_key_env`, or disable vision.
- **Table got mangled** — extraction runs through cleanup with code/number
  preservation forced on, but a weak model may still reformat. Try a stronger
  vision model or `output_format: markdown`.
