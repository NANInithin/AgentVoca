# AgentVoca Release Notes

## v0.4.0 — Observer Mode

**Released:** 2026-07-29  
**Version:** 0.4.0

### 🎯 Overview

AgentVoca v0.4.0 ships **Observer mode** — a background session
recorder that turns what you said, what was on screen, and what
you highlighted into a readable markdown document and a
machine-readable JSON sidecar at the end of a working session.

> **Agent mode is NOT in this release.** It is v0.5.0. Observer's
> JSON sidecar is the contract Agent will consume; nothing in
> Observer executes a task, writes a file on your behalf, or
> calls a tool.

The Observer subsystem is fully opt-in (`observer.enabled: false`
by default), fully offline by default (RapidOCR + the rules
compiler need no API key), and ships with a persistent visible
indicator (tray icon + non-dismissable on-screen badge) and an
exclusion list for password managers and incognito windows.

### ✨ New Features

#### Session recording
- **Ambient capture** — every spoken line during a session is
  transcribed via the already-configured ASR provider. The
  ambient tap on the existing mic stream is one
  `put_nowait` + `except Full: pass` — it never blocks the audio
  callback.
- **Dictation coexists with Observer** — when the dictation hotkey
  is pressed during a session, the dictated transcript also lands
  in the log tagged `utterance_dictated`, and dictation preempts
  ambient via the ASR arbiter.
- **Four keyframe triggers** (each individually toggleable):
  foreground window change, scroll-settle, click / selection,
  speech onset. All four gate through a token-bucket cap
  (default 4/min) and a minimum interval (default 4 s).
- **Active-window capture** — only the focused window is grabbed,
  downscaled to 1280 px wide, JPEG q75, and deduped by
  perceptual hash before OCR. Per-frame work runs on a dedicated
  worker with a bounded queue (drop-on-full).
- **OCR** — RapidOCR (ONNX) local by default; optional
  `openai_compatible` VLM escalation. OCR runs on a dedicated
  worker thread; failures are isolated to one keyframe.
- **Selection capture** — Windows UI Automation `TextPattern`,
  read-only, never touches the clipboard. `ocr_rect` fallback
  for apps where UIA is unavailable.
- **Privacy exclusion list** — foreground app globs + window-title
  patterns. Matching the exclusion list records a
  `pause_start` / `pause_end` pair and captures nothing —
  including ambient audio.

#### Compilation
- **Rules compiler** (default, no API key) — deterministic,
  per-block markdown with **Said** / **Highlighted** / **On
  screen** sections; aggressive OCR dedup keeps documents short;
  markdown-significant characters in OCR text are escaped.
- **OpenAI-compatible compiler** — two-phase rolling
  summarization: per-block narratives run in parallel, then a
  one-paragraph session summary. Per-block LLM failures fall back
  to the rules render with `degraded=True`; the user always gets
  an artifact.
- **None compiler** — raw chronological dump: one line per event.
- **JSON sidecar** — `agentvoca.observer.session/1` schema; the
  v0.5.0 Agent contract. Block boundaries are re-derived from
  `split_blocks`, so the JSON can never disagree with the
  markdown.

#### UX
- **Tray Observer submenu** — Start / Stop session, Pause /
  Resume, Open last session, Delete all sessions.
- **Non-dismissable on-screen badge** — `REC HH:MM:SS` or
  `PAUSED`, click-through, visible for the entire session. The
  only way to dismiss it is to end the session.
- **Two new hotkeys** — `hotkeys.toggle_observer` and
  `hotkeys.pause_observer`, exposed in the Hotkeys tab. The
  default config leaves them unset; they can also be reached
  from the tray menu.
- **Settings UI** — full **Observer** tab in the Settings window
  with a privacy notice at the top and a cloud warning that
  appears the moment `ocr.provider` or `compile.provider` is set
  to `openai_compatible`.
- **Crash recovery dialog** — non-modal, after pipeline startup.
  Sessions left `status='open'` by a killed process are surfaced
  with three actions: *Compile it* / *Keep for later* / *Delete*.
- **Purge** — tray menu purge command, plus a 7-day retention
  purge at startup. Per-session delete is also available.

### 🐛 Bug fixes

- **OBS-0 — VAD is now actually instantiated.** Until v0.4.0,
  `AudioCapture.__init__` accepted an optional `VAD` but no caller
  ever passed one. The `agentvoca-vad` worker thread from R2 was
  never started, and `app.mode: auto_stop` **silently never
  auto-stopped** — only `max_recording_duration_s` terminated a
  recording. OBS-0 wires a VAD into the audio pipeline when
  `audio.vad_enabled` is true (the default).

### 🔧 Technical details

#### Threading model
Observer adds six threads while a session is active, all
daemon, all joined with a timeout in
`ObserverController.shutdown()`. Zero extra threads when no
session is running. Threads: ambient VAD + segmentation, 2 Hz
foreground trigger poll, pynput mouse listener, screen grab +
dHash, OCR, selection UIA, and the single-writer ObserverStore
thread. The asyncio loop owns compilation; cross-thread entry
is `loop.call_soon_threadsafe` or
`asyncio.run_coroutine_threadsafe`, never raw `asyncio.run`.

#### Storage layout
```
~/.agentvoca/observer/
├── sessions.db           # WAL-mode SQLite, single-writer thread
├── sessions.db-wal       # survives a hard kill mid-session
├── blobs/<uuid>/<ts>-<seq>.jpg
└── exports/<uuid>/
    ├── session.md
    └── session.json
```
The `blob_path` stored in the DB is **relative** so the whole
directory can be relocated. The user-only ACL is hardened on
first `start()` (D12); encryption is explicitly out of scope —
see the privacy section of `docs/observer.md`.

#### Resource budget (acceptance gate)

| Metric | Budget |
|---|---|
| Added idle CPU while a session is open | < 5 % on a 4-core laptop |
| Added RSS while a session is open | < 400 MB |
| Sustained keyframes | ≤ 4 / minute |
| Audio callback p99 | unchanged (< 5 ms) |
| Disk per hour, typical | < 40 MB |

If a track cannot hold its share of this budget, the right
response is to reduce the capture rate — not to exceed the
budget.

### 📦 Dependency additions

- `rapidocr-onnxruntime` (Track 2) — rides the `onnxruntime`
  already present via `silero-vad`; ships det+rec ONNX models.
  Environment marker Windows-friendly; macOS/Linux can still
  install but `ocr.provider: rapidocr` will not load there.
- `comtypes` (Track 2) — Windows UI Automation client for
  read-only `TextPattern` selection capture. Windows-only
  install marker.

Both are imported lazily through the registry's
`"module:Class"` dotted-path mechanism (R14), so a user with
Observer disabled never imports them.

### ⚠️ Privacy disclosure (verbatim, do not soften)

The session archive — transcripts, OCR text, window titles, and
screenshot JPEGs — sits in **plaintext** under
`~/.agentvoca/observer/`, protected only by a user-only Windows
ACL. That defends against other user accounts on the same
machine. It does **not** defend against malware running as the
user, a stolen unencrypted drive, or a backup tool that sweeps
the home directory. Users who need that should enable
BitLocker/FileVault, or keep `retention_days` low.

Ambient microphone capture can record other people's voices.
Some jurisdictions require all-party consent. The app does not
attempt to give legal advice or geo-detect.

### 📦 Migration

A v0.3.6 `config.yaml` without an `observer:` block loads
unchanged; `observer.enabled` defaults to `false`. To opt in,
add an `observer:` block (or use the new **Observer** tab in the
Settings window) and bind the two new hotkeys (or use the tray
menu).

### 🛠 Known issues

- **macOS / Linux:** UIA selection reading and window-rect
  capture are Win32; on macOS / Linux the selection reader and
  screen grabber degrade to no-ops. Audio + app-name timeline
  still work. Parity targeted for v0.4.1.
- **D9 flag to owner:** the four keyframe triggers ship by
  default, including `speech_onset`. If the owner prefers to
  default it off, set `observer.triggers.speech_onset: false`
  in the default config.

### 📚 Documentation

- [docs/observer.md](observer.md) — full user-facing guide
- [docs/config-reference.md](config-reference.md) — every
  `observer.*` key with type, default, constraint
- [docs/performance.md](performance.md) — Observer resource
  budget and tuning knobs
- [examples/config.observer.yaml](../examples/config.observer.yaml)
  — a complete, working, fully-offline Observer config
