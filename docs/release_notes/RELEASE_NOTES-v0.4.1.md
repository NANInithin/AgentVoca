# AgentVoca v0.4.1 — Reliability and review fixes

**Released:** 2026-10-09

**Version:** 0.4.1

This patch release addresses the two v0.4.0 code reviews. The
[remediation audit](../reviews/remediation-audit.md) tracks all 118 explicitly listed
review entries, including overlaps and compound findings. Agent mode remains planned
for v0.5.0.

## Fixes

- **Observer privacy and integrity:** Excluded foreground apps gate ambient speech,
  dictation events, selection, keyframes, and OCR work. Queued work is discarded on
  exclusion transitions. Dictated speech reaches the session database and sidecar.
  OCR and compilation futures are tracked and drained before export.
- **Observer reliability:** Store startup errors surface instead of silently dropping
  events. Session start and stop no longer block hotkey handling on store barriers.
  Ambient and dictation ASR access is coordinated, with session identity and reported
  queue drops. UIA selection handling and worker timeout recovery were corrected.
- **Dictation and insertion:** ASR exhaustion cannot insert an empty transcript;
  overlapping recordings and stop races no longer reuse pipeline state. Undo tracks
  committed text. Clipboard paste snapshots all MIME formats and restores them if
  the user has not copied something else. Structured code and tables survive cleanup.
- **Settings and configuration:** Save and Apply respond to edits; nested settings
  survive round trips; writes are atomic. Hot changes are applied only where supported,
  and other changes prompt for a real restart. Invalid provider names, command actions,
  duplicate hotkeys, and unsupported audio formats fail validation clearly.
- **Desktop and packaging:** Observer badge and tray updates use the GUI thread.
  Lazily imported Observer packages are included in installed packages and the frozen
  build. Streaming audio memory is bounded, with complete-audio ASR fallback if its
  buffer cap is reached.

## Configuration changes

- Audio input is limited to 16 kHz mono, the format supported by the current VAD and
  ASR path. Choose another device if an existing device cannot provide it.
- `selection.method: ocr_rect` was removed because that fallback was not implemented.
- Unsupported screen and clipboard context switches are rejected rather than displayed
  as working options.
- OpenAI-compatible ASR and vision adapters forward only supported request options
  from `extra`; local-provider options and core request fields are ignored.

## Verification and limits

The offscreen test suite passed **874 tests** with **4 skipped** on Windows. Ruff lint
and formatting checks passed. These tests do not replace live microphone, native
Windows/Electron selection, macOS, or excluded-app transition smoke tests. The
remediation audit identifies six review entries whose code fixes still need those
desktop checks.

The sidecar duration from R18 is corrected. Automatic purging of stale open sessions
and deletion of artifacts in a custom `compile.output_dir` are **not included**:
automatic approval review rejected the broader irreversible deletion. Existing
retention behavior remains in place pending explicit approval of that scope.

On macOS and Linux, UIA selection and Windows active-window rectangle capture remain
unavailable, as in v0.4.0.
