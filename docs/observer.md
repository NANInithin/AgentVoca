# Observer Mode

Observer mode records a working session — what you said, what was on
screen, what you highlighted, what app you were in — and compiles it
at the end into a readable markdown document plus a machine-readable
JSON sidecar.

> **Agent mode is NOT in this release.** It is v0.5.0. Observer's
> JSON sidecar is the contract Agent will consume; nothing in
> Observer executes a task, writes a file on your behalf, or calls
> a tool.

---

## 1. How it works

A session is a contiguous recording period. You start a session with
the **Toggle Observer** hotkey, work normally, and stop with the
same hotkey. The session is compiled into a markdown document and a
JSON sidecar, both written to `~/.agentvoca/observer/exports/`.

| What gets captured | How | When |
|---|---|---|
| Spoken lines (ambient) | Tap on the existing mic stream + VAD utterance segmentation + the **already-configured** ASR provider | Continuously during a session |
| Spoken lines (dictated) | The dictation hotkey is reused; the dictated transcript also lands in the log as `utterance_dictated` | On every dictation during a session |
| Screenshots (keyframes) | 4 trigger sources → rate-limited → active-window grab → perceptual-hash dedup | At meaningful moments (see §3) |
| OCR text from screenshots | RapidOCR (ONNX) local provider; optional `openai_compatible` VLM escalation | Asynchronously after each keyframe |
| Highlighted text | Windows UI Automation `TextPattern`, read-only, **never touches the clipboard** | On every selection |
| Focus changes | 2 Hz foreground poll, cheap `ctypes` calls only | Throughout a session |
| Pause / resume | Per-foreground-app / per-window-title exclusion list, plus a hotkey | When the foreground matches the exclusion list or the user pauses |

The session compiles into a markdown document and a JSON sidecar
when you stop recording. Compiling is a deterministic rules render
by default; an LLM-backed compiler is available for users who want
narrative summaries (see §5).

---

## 2. Session lifecycle

1. **Toggle** the Observer hotkey to start a session. The tray icon
   turns red and a non-dismissable badge appears in the top-left of
   the screen.
2. **Work normally.** Ambient audio, keyframes, selections, and
   focus changes are recorded in the background.
3. **Pause** with the pause hotkey to suspend capture (e.g. when
   you open a password manager). A `pause_start` / `pause_end` pair
   is recorded in the log; nothing is captured during the pause.
4. **Toggle** again to stop the session. Compilation begins on the
   asyncio loop thread. When it finishes, the tray icon returns to
   idle and a notification with the output paths is shown.
5. **Open** the output. The markdown is the readable document; the
   JSON is the v0.5.0 Agent contract.

The session DB is at `~/.agentvoca/observer/sessions.db`. Blobs
(JPEG screenshots) live in `~/.agentvoca/observer/blobs/<session-uuid>/`.
Exports land in `~/.agentvoca/observer/exports/<session-uuid>/`.

---

## 3. The four keyframe triggers

Each trigger source is individually toggleable. The token bucket
(`observer.triggers.max_keyframes_per_min`, default 4/min) and the
minimum interval (`observer.triggers.min_interval_ms`, default 4 s)
hold the per-minute keyframe count within the resource budget.

| Trigger | Default | What it does |
|---|---|---|
| `window_change` | on | A new foreground window came to focus. |
| `scroll_settle` | on | The window scrolled and then settled for `scroll_settle_ms` (default 600 ms). |
| `click_selection` | on | The user released a click or finished selecting text. |
| `speech_onset` | on | Ambient VAD detected speech onset. This is the trigger that grounds an utterance to a screen. |

`speech_onset` is the most valuable trigger for the v0.5.0 Agent
(D9). It is on by default. If you find that the keyframe rate is
too high, the right knob to turn is `max_keyframes_per_min` or
`min_interval_ms`, not a trigger.

---

## 4. Privacy, consent, and what Observer does and does not protect

### Ships in v0.4.0

1. **Off by default.** `observer.enabled: false`. Nothing records
   until you turn it on *and* explicitly start a session.
2. **Persistent visible indicator.** Tray icon state + a
   non-dismissable overlay badge for the entire session. You can
   never forget it is on.
3. **Exclusion list.** Foreground app glob + window-title pattern.
   When excluded: no keyframe, no OCR, no selection. Ambient audio
   is also suspended — an excluded app is excluded, not partially
   excluded. A `pause_start` / `pause_end` pair records the gap
   honestly.
4. **Pause / resume hotkey.** Instant suspend without ending the
   session.
5. **Purge.** Tray → *Observer* → *Delete all sessions…*, plus
   per-session delete. Removes DB rows, blobs, and exports.
6. **Retention.** Sessions older than `retention_days` (default 7)
   are purged at startup. Set to `0` to disable.
7. **Local by default.** With `ocr.provider: rapidocr` and
   `compile.provider: rules`, **nothing leaves the machine.**
   Choosing an `openai_compatible` OCR or compiler provider sends
   screen content and transcripts to that endpoint — the settings
   UI says so plainly at the point of choice, matching how
   `docs/vision.md` handles it today.

### What D12 (no encryption) means, stated honestly

The session archive — transcripts, OCR text, window titles, and
screenshot JPEGs — sits in **plaintext** under
`~/.agentvoca/observer/`, protected only by a user-only Windows
ACL. That defends against other user accounts on the same
machine. It does **not** defend against malware running as the
user, a stolen unencrypted drive, or a backup tool that sweeps the
home directory. Users who need that should enable
BitLocker/FileVault, or keep `retention_days` low.

### Legal

Ambient microphone capture can record other people's voices. Some
jurisdictions require all-party consent. The app does not attempt
to give legal advice or geo-detect.

---

## 5. Providers

### OCR

| Provider | Local? | Notes |
|---|---|---|
| `rapidocr` | yes (ONNX) | Default. Rides the `onnxruntime` already present via `silero-vad`; ships det+rec ONNX models; ~15 MB. |
| `openai_compatible` | no | Any OpenAI-compatible `/v1/chat/completions` endpoint that accepts an image URL or base64 image. |
| `none` | yes | Disables OCR; keyframes are still stored, just without text. |

### Compiler

| Provider | Local? | Notes |
|---|---|---|
| `rules` | yes | Default. Deterministic, no network. Produces a structured markdown with per-block **Said** / **Highlighted** / **On screen** sections. |
| `openai_compatible` | no | Two-phase rolling summarization: per-block narrative (run in parallel), then a one-paragraph session summary. **Degrades to rules** for any block whose LLM call fails, with `degraded=True` on the result. |
| `none` | yes | Raw chronological dump: one line per event, no grouping. |

---

## 6. Resource budget

| Metric | Budget |
|---|---|
| Added idle CPU while a session is open | < 5 % on a 4-core laptop |
| Added RSS while a session is open | < 400 MB |
| Sustained keyframes | ≤ 4 / minute |
| Audio callback p99 | unchanged (< 5 ms) |
| Disk per hour, typical | < 40 MB |

If a session cannot hold its share of this budget, the right
response is to reduce the capture rate — not to exceed the budget.

---

## 7. Crash recovery

If AgentVoca is killed (process kill, power loss) mid-session, the
session is left with `status='open'` in the DB. On next launch, a
non-modal dialog asks what to do with the recovered session:

> AgentVoca found 1 unfinished Observer session from 28 Jul, 14:02 (1 h 12 m).
> [Compile it] [Keep for later] [Delete]

*Compile it* marks the session `closed` and runs compilation.
*Keep for later* leaves the session `open`; the dialog asks again
next launch. *Delete* purges the session (rows + blobs + exports).

---

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| **Observer captured nothing** | Observer is off, no session was started, or the foreground app is in the exclusion list. | Check `observer.enabled` in the config; toggle the Observer hotkey; check `observer.privacy.exclude_apps`. |
| **OCR text is garbage** | Dark themes and small fonts are hard for RapidOCR. | Raise `observer.screen.max_width_px`, or switch to a cloud VLM provider (`ocr.provider: openai_compatible`). |
| **Highlighting isn't captured in app X** | UIA is unsupported in some apps (Electron, PDF viewers are known-bad). | The OCR-rect fallback is approximate. If you depend on capturing selections in that app, contact support with the app name. |
| **My laptop is warm** | The keyframe rate is too high for the available budget. | Lower `observer.triggers.max_keyframes_per_min` (e.g. 2), raise `observer.triggers.min_interval_ms` (e.g. 8000). |
| **Where are my sessions?** | The storage dir was changed. | Check `observer.storage.dir` (default `~/.agentvoca/observer`). Exports land in `<dir>/exports/<session-uuid>/`. |
| **Compilation says `degraded`** | One or more LLM calls failed during compilation. | The output is still a complete artifact — blocks whose LLM calls failed were rendered with the rules compiler. Check the network and try again. |
| **Cloud warning appears unexpectedly** | A provider was set to `openai_compatible` somewhere. | Check `observer.ocr.provider` and `observer.compile.provider`. |
