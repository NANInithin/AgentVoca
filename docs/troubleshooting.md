# Troubleshooting

Common setup and runtime issues for AgentVoca.

---

## Microphone permissions

### macOS

- System Settings → Privacy & Security → Microphone
- Grant permission to your terminal app or to the AgentVoca app bundle.
- After granting permission, restart the app.

### Windows

- Settings → Privacy & security → Microphone
- Enable "Allow desktop apps to access the microphone."
- Ensure your audio input device is not muted in Sound settings.

### Linux

- Ensure PulseAudio or PipeWire allows the process to access the mic.
- If running via a terminal, `pactl list sources` shows available input devices.

---

## Accessibility permissions (macOS — keyboard insertion)

**Symptom:** Keyboard insertion silently fails; clipboard fallback activates instead.

macOS requires explicit Accessibility permission for any app that simulates keyboard input.

- System Settings → Privacy & Security → Accessibility
- Add your terminal app (e.g., Terminal.app, iTerm2) or the AgentVoca app bundle.
- Restart the app after granting permission.

If you are running from a PyInstaller bundle, grant permission to the bundle's `.app`.

---

## VAD model not loading

**Symptom:** Startup is slow or logs show "Failed to load VAD model". App continues to
run with VAD disabled (always-on recording until manual stop).

- Silero-VAD downloads a model from Hugging Face on first run (~5 MB). Ensure you have
  internet connectivity on first launch.
- Set `audio.vad_enabled: false` to disable VAD entirely if the model cannot be loaded.

---

## faster-whisper model download

**Symptom:** First run is very slow or fails with a download error.

- Models are cached in `~/.cache/huggingface/hub/` (macOS/Linux) or
  `%USERPROFILE%\.cache\huggingface\hub\` (Windows).
- `large-v3` is ~3 GB; use `base` (~145 MB) or `small` (~460 MB) for faster startup.
- If behind a proxy, set `HTTPS_PROXY` before running.

---

## Hotkey conflicts

**Symptom:** The recording hotkey does nothing or activates another application.

- Change `hotkeys.toggle_recording` in `config.yaml` to an unused combination.
- Common conflicts: `ctrl+space` is used by macOS Spotlight and some IDE configurations.
- After changing hotkeys, restart the app.

---

## Insertion failures

**Symptom:** Text does not appear at the cursor after recording.

1. Enable `insertion.clipboard_fallback: true` as a first step.
2. On macOS, check Accessibility permissions (see above).
3. Some applications drop characters under fast typing. Set
   `insertion.delay_between_chars_ms: 5` or `10`.
4. If clipboard fallback also fails, check that the target app is in the foreground and
   accepts paste events.
5. Try switching `insertion.strategy: clipboard` as the primary strategy.

---

## Config validation error at startup

**Symptom:** App exits immediately with a config error message.

- Check YAML indentation — Python's YAML parser is strict about whitespace.
- Ensure `asr.provider` is set to a registered provider name.
- If `api_key_env` is set, confirm the named environment variable exists in the shell
  where you launch the app.
- Validate `audio.sample_rate` is in `[8000, 48000]` and `silence_timeout_ms > 0`.
- If `cleanup.custom_prompt_path` is set, confirm the file exists.

---

## Cleanup fails / raw transcript is inserted

**Symptom:** The LLM cleanup step fails and the unformatted transcript is inserted.

- Check `cleanup.endpoint` is correct and reachable.
- If `api_key_env` is set, confirm the env var is present and non-empty.
- Check network connectivity for remote providers.
- Inspect logs with `--debug` to see the full error from the provider.
- Set `cleanup.provider: rules` as a reliable fallback that needs no API key.

---

## App does not appear in the system tray

**Symptom:** The app starts (no error) but there is no tray icon.

- On Windows, the tray icon may be hidden. Click the "^" chevron in the taskbar.
- On macOS, ensure "Show in menu bar" is not blocked by another app.
- Restart the app with `--debug` and check the console for PySide6 errors.

---

## Debug logging

Run with `--debug` to enable verbose logging:

```bash
uv run agentvoca --debug
```

Logs are written to stdout. Redirect to a file for easier review:

```bash
uv run agentvoca --debug 2>&1 | tee agentvoca.log
```

---

## Still stuck?

Open an issue at the project repository and include:

- Your `config.yaml` with secrets redacted
- The debug log output
- Platform and Python version (`python --version`)
