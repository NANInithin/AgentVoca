# Config Reference

All configuration is in a single YAML file validated at startup by pydantic v2.
The schema is defined in `src/agentvoca/config/schema.py`.

---

## Config file location

| Platform | Default path |
|---|---|
| macOS / Linux | `~/.agentvoca/config.yaml` |
| Windows | `%USERPROFILE%\.agentvoca\config.yaml` |

Pass a custom path with `--config <path>`.

---

## Environment variable expansion

Any string value may use `${ENV_VAR}` syntax. Missing variables are replaced with an
empty string at load time.

```yaml
cleanup:
  endpoint: https://${MY_PROXY_HOST}/v1
  api_key_env: MY_API_KEY_VAR
```

Secrets should never be written directly in the config file. Use `api_key_env` to
reference an environment variable by name — the app reads the variable at runtime.

---

## Validation rules

- `audio.sample_rate` must be in `[8000, 48000]`.
- `audio.silence_timeout_ms` must be `> 0`.
- `hotkeys.*` must match supported hotkey syntax (see `hotkeys` section below).
- `cleanup.custom_prompt_path` must exist on disk if set.
- If `asr.endpoint` is set and `asr.api_key_env` is set, the named env var must be
  present at startup.
- If `cleanup.endpoint` is set and `cleanup.api_key_env` is set, same requirement.

---

## app

Controls global application behavior.

| Key | Type | Default | Description |
|---|---|---|---|
| `profile` | string | `standard` | Cleanup style shorthand. One of: `raw`, `light`, `standard`, `technical`, `professional`, `custom`. |
| `language` | string | `auto` | Language hint passed to the ASR provider. |
| `mode` | string | `toggle` | Recording trigger mode: `push_to_talk`, `toggle`, or `auto_stop`. |
| `debug` | bool | `false` | Enable debug logging to console. |

---

## audio

Controls microphone capture.

| Key | Type | Default | Description |
|---|---|---|---|
| `input_device` | string | `default` | Device name substring or `"default"`. Run `uv run python -c "import sounddevice; print(sounddevice.query_devices())"` to list devices. |
| `sample_rate` | int | `16000` | Sample rate in Hz. Must be in `[8000, 48000]`. |
| `channels` | int | `1` | Number of input channels. |
| `vad_enabled` | bool | `true` | Enable silero-vad silence detection for auto-stop. |
| `silence_timeout_ms` | int | `900` | Milliseconds of silence before auto-stop triggers. |
| `max_recording_duration_s` | int | `120` | Maximum recording length in seconds before forced stop. |

---

## asr

Controls the speech-to-text provider.

| Key | Type | Default | Description |
|---|---|---|---|
| `provider` | string | *(required)* | Provider name. Built-in: `faster_whisper`, `openai_compatible`. |
| `model` | string | `null` | Model name or path. For faster-whisper: `tiny`, `base`, `small`, `medium`, `large-v3`, etc. |
| `endpoint` | string | `null` | Remote API base URL (e.g. `https://api.openai.com/v1`). Required for `openai_compatible`. |
| `api_key_env` | string | `null` | Name of the env var holding the API key (not the key itself). |
| `language_hint` | string | `null` | ISO-639-1 language code (e.g. `en`, `de`). Overrides `app.language`. |
| `extra` | object | `{}` | Provider-specific extra options. |

### faster_whisper notes

- The model is downloaded to the Hugging Face cache on first run.
- `large-v3` is the most accurate; `base` or `small` are faster for lower-latency use.
- If a GPU is available, faster-whisper uses it automatically.

### openai_compatible notes

- Works with OpenAI Whisper API, Groq, and any endpoint that accepts
  `multipart/form-data` file uploads at `/audio/transcriptions`.
- Set `api_key_env` to the name of the env var holding your API key.

---

## cleanup

Controls transcript post-processing.

| Key | Type | Default | Description |
|---|---|---|---|
| `provider` | string | `rules` | Provider name. Built-in: `rules`, `openai_compatible`, `none`. |
| `model` | string | `null` | Model name for LLM providers (e.g. `gpt-4o-mini`). |
| `endpoint` | string | `null` | API base URL for LLM providers. |
| `api_key_env` | string | `null` | Name of the env var holding the API key. |
| `style` | string | `standard` | Cleanup style. See `app.profile` values. |
| `preserve_code` | bool | `true` | If true, includes technical text preservation guardrails in the LLM system prompt. |
| `custom_prompt_path` | string | `null` | Path to a plain-text file to use as the full system prompt. Overrides `style`. |
| `extra` | object | `{}` | Provider-specific extra options. |

### Style modes

| Style | Behavior |
|---|---|
| `raw` | Return transcript unchanged. |
| `light` | Add basic punctuation and capitalization only. |
| `standard` | Remove filler words, add punctuation, fix basic grammar. |
| `technical` | Like standard but optimized for code and technical accuracy. |
| `professional` | Formal grammar and clear paragraphing. |
| `custom` | Use `custom_prompt_path` for full control. |

---

## insertion

Controls how the cleaned text is placed into the active application.

| Key | Type | Default | Description |
|---|---|---|---|
| `strategy` | string | `keyboard` | Primary insertion method: `keyboard` or `clipboard`. |
| `clipboard_fallback` | bool | `true` | Fall back to clipboard paste if keyboard insertion fails. |
| `delay_between_chars_ms` | int | `0` | Milliseconds between each typed character. Increase to `5`–`10` for apps that drop characters. |

---

## hotkeys

Global hotkey bindings. All keys are registered system-wide via pynput.

| Key | Type | Default | Description |
|---|---|---|---|
| `toggle_recording` | string | `ctrl+space` | Start/stop recording (or hold for push-to-talk). |
| `open_settings` | string | `ctrl+alt+comma` | Open the settings window. |
| `insert_last_transcript` | string | `null` | Re-insert the last successful transcript. |
| `cancel` | string | `escape` | Cancel an in-progress recording or discard the current transcript. |

**Supported key names:** letters (`a`–`z`), digits (`0`–`9`), `escape`, `space`, `comma`,
`period`, `slash`, `backslash`, `tab`, `enter`, `backspace`, `delete`, `home`, `end`,
`page_up`, `page_down`, `left`, `right`, `up`, `down`, `f1`–`f24`.

**Modifiers:** `ctrl`, `alt`, `shift`, `cmd` (macOS), `win` (Windows).

---

## vocabulary

User-defined term substitution applied after transcription and before cleanup.
Longer terms are matched before shorter ones. Matching is case-insensitive and
whole-word only.

| Key | Type | Default | Description |
|---|---|---|---|
| `path` | string | `null` | Path to a plain-text file, one term per line. Lines starting with `#` are ignored. |
| `inline` | list[string] | `[]` | Terms defined directly in config. Merged with `path` terms. |

```yaml
vocabulary:
  path: ~/.agentvoca/vocab.txt
  inline:
    - PyTorch
    - CUDA
    - NumPy
```

---

## snippets

Short trigger → full phrase expansion applied after vocabulary substitution.
Matching is case-insensitive and whole-word only.

| Key | Type | Default | Description |
|---|---|---|---|
| `path` | string | `null` | Path to a YAML file mapping trigger strings to expansions. |

```yaml
# ~/.agentvoca/snippets.yaml
"ppl": "people"
"btw": "by the way"
"asap": "as soon as possible"
"i.e.": "that is"
```

---

## Full example

See [config.example.yaml](../config.example.yaml) and the per-provider examples in
[examples/](../examples/).
