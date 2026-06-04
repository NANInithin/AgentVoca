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

**`ctrl+alt+z` undo not working on Windows:**
NVIDIA drivers silently capture `ctrl+alt+z` (ShadowPlay overlay toggle) before any
other app sees it. Use `ctrl+shift+z` for the undo hotkey instead:

```yaml
hotkeys:
  undo: ctrl+shift+z
```

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

## CUDA inference fails on Windows (`cublas64_12.dll not found`)

**Symptom:** Log shows `CUDA inference probe failed — switching to CPU` on every startup.

The model loads on GPU (memory allocation works), but CUDA matrix operations need
`cublas64_12.dll` which Windows cannot find even if `nvidia-cublas-cu12` is pip-installed.

**Quick fix — force CPU mode:**

```yaml
asr:
  extra:
    device: cpu
```

This skips the GPU probe and starts faster with no warning.

**Proper GPU fix — install CUDA Toolkit 12.x:**

Download and install [CUDA Toolkit 12.x](https://developer.nvidia.com/cuda-toolkit) from
NVIDIA. The installer places `cublas64_12.dll` on the system `PATH` where Windows finds it
automatically. Remove the `device: cpu` override afterwards.

---

## Streaming: same text repeated / very long transcription after stop

**Symptom:** After stopping recording, transcription takes minutes and inserts repeated lines.

This was a bug (fixed in v2.1) where the AudioChunker sent the rolling *window* with each
chunk rather than the *delta*. If you are seeing this, ensure you have the latest version.

---

## Undo does not remove text from the target app

**Symptom:** Pressing the undo hotkey is logged (`Hotkey triggered: undo`) but the text
in the editor is not removed.

The undo targets the window that received the insertion. Keep that window focused or
do not switch away before pressing undo — the app re-focuses it automatically before
sending the backspace keystrokes.

---

## Adaptive vocabulary: no correction recorded

**Symptom:** After undo + re-dictate, no `Adaptive: recording correction` log appears.

The correction window is **30 seconds** from the undo hotkey press to the pipeline
finishing the second dictation. With streaming + CPU this can take 10–15 s. If you
speak too slowly or wait too long, the window expires. Speak the correction immediately
after pressing undo.

Also: the mis-heard and corrected texts must differ (case-insensitive). If Whisper
keeps producing the same text, the correction is not recorded.

---

## Still stuck?

Open an issue at the project repository and include:

- Your `config.yaml` with secrets redacted
- The debug log output
- Platform and Python version (`python --version`)
