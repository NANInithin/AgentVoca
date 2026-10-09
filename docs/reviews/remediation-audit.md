# Review remediation audit

This tracks every explicitly enumerated finding in the two supplied reviews.
The reviews overlap, and several condensed bullets contain multiple defects; 118 is a
count of cited entries, not a count of distinct root causes. The second review's summary
table reports 19 HIGH items, while its detailed list actually contains H1-H25.

**Status:** 111 entries have code fixes and automated verification; 6 have code fixes
but still need live desktop/device smoke; R18 is partially fixed and blocked on the
retention deletion policy. Automated verification covers the repository suite, not
live microphone, Windows UI Automation, Electron, or macOS behavior.

## Entry checklist

- [ ] **R01** (first review): Exclusion is checked only for keyframe requests. It writes pause markers but never pauses SessionManager or gates ambient ASR, so excluded-app speech can be stored; with triggers off, exclusion is never polled. **[CODE FIXED - live smoke pending]**
- [ ] **R02** (first review): A focus_change row with an excluded title is written before exclusion is checked. A queued grab can complete after switching to an excluded window. **[CODE FIXED - live smoke pending]**
- [x] **R03** (first review): OCR futures are untracked. Stop immediately loads and exports the bundle; late OCR patches SQLite after JSON/Markdown are frozen. Shutdown can cancel compilation. **[CODE FIXED - automated checks]**
- [x] **R04** (first review): Save and Apply are disabled while controller is clean; page edits do not update it or button state until clicked. Closing may silently discard visible edits. Reproduced offscreen: changing language left Save disabled and is_dirty false. **[CODE FIXED - automated checks]**
- [x] **R05** (first review): Shallow section merge plus partial nested dictionaries resets unexposed fields, including storage.dir, screen settings, selection.enabled, and compile.output_dir. Reproduced offscreen: custom storage dir reverted to default after page save. **[CODE FIXED - automated checks]**
- [x] **R06** (first review): Exhausted retries emit an error but return normally; pipeline continues with an empty transcript and can publish insertion success. **[CODE FIXED - automated checks]**
- [x] **R07** (first review): apply_config_update never stores new_config. Constant is_hot_field checks rebuild providers on every save and instantiate commands/adaptive even when disabled; context and vision hot behavior remain stale. Observer hot fields are classified but not applied. **[CODE FIXED - automated checks]**
- [x] **R08** (first review): Multiline/non-ASCII paste returns before clearing prior _last_text. Undo can backspace the previous insertion length in the current target; partial keyboard failure followed by fallback is also unsafe. **[CODE FIXED - automated checks]**
- [x] **R09** (first review): Rules cleanup ignores preserve_code and collapses all whitespace, destroying Markdown tables and code blocks. Reproduced: a three-line table became one line. **[CODE FIXED - automated checks]**
- [x] **R10** (first review): The provider emits one full final segment, which alone starts pipelined cleanup. The pipeline checks cleaned segments before awaiting that task; if it completes first, full text is cleaned twice and joined twice. **[CODE FIXED - automated checks]**
- [x] **R11** (first review): Stop schedules a later finalizer that reads mutable _audio_buffer. A quick new recording resets the buffer before the old stop consumes it. **[CODE FIXED - automated checks]**
- [x] **R12** (first review): Ambient work already running is not preempted by dictation, so both may call one provider concurrently. Queued ambient results lack session identity and may be recorded in a later session. **[CODE FIXED - automated checks]**
- [x] **R13** (first review): Store.start ignores initialization barrier failure. A writer can die while marked started, and main does not isolate store construction/start/purge failure from the dictation app. **[CODE FIXED - automated checks]**
- [x] **R14** (first review): Recovery callbacks defined inside a loop close over session and dialog. With multiple unfinished sessions, buttons can act on the final loop item. **[CODE FIXED - automated checks]**
- [x] **R15** (first review): Open last session and Delete all sessions are visible but _emit_observer_action deliberately does nothing for them; main has no separate wiring. **[CODE FIXED - automated checks]**
- [x] **R16** (first review): clear drops queued shots but not an in-flight worker, so an old shot may enter a new dictation. Failed extractions are compacted before anchor matching, shifting later images to earlier anchors. **[CODE FIXED - automated checks]**
- [x] **R17** (first review): The orchestrator publishes ObserverUtteranceEvent on primary insertion, but no production subscriber records it as utterance_dictated. Dictated speech is absent from Observer DB and sidecar. Clipboard fallback also omits the event. The existing integration test asserts event publication only. **[CODE FIXED - automated checks]**
- [ ] **R18** (first review): Sidecar duration uses first-to-last event rather than session open/close. Retention never purges open sessions, allows 0 to disable purge, and deletes store.exports rather than a custom compile.output_dir. **[PARTIAL - duration fixed; retention and custom-export deletion need explicit approval]**
- [x] **R19** (first review): Indicator starts/stops QTimer and hides itself in callbacks that can run on a hotkey thread. Its timer also overwrites PAUSED with REC. **[CODE FIXED - automated checks]**
- [x] **R20** (first review): Schema accepts F13–F24 but translator maps only F1–F12. **[CODE FIXED - automated checks]**
- [ ] **R21** (first review): Config accepts 8–48 kHz and stereo, but VAD does not resample and ASR/VAD flatten interleaved stereo as mono. **[CODE FIXED - live smoke pending]**
- [x] **R22** (first review): Case-insensitive regex lowercases a match but looks it up in the original mapping; uppercase configured triggers fail. The editable inline snippets table is never persisted. Reproduced: BRB remained BRB. **[CODE FIXED - automated checks]**
- [ ] **R23** (first review): Config/UI offer ocr_rect, but main constructs NoopSelectionReader except for Windows uia. The fallback is unavailable. Actual UIA COM behavior still needs live Windows validation. **[CODE FIXED - live smoke pending]**
- [x] **R24** (first review): Use defaults advances only one wizard page despite promising a jump to review. Restart now quits without relaunch. Context screen/clipboard switches are exposed without a runtime reader. **[CODE FIXED - automated checks]**
- [x] **R25** (first review): YAML config writes directly to its public path and can be truncated by interruption. Observer's nominal read-only connection opens the DB path without mode=ro. **[CODE FIXED - automated checks]**
- [x] **C1** (second review): Recovery-dialog closures act on the wrong session — `main.py:71` **[CODE FIXED - automated checks]**
- [x] **C2** (second review): Observer store `start()` ignores writer-thread init failure — `observer/store.py:193` **[CODE FIXED - automated checks]**
- [x] **C3** (second review): New recording can strand the in-flight pipeline and insert the next dictation twice — `core/orchestrator.py:1084` **[CODE FIXED - automated checks]**
- [ ] **C4** (second review): Excluded apps are recorded to the session archive — `observer/triggers.py:346` + `main.py` ambient wiring **[CODE FIXED - live smoke pending]**
- [x] **C5** (second review): Settings window can never save — `setup/settings_window.py:154` **[CODE FIXED - automated checks]**
- [x] **C6** (second review): Any settings save silently resets Observer storage paths and re-enables selection capture — `setup/pages/observer_page.py:281` **[CODE FIXED - automated checks]**
- [x] **H1** (second review): `apply_config_update` never stores `new_config` **[CODE FIXED - automated checks]**
- [x] **H2** (second review): WB-04 pipelined cleanup is inert and doubles cleanup cost **[CODE FIXED - automated checks]**
- [x] **H3** (second review): Blocking `WhisperModel` loads on the event loop **[CODE FIXED - automated checks]**
- [x] **H4** (second review): `stop_recording`/`cancel_recording` non-atomic check-then-set **[CODE FIXED - automated checks]**
- [ ] **H5** (second review): UIA selection capture cannot work against real comtypes **[CODE FIXED - live smoke pending]**
- [x] **H6** (second review): One hung UIA call permanently jams the single-worker executor **[CODE FIXED - automated checks]**
- [x] **H7** (second review): LLM compiler degraded-fallback calls a non-existent method **[CODE FIXED - automated checks]**
- [x] **H8** (second review): Lenient loader sentinel misses Observer providers **[CODE FIXED - automated checks]**
- [x] **H9** (second review): Rules cleanup (default provider) mangles dictation **[CODE FIXED - automated checks]**
- [x] **H10** (second review): Failed keyboard insert leaves `_last_text` set → undo deletes the user's own text **[CODE FIXED - automated checks]**
- [x] **H11** (second review): Clipboard delegation never updates `_last_text` → undo removes the wrong text **[CODE FIXED - automated checks]**
- [x] **H12** (second review): `insert_last_transcript` hotkey registered but unhandled **[CODE FIXED - automated checks]**
- [x] **H13** (second review): `open_settings` hotkey creates Qt widgets on the pynput thread **[CODE FIXED - automated checks]**
- [x] **H14** (second review): Tray "Open last session…" / "Delete all sessions…" are dead items **[CODE FIXED - automated checks]**
- [x] **H15** (second review): Observer badge stuck showing "REC 0:00:00" after session end **[CODE FIXED - automated checks]**
- [x] **H16** (second review): Pause badge overwritten by "REC elapsed" after one second **[CODE FIXED - automated checks]**
- [x] **H17** (second review): AmbientListener state machine not reset on stop **[CODE FIXED - automated checks]**
- [x] **H18** (second review): Settings `closeEvent` silently discards typed edits **[CODE FIXED - automated checks]**
- [x] **H19** (second review): "Restart now" quits but never relaunches **[CODE FIXED - automated checks]**
- [x] **H20** (second review): Four hotkey presets are invalid per the repo's own validators **[CODE FIXED - automated checks]**
- [x] **H21** (second review): "(disabled)" preset offered for required hotkeys **[CODE FIXED - automated checks]**
- [x] **H22** (second review): `update_section` strict re-validation crashes wizard/settings save **[CODE FIXED - automated checks]**
- [x] **H23** (second review): Shared custom-hotkey textbox corrupts both custom hotkeys **[CODE FIXED - automated checks]**
- [x] **H24** (second review): Snippet table input silently discarded **[CODE FIXED - automated checks]**
- [x] **H25** (second review): `language_hint` never saved in local ASR mode **[CODE FIXED - automated checks]**
- [x] **M01** (second review): `orchestrator.py:731` — newline/paragraph command inserts are fire-and-forget tasks racing the main insertion (clipboard + shared executor; ordering arbitrary). Await inline. **[CODE FIXED - automated checks]**
- [x] **M02** (second review): `orchestrator.py:673` — command-only dictations ("scratch that") leave the state machine stuck in "cleaning"; overlay/tray desync until the next full pipeline. **[CODE FIXED - automated checks]**
- [x] **M03** (second review): `orchestrator.py:1337` — `apply_config_update` ignores enabled flags: disabling commands/adaptive keeps them running (adaptive keeps writing the learned-vocab file — a privacy toggle that silently no-ops); enabling context at runtime does nothing. **[CODE FIXED - automated checks]**
- [x] **M04** (second review): `orchestrator.py:1231` — `_transition_or_emit_error` never transitions to "error" → the 5 s recovery timer is dead code; UI stuck mid-pipeline on errors. **[CODE FIXED - automated checks]**
- [x] **M05** (second review): `orchestrator.py:431` — adaptive correction compares post-cleanup text against raw transcripts; mappings can never match with reformatting cleanup providers (adaptive vocab effectively broken unless `cleanup.provider: none`). Also `orchestrator.py:764-782` passes whole sentences as wrong/right instead of diffing terms — after 3 undoes a whole-sentence mapping is promoted. **[CODE FIXED - automated checks]**
- [x] **M06** (second review): `orchestrator.py:956` — `ObserverUtteranceEvent` not published on the clipboard-fallback path → dictations missing from Observer sessions. **[CODE FIXED - automated checks]**
- [x] **M07** (second review): `orchestrator.py:589` [SUSPECTED] — no reentrancy guard on `_run_pipeline`; overlapping dictations share mutable pipeline state. **[CODE FIXED - automated checks]**
- [x] **M08** (second review): `registry.py:100` — `observer/ocr/` and `observer/selection/` have no `__init__.py`; setuptools `find_packages` drops them → lazily-imported dotted paths raise `ModuleNotFoundError` in packaged builds (works only under editable install). **[CODE FIXED - automated checks]**
- [x] **M09** (second review): `event_bus.py:81` — exceptions from cross-thread async handlers vanish entirely (discarded concurrent future never logs at GC). `:84` — `asyncio.run()` fallback blocks the publisher thread and kills spawned tasks. `:77` — in-loop `create_task` result dropped (GC hazard). **[CODE FIXED - automated checks]**
- [x] **M10** (second review): `main.py:273` — ASR arbiter queue depth wired to `observer.ocr.max_queue` (wrong field; couples ambient drop behavior to OCR tuning). **[CODE FIXED - automated checks]**
- [x] **M11** (second review): `main.py:356` [SUSPECTED] — exclusion `pause_start` row stores the matched pattern itself — leaks an identity fragment of the excluded app into the archive. **[CODE FIXED - automated checks]**
- [x] **M12** (second review): `tray.py:325` — elapsed tooltip QTimer started/stopped from the pynput thread → never updates for hotkey sessions. **[CODE FIXED - automated checks]**
- [x] **M13** (second review): `store.py:205` — `stop()` timeout path nulls `_conn`/`_writer` under a live writer → later jobs fail an assert and drop silently; restart spawns a second writer on the same queue. **[CODE FIXED - automated checks]**
- [x] **M14** (second review): `store.py:688` — "read-only" connections opened read-write (`uri` lacks `file:` prefix + `mode=ro`); `_ro_conn_uri` is dead code. **[CODE FIXED - automated checks]**
- [x] **M15** (second review): `controller.py:147` + `session.py:65` — lifecycle unsynchronized across pynput/Qt threads: double-open leaves a phantom `status='open'` session that re-prompts on every launch and is never purged; double-stop runs two concurrent compiles over the same exports. Add a `threading.Lock`. **[CODE FIXED - automated checks]**
- [x] **M16** (second review): `store.py:403` [SUSPECTED] — session open/close block the hotkey listener thread behind 5 s store barriers → all hotkeys (incl. dictation) delayed up to 5 s when the writer stalls. **[CODE FIXED - automated checks]**
- [x] **M17** (second review): `audio.py:294` — boundary block duplicated when `max_utterance_ms` splits an utterance → duplicated words across split segments. **[CODE FIXED - automated checks]**
- [x] **M18** (second review): `audio.py:150` [SUSPECTED] — no sample-rate validation; silero supports only 8/16 kHz. At 48 kHz the VAD errors→"assume speech"→SPEAKING permanently → continuous garbage segments to ASR. **[CODE FIXED - automated checks]**
- [x] **M19** (second review): `arbiter.py:134` [SUSPECTED] — dictation can run concurrently with an in-flight ambient transcription (idle event only gates un-started jobs) → dictation latency inflated by Observer work. **[CODE FIXED - automated checks]**
- [x] **M20** (second review): `arbiter.py:173` — dropped ambient jobs never surfaced (submit returns True; `dropped_count` has zero consumers; no `gap` event) → silent data loss + dishonest timeline. **[CODE FIXED - automated checks]**
- [x] **M21** (second review): `audio.py:157` + `screen.py:143` [SUSPECTED] — stop() lifecycle: stale sentinel kills the next session's worker; join-timeout spawns duplicate workers racing shared state. **[CODE FIXED - automated checks]**
- [x] **M22** (second review): `rapidocr.py:41` — `_engine_lock` created but never acquired; engine can be built twice under unbounded concurrent OCR jobs (2x memory/CPU spike). **[CODE FIXED - automated checks]**
- [x] **M23** (second review): `export/base.py:46` — exporters do blocking `fsync` + full-session payload build on the shared dictation event loop. **[CODE FIXED - automated checks]**
- [x] **M24** (second review): `windows_uia.py:110` [SUSPECTED] — comtypes imported on the capture worker thread (the exact hang the comment claims to prevent; `is_available()` never called from main thread). **[CODE FIXED - automated checks]**
- [x] **M25** (second review): `compile/base.py:108` — a pause >5 min makes `pause_end` open a new block (`None==None` + delta) — contradicts the docstring; renders "unknown" headers. **[CODE FIXED - automated checks]**
- [x] **M26** (second review): `compile/openai_compatible.py:75` — per-block char budget bypassed by a single large event (100k-char selection ≈ 12x budget) → context overflow / cost blowup. **[CODE FIXED - automated checks]**
- [x] **M27** (second review): `compile/openai_compatible.py:282` — LLM response missing `SUMMARY:` marker is misflagged degraded; if all blocks omit it, the session summary call is skipped entirely. **[CODE FIXED - automated checks]**
- [x] **M28** (second review): `json_sidecar.py:133` — sidecar emits `pause_end` gap entries the rules compiler does not; inconsistent reason scheme between the two artifacts. **[CODE FIXED - automated checks]**
- [x] **M29** (second review): `faster_whisper.py:345,519,533` — CUDA-recovery resets reload the accurate model but never the streaming model → streaming partials silently dead after one CUDA failure. **[CODE FIXED - automated checks]**
- [x] **M30** (second review): `vad.py:111` — docstring promises resampling; none exists. Non-16 kHz config → VAD warning every 64 ms, auto-stop silently disabled app-wide. **[CODE FIXED - automated checks]**
- [x] **M31** (second review): `vad.py:101` — stereo (`channels=2`) fed interleaved to VAD/ASR; the mono-mix branch is dead code (`np.frombuffer` on bytes is always 1-D) → corrupted transcripts. **[CODE FIXED - automated checks]**
- [x] **M32** (second review): `capture.py:96` [SUSPECTED] — VAD queue depth (~4.1 s) vs 900 ms silence timeout; stale silence can auto-stop mid-utterance on loaded machines. **[CODE FIXED - automated checks]**
- [x] **M33** (second review): `schema.py:510` — `compile.output_dir` ""-sentinel resolved in-place on load; first save pins a concrete path; changing `storage.dir` later never moves exports. **[CODE FIXED - automated checks]**
- [x] **M34** (second review): `cleanup/openai_compatible.py:32` — no endpoint → silently POSTs transcripts to `api.openai.com` unconfigured (401 x retries) — offline-by-default violation. **[CODE FIXED - automated checks]**
- [x] **M35** (second review): `schema.py:230` — `commands.phrases` action values unvalidated; a typo'd action matches the phrase then discards the transcript. **[CODE FIXED - automated checks]**
- [x] **M36** (second review): `schema.py:108` — provider names never validated at load (comment claims they are); typo'd provider → unhandled `ProviderNotFoundError` traceback at `Orchestrator()` construction (outside try). **[CODE FIXED - automated checks]**
- [x] **M37** (second review): `clipboard.py:85` + `keyboard.py:137` — `undo_last` fires Ctrl+Z/backspaces even when nothing was ever inserted → undoes the user's own last action in the focused app. **[CODE FIXED - automated checks]**
- [x] **M38** (second review): `context/active_app.py:101` — inverted tuple when `OpenProcess` fails (elevated windows): window title reported as app name → wrong cleanup-style profile matches; title surfaces as "app name". **[CODE FIXED - automated checks]**
- [x] **M39** (second review): `vocab/snippets.py:151` — snippet keys stored as written but looked up lowercased → any uppercase trigger never expands. **[CODE FIXED - automated checks]**
- [x] **M40** (second review): `capture/screenshot.py:217` — identical consecutive snips silently dropped (signature equals the pre-snip clipboard baseline; Snip & Sketch leaves the prior capture) → 30 s hang, second screenshot lost. **[CODE FIXED - automated checks]**
- [x] **M41** (second review): `capture/screenshot.py:246` — `clear()` doesn't cancel in-flight captures → a capture from dictation N splices into dictation N+1's transcript. **[CODE FIXED - automated checks]**
- [x] **M42** (second review): `keyboard.py:80` + `clipboard.py:64` — every non-ASCII/multiline dictation (and every newline voice command) destroys the user's clipboard with no snapshot/restore. **[CODE FIXED - automated checks]**
- [x] **M43** (second review): `utils/logging.py:24,53` — log-dir `mkdir` outside try/except; raw `OSError` crashes startup on locked-down machines before the wizard can run (docstring promises `ConfigError`). **[CODE FIXED - automated checks]**
- [x] **M44** (second review): `vision/anchors.py:91` — global blank-line collapse mangles extracted code (PEP 8 two-blank-lines → one) — violates the `preserve_code` contract. **[CODE FIXED - automated checks]**
- [x] **M45** (second review): `utils/logging.py:70` — structlog `ConsoleRenderer` + stdlib handlers → double-formatted log lines with raw ANSI color codes in `agentvoca.log`. **[CODE FIXED - automated checks]**
- [x] **M46** (second review): `wizard.py:54` — `page.isComplete = widget.is_complete` attribute assignment never overrides the C++ virtual in PySide6 → FinishPage validation dead (save-time check still blocks invalid configs). **[CODE FIXED - automated checks]**
- [x] **M47** (second review): `persistence.py:125,63,105` — backup/parent-dir/read run outside the OSError→ConfigError try; a raw `OSError` escapes `save()` (which catches only `ConfigError`) → save click silently does nothing. **[CODE FIXED - automated checks]**
- [x] **M48** (second review): `env_helper.py:72` — PowerShell snippet doesn't escape `$` → API keys containing `$` silently corrupted when pasted (double-quote interpolation). **[CODE FIXED - automated checks]**
- [x] **M49** (second review): `welcome.py:128` — "Use defaults" advances one page instead of jumping to finish (docstring promises the jump). **[CODE FIXED - automated checks]**
- [x] **M50** (second review): `welcome.py:84` — auto-open checkbox hardcoded True; never loaded from `state.json`. **[CODE FIXED - automated checks]**
- [x] **M51** (second review): `asr_page.py:307` — custom local model ids (e.g. `distil-large-v3`) silently coerced to a preset on the next save → user's model choice destroyed. **[CODE FIXED - automated checks]**
- [x] **M52** (second review): `advanced_page.py:168` — vision env-helper dialog missing the `env_var_changed` connection → renamed env var never persists (asr/cleanup pages have it). **[CODE FIXED - automated checks]**
- [x] **L01** (second review): `orchestrator.py:270` — `stop()` never cancels `_pipeline_task`; parked pipeline can run against shut-down providers. `:258` — warm-up task unreferenced (GC hazard). `:1030` — `segment_index` never incremented for finals. **[CODE FIXED - automated checks]**
- [x] **L02** (second review): `state_machine.py:248` — `transitioned` computed after mutation; comparison always False (latent). `event_bus.py:88` — `handler.__name__` can raise inside except. `:61` — handler list iterated live (shutdown-window skips). `async_loop.py:78` — stop() logs success unconditionally; double-stop truncates drain. **[CODE FIXED - automated checks]**
- [x] **L03** (second review): `main.py:1043` — pipeline build failure exits code 1 with zero user notification. `:721` — repeated open_settings drops the previous window mid-edit (GC) and stacks `config_saved` connections. `hotkeys.py:143` — listener TOCTOU; no duplicate-binding validation. `overlay.py:205` — warm-up `singleShot` can hide the overlay mid-recording. **[CODE FIXED - automated checks]**
- [x] **L04** (second review): `controller.py:270` — `_await_on_loop` drops the task ref (GC). `:232` — `_schedule_compile` leaks an un-awaited coroutine when the loop is closed. `:295` — `load_bundle` outside try; future discarded → compile failures invisible. **[CODE FIXED - automated checks]**
- [x] **L05** (second review): `triggers.py:133,359,339` — counter races outside locks; scroll-settle reset can erase a fresh scroll; transient detect failures produce spurious focus rows. `screen.py:172,239` — counter races. **[CODE FIXED - automated checks]**
- [x] **L06** (second review): `faster_whisper.py:314` — `np.frombuffer` outside try violates the `ASRError` contract. `asr/openai_compatible.py:127` — `extra` forwarded verbatim as multipart fields (provider-local keys break strict endpoints). `capture.py:163` — stop() join timeout orphans the VAD worker; stale sentinel. `:236` — flush-before-publish ordering comment is false. **[CODE FIXED - automated checks]**
- [x] **L07** (second review): `loader.py:118` — lenient path double env-var expansion. `schema.py:200` — optional-hotkey errors name the wrong field. **[CODE FIXED - automated checks]**
- [x] **L08** (second review): `clipboard.py:42` — `is_available()` wipes the clipboard (latent). `platform/windows.py:57` — `focus_window` returns True without checking BOOL returns → undo can type into the wrong window. `platform/macos.py:41` — `paste_modifier_key()` returns invalid "cmd". `profiles.py:40` — fallback style bypasses `_VALID_STYLES`. `vocab/adaptive.py:61` — case-variant re-correction appends duplicate mapping lines. **[CODE FIXED - automated checks]**
- [x] **L09** (second review): `logging.py:60` — handler-removal comment false; re-init duplicates handlers. `:23` — env var `agentvoca_LOG_DIR` casing bug. `vision/openai_compatible.py:34,131,141` — "available" with unconfigured default endpoint; `extra` passthrough can break the request contract. **[CODE FIXED - automated checks]**
- [x] **L10** (second review): `wizard.py:161` — teardown guard wrong for reject path. `persistence.py:104` — `save_to_disk_preserving` shallow merge destroys the nested `extra:` blocks it exists to protect (dead code). `first_run.py:138` — `config_exists()` lies when `AGENTVOCA_CONFIG` set (dead code). `config_controller.py:198` — restart_paths disagrees with partition. `restart_policy.py:117` — `vision.extra` unclassified. `model_catalog.py:180` — fire-and-forget fetch, docstring mis-states delivery thread. `app_basics.py:62`/`cleanup_page.py:261` — schema-valid "custom" values coerced on save. `audio_page.py:63` — PortAudio re-probe blocks the GUI thread at every page entry. `asr_page.py:232` — in-flight fetch emits on possibly-destroyed page. `welcome.py:85` — auto-open checkbox writes state.json even if the wizard is cancelled. **[CODE FIXED - automated checks]**

## Remaining verification and decision

- R01/R02/C4: On a real desktop, switch into and out of an excluded window
  during ambient speech, dictation, selection, a queued grab, and OCR. Inspect SQLite,
  blobs, and remote request logs for excluded content.
- R21: Confirm 16 kHz mono capture with a real 16/44.1/48 kHz input device.
- R23/H5: Smoke native Windows and Electron selection through real comtypes/UIA.
- R18: The sidecar duration is corrected. Automatic purging of stale open sessions
  and deletion of artifacts in a custom compile.output_dir were rejected by
  automatic approval review because they broaden irreversible deletion. The existing
  retention behavior remains until the user explicitly approves that scope.

The second review also lists observations outside its numbered findings. The streaming
chunker now caps its stalled-loop buffer at 16 MiB and uses the complete recording for
final batch ASR if that cap is reached. OCR and compile provider lifecycles are driven
at startup/shutdown; the OCR queue is bounded. The never-used `VADSpeechEvent` is a
redundant event contract, with no identified user-facing failure. The absence of
ObserverPage from the first-run wizard is consistent with Observer being opt-in in
Settings. `mark_abandoned` and stale open-session retention remain part of R18.

## Automated evidence

- Final offscreen run: `874 passed, 4 skipped`; Ruff passed.
- Focused tests cover config persistence, Observer privacy/export, ASR arbitration,
  clipboard preservation, selection UIA fakes, and insertion/undo.
- See current test output for the exact passing count; live OS and API behavior
  cannot be inferred from these tests.
