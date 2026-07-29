# Graph Report - .  (2026-07-29)

## Corpus Check
- 257 files · ~172,028 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 4160 nodes · 10344 edges · 169 communities (146 shown, 23 thin omitted)
- Extraction: 78% EXTRACTED · 22% INFERRED · 0% AMBIGUOUS · INFERRED: 2286 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11
- Community 12
- Community 13
- Community 14
- Community 15
- Community 16
- Community 17
- Community 18
- Community 19
- Community 20
- Community 21
- Community 22
- Community 23
- Community 24
- Community 25
- Community 26
- Community 27
- Community 28
- Community 29
- Community 30
- Community 31
- Community 32
- Community 33
- Community 34
- Community 35
- Community 36
- Community 37
- Community 38
- Community 39
- Community 40
- Community 41
- Community 42
- Community 43
- Community 44
- Community 45
- Community 46
- Community 47
- Community 48
- Community 49
- Community 50
- Community 51
- Community 52
- Community 53
- Community 54
- Community 55
- Community 56
- Community 57
- Community 58
- Community 59
- Community 60
- Community 61
- Community 62
- Community 63
- Community 64
- Community 65
- Community 66
- Community 67
- Community 68
- Community 69
- Community 70
- Community 71
- Community 72
- Community 73
- Community 74
- Community 75
- Community 76
- Community 77
- Community 78
- Community 79
- Community 80
- Community 81
- Community 82
- Community 83
- Community 84
- Community 85
- Community 86
- Community 87
- Community 88
- Community 89
- Community 90
- Community 91
- Community 92
- Community 93
- Community 94
- Community 95
- Community 96
- Community 97
- Community 98
- Community 99
- Community 100
- Community 101
- Community 102
- Community 103
- Community 104
- Community 105
- Community 106
- Community 107
- Community 108
- Community 109
- Community 110
- Community 111
- Community 112
- Community 113
- Community 114
- Community 115
- Community 116
- Community 117
- Community 118
- Community 119
- Community 120
- Community 121
- Community 122
- Community 123
- Community 124
- Community 125
- Community 126
- Community 127
- Community 128
- Community 129
- Community 130
- Community 131
- Community 132
- Community 133
- Community 134
- Community 135
- Community 136
- Community 137
- Community 138
- Community 139
- Community 140
- Community 141
- Community 142
- Community 143
- Community 144
- Community 145
- Community 146
- Community 147
- Community 148
- Community 149
- Community 150
- Community 151
- Community 152
- Community 153
- Community 154
- Community 155
- Community 156
- Community 157
- Community 158
- Community 159
- Community 160

## God Nodes (most connected - your core abstractions)
1. `EventBus` - 293 edges
2. `FullConfig` - 207 edges
3. `Orchestrator` - 185 edges
4. `ProviderRegistry` - 183 edges
5. `ASRConfig` - 173 edges
6. `CleanupConfig` - 157 edges
7. `InsertionConfig` - 157 edges
8. `ObserverStore` - 148 edges
9. `TranscriptSegment` - 120 edges
10. `RecordingStoppedEvent` - 103 edges

## Surprising Connections (you probably didn't know these)
- `Observer Mode (v0.4.0)` --semantically_similar_to--> `Observer Mode Documentation`  [INFERRED] [semantically similar]
  README.md → docs/observer.md
- `Screenshot-to-Text (v3/v0.3.6)` --semantically_similar_to--> `Screenshot-to-Text Documentation`  [INFERRED] [semantically similar]
  README.md → docs/vision.md
- `_MockASR` --uses--> `FasterWhisperProvider`  [INFERRED]
  scripts/benchmark.py → src/agentvoca/asr/faster_whisper.py
- `_MockASR` --uses--> `RulesCleanupProvider`  [INFERRED]
  scripts/benchmark.py → src/agentvoca/cleanup/rules.py
- `_MockASR` --uses--> `FullConfig`  [INFERRED]
  scripts/benchmark.py → src/agentvoca/config/schema.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **AgentVoca provider plug-in system** — concept_provider_registry, concept_asr_provider_base, concept_cleanup_provider_base, concept_insertion_strategy_base, concept_faster_whisper_provider, concept_openai_compatible_asr, concept_rules_cleanup, concept_openai_compatible_cleanup, concept_keyboard_insertion, concept_clipboard_insertion, concept_domain_error_pattern [EXTRACTED 0.95]
- **v0.4.0 Observer Mode release surface** — readme_observer_mode, docs_observer, docs_observer_session_lifecycle, docs_observer_keyframe_triggers, docs_observer_privacy_consent, docs_observer_crash_recovery, docs_observer_resource_budget, docs_observer_ocr_providers, docs_observer_compile_providers, docs_observer_speech_onset_d9, docs_observer_visible_consent, docs_observer_token_bucket_rate_limiting, docs_config_reference_observer, examples_config_observer [EXTRACTED 0.95]
- **Configuration validation test fixtures** — tests_fixtures_configs_invalid_hotkey, tests_fixtures_configs_invalid_sample_rate, tests_fixtures_configs_invalid_silence_timeout, tests_fixtures_configs_missing_required, tests_fixtures_configs_valid_full [INFERRED 0.95]
- **v0.3.6 performance, stability, I/O pass** — docs_performance_v036_optimizations, docs_performance_vad_worker_thread, docs_performance_latency_budgets, docs_performance_benchmark_harness, readme_streaming_asr, readme_adaptive_vocabulary, _github_workflows_ci [INFERRED 0.85]
- **v0.3.6 Release Document Set** — docs_proposals_v0_3_6_optimization, docs_proposals_v0_3_6_plan_agent1_audio_streaming, docs_proposals_v0_3_6_plan_agent2_io_text_startup [EXTRACTED 1.00]
- **v0.4.0 Release Document Set** — docs_proposals_v0_4_0_observer_mode, docs_proposals_v0_4_0_contracts, docs_proposals_v0_4_0_plan_agent1_foundation_storage, docs_proposals_v0_4_0_plan_agent2_capture_perception, docs_proposals_v0_4_0_plan_agent3_compilation_surface [EXTRACTED 1.00]
- **Observer Threading Model Worker Threads** — docs_proposals_v0_4_0_observer_mode_threading_model, docs_proposals_v0_4_0_observer_mode_observer_store, docs_proposals_v0_4_0_observer_mode_asr_arbiter, docs_proposals_v0_4_0_observer_mode_ambient_listener, docs_proposals_v0_4_0_observer_mode_screen_grabber, docs_proposals_v0_4_0_observer_mode_ocr_provider, docs_proposals_v0_4_0_observer_mode_trigger_gate [EXTRACTED 1.00]

## Communities (169 total, 23 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.03
Nodes (85): AudioChunkEvent, AudioFrameEvent, CleanedTextEvent, CommandRecognizedEvent, ContextResolvedEvent, CorrectionLearnedEvent, ErrorEvent, PartialTranscriptEvent (+77 more)

### Community 1 - "Community 1"
Cohesion: 0.03
Nodes (50): _make_orchestrator(), _MockASR, _MockCleanup, Cleanup provider that returns the transcript unchanged after a delay., Wire an orchestrator with pre-built provider instances. A registry with…, ASR provider that returns fixed text after an optional simulated delay., ASRProvider, Abstract base class for automatic speech recognition providers. Implementations… (+42 more)

### Community 2 - "Community 2"
Cohesion: 0.03
Nodes (85): HotkeyManager, Global hotkey binding for voice dictation. Uses pynput.keyboard.HotKey (with…, Register a hotkey to emit a specific action. Args: hotkey_str: Hotkey…, Start the global hotkey listener., Stop the global hotkey listener., Forget every registered hotkey. Used by the v0.3.5 settings window to clear the…, Convert our config format to pynput HotKey.parse() format. Examples::…, Manages global hotkey registration and dispatch. Args: event_bus: Shared event… (+77 more)

### Community 3 - "Community 3"
Cohesion: 0.03
Nodes (69): CallbackFlags, CallbackStop, AmbientSink, AudioCapture, ndarray, Protocol, Open the audio input stream. Raises: AudioError: If the selected device cannot…, Close the audio input stream and join the VAD worker (R2). (+61 more)

### Community 4 - "Community 4"
Cohesion: 0.04
Nodes (60): _fmt_elapsed(), ObserverIndicator, Minimal transparent status overlay showing recording state and interim…, Place the overlay in the top-right corner of the screen., Emit the transcript text onto the GUI thread., Emit a partial transcript onto the GUI thread., Emit warm-up completion onto the GUI thread., Update the state label when the app state changes (GUI thread). (+52 more)

### Community 5 - "Community 5"
Cohesion: 0.03
Nodes (44): _ProviderEntry, ProviderRegistry, Resolve a lazily-registered ``"module:Class"`` path to a class., Register an ASR provider class under the given name. Args: name: Unique…, Register a cleanup provider class under the given name. Args: name: Unique…, Register an insertion strategy class under the given name. Args: name: Unique…, Register a vision provider class under the given name. Args: name: Unique…, Register an Observer OCR provider class under the given name. Args: name:… (+36 more)

### Community 6 - "Community 6"
Cohesion: 0.04
Nodes (40): AudioChunker, Clear the internal buffer without stopping., Return new audio since the last emission and compact the buffer. ``end`` is…, Emit audio deltas at the configured cadence., Emits raw audio delta ``AudioChunkEvent`` s during recording. Args: event_bus:…, True if the chunker is actively emitting chunks., Begin the chunk emission loop., Feed incoming audio data into the chunker buffer. Args: data: Raw PCM float32… (+32 more)

### Community 7 - "Community 7"
Cohesion: 0.05
Nodes (40): pytestmark_uia, Text the user highlighted on screen. Attributes: text: The selected text,…, Selection, ABC, Selection reader abstract base class (v0.4.0, OBS-18). The contract: read the…, Reads the current text selection on screen. Implementations must be read-only.…, Return False on platforms/configs where selection reading cannot work (e.g.…, Read the current selection, or None if there is none. Returns ``None`` when: -… (+32 more)

### Community 8 - "Community 8"
Cohesion: 0.04
Nodes (29): InsertionConfig, Text insertion configuration., InsertionResult, Result of a text insertion attempt. Attributes: success: True if the text was…, InsertionStrategy, ABC, Insertion strategy abstract base class. All text insertion strategies must…, Abstract base class for text insertion strategies. Implementations must handle… (+21 more)

### Community 9 - "Community 9"
Cohesion: 0.06
Nodes (43): Rewrite transcript using the LLM. Args: transcript: The raw transcript text.…, Read custom_prompt_path, cached by mtime so edits are picked up., InsertionCompleteEvent, Published when text insertion completes. Attributes: success: True if insertion…, Published when recording stops with the captured audio. Attributes:…, Published when a transcript segment is available. Attributes: text: The…, RecordingStoppedEvent, TranscriptEvent (+35 more)

### Community 10 - "Community 10"
Cohesion: 0.04
Nodes (28): CleanupProvider, Abstract base class for transcript cleanup providers. Implementations must…, Return True if the provider can clean partial segments coherently. Default…, Prime connection pool / load local model. Must not raise. Default no-op., Return the registry key for this provider. Returns: The unique string name used…, Return True if the provider can accept requests right now. This should check…, Return a cleaned version of the transcript. Must never return an empty string…, CleanupConfig (+20 more)

### Community 11 - "Community 11"
Cohesion: 0.05
Nodes (45): ASRConfig, FullConfig, Top-level configuration model combining all sections., ASR provider configuration., minimal_config(), Return a minimal valid FullConfig suitable for unit tests., Test 3: after a cancel, the next full dictation completes normally., Test 4: cancel() is safe to call repeatedly and in idle state. (+37 more)

### Community 12 - "Community 12"
Cohesion: 0.08
Nodes (35): BaseModel, field_validator, AdaptiveConfig, CommandsConfig, ContextConfig, ObserverCompileConfig, ObserverConfig, ObserverPrivacyConfig (+27 more)

### Community 13 - "Community 13"
Cohesion: 0.07
Nodes (23): AppConfig, AudioConfig, HotkeysConfig, Hotkey binding configuration., Vocabulary/substitution settings., Snippet expansion settings., Application-level settings., Audio capture settings. (+15 more)

### Community 14 - "Community 14"
Cohesion: 0.05
Nodes (30): Future, AsyncLoopThread, AbstractEventLoop, Any, A single asyncio event loop owned by a dedicated daemon thread., Start the loop thread and block until the loop is running., The underlying event loop (running on the background thread)., Schedule a coroutine on the loop from any thread. Returns a… (+22 more)

### Community 15 - "Community 15"
Cohesion: 0.07
Nodes (29): _active_window_rect_windows(), dhash(), hamming(), ImageGrab_grab(), Image, Screen capture + perceptual-hash dedup (v0.4.0, OBS-14). Grabs the active…, Grabs the active window rect, downscales, encodes JPEG, hashes. A single…, Enqueue a capture request. Returns False if the queue is full. (+21 more)

### Community 16 - "Community 16"
Cohesion: 0.06
Nodes (57): v0.3.6 Performance & Reliability Proposal, R10: Parallelize multi-screenshot vision extraction via asyncio.gather, R11: One shared single-worker input executor for pyautogui/pyperclip, R12: O(1) casing lookup in VocabularyDictionary._replacement, R13: Bulk add_mappings() API for learned vocabulary merges, R14: Lazy provider imports via dotted-path registry, R1: Delete duplicate VAD inference in audio callback, R2: Move VAD inference off audio callback via dedicated worker thread (+49 more)

### Community 17 - "Community 17"
Cohesion: 0.05
Nodes (29): QAction, QIcon, Emit the state change onto the GUI thread., _fmt_elapsed(), _make_icon(), QWidget, Update the tray icon to reflect the given dictation state., Emit the state change onto the GUI thread. (+21 more)

### Community 18 - "Community 18"
Cohesion: 0.07
Nodes (37): all_snippets(), bash_snippet(), EnvStatus, fish_snippet(), powershell_snippet(), Env-var helper — the UI's "Set this API key now" affordance. AgentVoca never…, Return the most useful persistence snippet for the host OS. Args: name: Env var…, Return every persistence snippet, keyed by shell name. Useful for a dialog that… (+29 more)

### Community 19 - "Community 19"
Cohesion: 0.06
Nodes (38): _construct_lenient(), _expand_env_vars(), load_config(), load_config_lenient(), _load_yaml(), Any, Path, Config loader: YAML parsing, environment variable expansion, validation.… (+30 more)

### Community 20 - "Community 20"
Cohesion: 0.06
Nodes (28): load_config_from_dict(), Load config from an in-memory dictionary (useful for testing). Environment…, _load_fixture(), A full config with all fields should load cleanly., A missing env var should be replaced with empty string., A remote provider with api_key_env=null should not require the env var., A remote provider with a set api_key_env should pass., A remote provider with a missing api_key_env should fail. (+20 more)

### Community 21 - "Community 21"
Cohesion: 0.08
Nodes (35): make_default_catalog(), ModelCatalog, ModelCatalogError, ModelEntry, Model catalog — fetch the list of models available at an OpenAI-compatible…, Fetch on a background thread; deliver result via ``on_done``. ``on_done``…, Drop the cached model list. Used when the user changes the endpoint., Turn a ``/v1/models`` payload into ``ModelEntry`` rows. Handles the… (+27 more)

### Community 22 - "Community 22"
Cohesion: 0.10
Nodes (17): ObserverStore, Path, SQLite-backed session + event store for Observer mode. All writes are non-…, _make_event(), Path, OBS-5: ObserverStore tests. The store is the source of truth for Observer data.…, The clamp must not leak across sessions: a new session starts clean., Simulate a hard kill: append events, then stop() without close_session. On a… (+9 more)

### Community 23 - "Community 23"
Cohesion: 0.07
Nodes (24): Return the current application state., AbstractEventLoop, Pause the open session. False if already paused or no session., Resume a paused session. False if not paused or no session., Owns the currently-open session and its paused state. Pure coordination over…, Reason the session is currently paused. Empty when not paused., SessionManager, AppState (+16 more)

### Community 24 - "Community 24"
Cohesion: 0.11
Nodes (38): OpenAICompatibleCompiler, AsyncClient, LLM session compiler for any OpenAI-compatible /v1/chat/completions endpoint.…, Build the persistent HTTP client. Exposed as a seam for tests., Close the pooled HTTP client. Safe to call more than once., Send a chat-completion request and return the assistant text. Exposed as a seam…, _build_bundle(), _handler_fail_nth() (+30 more)

### Community 25 - "Community 25"
Cohesion: 0.06
Nodes (25): ABC, ASR provider abstract base class. All ASR adapters must subclass…, Faster-Whisper ASR provider. Inference is performed locally using the faster-…, Register pip-installed NVIDIA DLL directories with the Windows DLL loader.…, _register_cuda_dlls(), ASR provider adapters. Provider classes are imported lazily (PEP 562) so that…, _pcm_f32_to_wav(), OpenAI-compatible ASR provider. Sends audio to any OpenAI-compatible… (+17 more)

### Community 26 - "Community 26"
Cohesion: 0.07
Nodes (22): The trigger → expansion mapping (read-only)., True if no snippets are registered., Expand snippet triggers in the given text. Triggers are matched as case-…, Snippet expansion for transcript text. Replaces trigger words/phrases with…, SnippetExpander, The mapping property returns a copy, not the internal dict., No snippets means no expansion., A trigger should not match words that merely contain it. (+14 more)

### Community 27 - "Community 27"
Cohesion: 0.06
Nodes (21): OnText, _AmbientJob, ASRArbiter, ASR arbiter for Observer mode (v0.4.0, OBS-12). Serialises access to a single…, Dictation path. Blocks ambient for the duration of the call. The try/finally…, Enqueue an ambient job. Returns False if the enqueue failed. On overflow the…, Loop-thread enqueue with oldest-drop on overflow. Every overflow increments…, Number of ambient jobs dropped due to queue overflow. (+13 more)

### Community 28 - "Community 28"
Cohesion: 0.07
Nodes (23): Screenshot capture (v3)., _png_dimensions(), Block until no captures are in flight, or until ``timeout`` elapses. Returns…, Return all captured screenshots in order and clear the queue., Return True if any captures are queued or in flight., Discard any queued screenshots (e.g. at the start of a recording)., Run the platform snip and return PNG bytes, or None if cancelled., Return (width, height) for PNG bytes, or (None, None) if not parseable. (+15 more)

### Community 29 - "Community 29"
Cohesion: 0.09
Nodes (30): atomic_write_text(), Exporter, Path, Protocol, Internal helpers for Observer exporters (v0.4.0, Track 3, OBS-24). Atomic file…, Protocol for an Observer session exporter. An exporter is constructed with a…, Write the artifact and return its path. The controller…, Write ``text`` to ``path`` atomically. A crash mid-write (process kill, power… (+22 more)

### Community 30 - "Community 30"
Cohesion: 0.08
Nodes (28): action_by_field(), find_preset(), HotkeyAction, HotkeyPreset, labels_for_dropdown(), Hotkey preset catalogue. Per the v0.3.5 UI decision, the hotkey fields expose a…, Return the config value for a dropdown label, or ``CUSTOM`` sentinel. Returns…, Return the warning string for ``value``, or None if it has none. (+20 more)

### Community 31 - "Community 31"
Cohesion: 0.06
Nodes (30): Load the silero-vad model. Raises: VADError: If the model fails to load., AgentVocaError, CaptureError, HotkeyError, InsertionError, ProviderNotAvailableError, Exception, Domain exception hierarchy for the AgentVoca application. All modules surface… (+22 more)

### Community 32 - "Community 32"
Cohesion: 0.09
Nodes (22): Render a session into a ``CompiledSession``. MUST NOT raise. On any internal…, Render every event as one line, in ts_ms order. The output is intentionally…, Compile a session. Never raises. Per-block calls run in parallel via…, CompiledSession, Grab, A captured screen region, already encoded. Attributes: jpeg: JPEG-encoded…, Output of a SessionCompiler. Attributes: markdown: The full rendered markdown…, A whole session loaded into memory for compilation. ``events`` is ordered by… (+14 more)

### Community 33 - "Community 33"
Cohesion: 0.09
Nodes (31): ExclusionMatcher, Pattern, Privacy exclusion matching for Observer mode (v0.4.0, Track 3, OBS-25). Decides…, Decides whether the current foreground context must not be captured. Args:…, Compile a list of glob patterns into a list of (literal, regex) pairs.…, The original ``exclude_apps`` patterns (post-filter of blanks)., The original ``exclude_title_patterns`` (post-filter of blanks)., Return ``(excluded, matched_pattern)``. A match in either list excludes. The… (+23 more)

### Community 34 - "Community 34"
Cohesion: 0.13
Nodes (14): Rate-limit keyframe requests. The only path to a screen capture. All four…, TriggerGate, FakeActiveApp, FakeClock, FakeSession, _make_engine(), Tests for the trigger sources (OBS-13). The sources — window change, scroll…, Active-app detector fake. ``set(app, title)`` then ``detect()`` returns it. (+6 more)

### Community 35 - "Community 35"
Cohesion: 0.09
Nodes (21): AppBasicsPage, App basics page — language hint, recording mode, debug toggle., Wizard and settings-window page widgets. Each page is a ``ConfigPage`` subclass…, ObserverPage, QComboBox, Observer settings page (v0.4.0, Track 3, OBS-27). Exposes every ``observer.*``…, Tabbed settings window — replaces the read-only ``app/settings.py``. Wraps the…, _force_offscreen_qt() (+13 more)

### Community 36 - "Community 36"
Cohesion: 0.07
Nodes (19): QWizard, QWizardPage, ConfigPage, Base class for every page in the wizard and settings window. Subclasses…, Attach or re-attach a controller and refresh the UI., Build the page's UI. Subclasses should populate ``self._body``. The default…, Sync the UI from the controller's draft. Override in subclasses., Sync the UI back into the controller's draft. Override in subclasses. (+11 more)

### Community 37 - "Community 37"
Cohesion: 0.08
Nodes (19): ProfileResolver, Resolves an app name to a cleanup style profile. Args: profiles: A dict mapping…, Return a copy of the raw mapping (profile name → style)., Resolve an app name to a style profile. Args: app_name: The detected…, With no profiles, resolve should return None., Exact app name match should return the configured style., When no pattern matches, the '*' fallback should be used., Patterns using glob wildcards should match via fnmatch. (+11 more)

### Community 38 - "Community 38"
Cohesion: 0.09
Nodes (21): _asr_endpoint_warning(), AsrPage, QComboBox, ASR (speech-to-text) page — provider, model, endpoint, API key., Show/hide the 'this host can't do speech-to-text' warning., # NOTE: OpenRouter is intentionally NOT in this list. It added a dedicated, Kick off an async model-list fetch for the current endpoint + key., Return a warning if ``endpoint`` is a known chat-only (no-STT) host. (+13 more)

### Community 39 - "Community 39"
Cohesion: 0.15
Nodes (19): collected_utterances(), loop_thread(), _make_block(), _make_listener(), fixture, Tests for ``AmbientListener`` (OBS-11). The listener segments a stream of audio…, Build a listener with a real (or scripted) VAD., Returns a scripted sequence of (is_speech) per ``process_chunk`` call. When the… (+11 more)

### Community 40 - "Community 40"
Cohesion: 0.09
Nodes (21): DeviceEntry, DeviceProbe, _devices_module(), Device probe — thin wrapper around ``audio.devices`` for the UI layer. The…, Return at least the 'default' entry when PortAudio is unavailable., Return the cached entries, refreshing once on first call., Resolve a config value to a concrete device info dict, or None. Used by tests…, Return ``agentvoca.audio.devices``, importing lazily. Imported lazily so… (+13 more)

### Community 41 - "Community 41"
Cohesion: 0.09
Nodes (18): User-defined vocabulary for term substitution in transcripts. Usage:: vocab =…, VocabularyDictionary, A vocabulary term should not match inside another word., No terms means no substitutions., The terms property returns a copy, not the internal list., Empty text returns empty text., A vocabulary term matched case-insensitively is preserved with its original…, If the term is already correctly cased, it stays the same. (+10 more)

### Community 42 - "Community 42"
Cohesion: 0.11
Nodes (18): Audio capture using sounddevice. Captures microphone audio with configurable…, Audio chunker — emits raw audio deltas during recording. The chunker feeds…, Audio device enumeration and selection. Wraps sounddevice to enumerate input…, Voice activity detection wrapper around silero-vad. Wraps the silero-vad…, Screenshot capture using OS-native snip tools (v3). The capturer invokes the…, Persistent asyncio event loop running on a background thread. The desktop app's…, Synchronous-first event bus for the agentvoca pipeline. Handlers are called in…, Observer ambient listener (v0.4.0, OBS-11). Segments the ambient mic tap into… (+10 more)

### Community 43 - "Community 43"
Cohesion: 0.10
Nodes (29): _dedup_lines(), _escape_md(), _first_non_empty_lines(), _fmt_date(), _fmt_duration(), _fmt_hhmm(), _local_time(), _pluralize() (+21 more)

### Community 44 - "Community 44"
Cohesion: 0.09
Nodes (17): OCRResult, Frozen data models for Observer mode (v0.4.0). Pure data. No I/O, no behavior,…, Output of an OCRProvider. Attributes: text: Extracted text, reading order,…, OCRProvider, ABC, OCR provider abstract base class (v0.4.0, OBS-15). Mirrors the conventions of…, Abstract base class for Observer OCR providers., Extract text from a JPEG. Args: image_jpeg: JPEG-encoded bytes (the… (+9 more)

### Community 45 - "Community 45"
Cohesion: 0.13
Nodes (27): _backup_existing(), _ensure_parent(), load_from_disk(), Any, Path, Persistence helpers for the interactive setup wizard / settings window. The…, Backup + write helper shared by the two save paths., Load and validate a YAML config from disk. Thin wrapper around ``load_config``… (+19 more)

### Community 46 - "Community 46"
Cohesion: 0.15
Nodes (25): build_fixture_session(), Write a realistic multi-block session into ``store`` and return it.…, _attach(), _make_full_config(), _NoopIndicator, asyncio, Path, Integration tests for the Observer compile-on-stop and recovery flow (OBS-28).… (+17 more)

### Community 47 - "Community 47"
Cohesion: 0.09
Nodes (13): Owns the four trigger sources and a ``TriggerGate``. Threading --------- -…, Start the poll thread and the mouse listener. Idempotent., Stop the poll thread and the mouse listener. Idempotent., Called by the AmbientListener at every IDLE→SPEAKING transition., Inject a click-down position from tests., Inject a click-up position from tests., Inject a scroll event from tests., One iteration of the poll loop. Used by tests. (+5 more)

### Community 48 - "Community 48"
Cohesion: 0.14
Nodes (27): load_controller(), Build a ``ConfigController`` from a YAML file on disk. Falls back to the v1…, Path, Integration tests for the setup wizard. Drives the wizard headlessly with the…, A page the user has not visited must keep whatever the controller had in it.…, Regression: typing into the ASR page and clicking Next used to clobber the…, test_wizard_constructs_with_eight_pages(), test_wizard_emits_config_saved_signal() (+19 more)

### Community 49 - "Community 49"
Cohesion: 0.09
Nodes (17): _CollectingSink, _FullQueueSink, _indata(), ndarray, patch, _RaisingSink, Audio-callback p99 < 5 ms with the tap installed. Same methodology as the…, With no sink installed, the callback is byte-identical to v0.3.6. (+9 more)

### Community 50 - "Community 50"
Cohesion: 0.09
Nodes (15): AmbientListener, AbstractEventLoop, Protocol, AmbientSink impl. Runs on the sounddevice callback thread. Strictly non-…, Spawn the worker thread. Idempotent. Loads the own VAD if one was not injected.…, Stop the worker thread and release the own VAD if any., Force-emit any in-progress utterance. Test barrier; also called at session stop…, Number of utterances emitted since construction. (+7 more)

### Community 51 - "Community 51"
Cohesion: 0.11
Nodes (23): ABC, Session compiler abstract base class and shared blocking algorithm (v0.4.0).…, Abstract base class for Observer session compilers. Args: config: The Observer…, Optional soft contract. Default no-op., SessionCompiler, _local_time(), NoneCompiler, datetime (+15 more)

### Community 52 - "Community 52"
Cohesion: 0.17
Nodes (23): JsonExporter, Path, Build contracts \xa75's JSON sidecar for the v0.5.0 Agent contract., Write the JSON sidecar and return its path. Args: compiled: The compiled…, Build the JSON ``blocks`` array. Block boundaries come from ``split_blocks`` so…, _build(), _load(), asyncio (+15 more)

### Community 53 - "Community 53"
Cohesion: 0.11
Nodes (15): CleanupPage, QComboBox, Cleanup page — provider, style, endpoint, API key., Kick off an async model-list fetch for the current endpoint + key., QComboBox, Small helpers shared between page widgets. Kept in a private module so the…, Pick the authoritative id from an editable QComboBox. The combobox is populated…, resolve_editable_combo_id() (+7 more)

### Community 54 - "Community 54"
Cohesion: 0.20
Nodes (27): _build_compiler(), _build_fixture_bundle(), asyncio, Path, Tests for ``observer/compile/rules.py`` (OBS-21). All tests run against the…, An empty bundle compiles to a valid stub, not a crash., Compiling the same bundle twice yields byte-identical output., A repeated OCR line is shown once per block, not on every keyframe. (+19 more)

### Community 55 - "Community 55"
Cohesion: 0.12
Nodes (13): QCloseEvent, Backward-compat shim — the read-only settings window moved to ``setup``. The…, QWidget, Push every page's UI state back into the controller draft., Reload every page from the controller and update the banner., Tabbed editor for ``FullConfig`` with apply / discard / restart banner., SettingsWindow, Path (+5 more)

### Community 56 - "Community 56"
Cohesion: 0.12
Nodes (19): Vision / screenshot-to-text configuration (v3). When enabled, a dedicated…, VisionConfig, OpenAICompatibleVisionProvider, AsyncClient, Vision provider using an OpenAI-compatible chat-completions API., Initialize the provider with config. Args: config: The vision configuration…, Construct the shared ``httpx.AsyncClient``. Exposed as a seam so tests can…, Close the pooled HTTP client. Safe to call more than once. (+11 more)

### Community 57 - "Community 57"
Cohesion: 0.14
Nodes (26): Partition a session's events into blocks. A new block starts on a…, split_blocks(), _bundle(), _evt(), Tests for ``observer/compile/base.py`` — the shared blocking algorithm. Track…, A pause stretch inside one block does not fragment the block., An empty session produces zero blocks., If the session does not start with a focus_change, an implicit block is opened… (+18 more)

### Community 58 - "Community 58"
Cohesion: 0.11
Nodes (20): AnchorSplicer, Match, Anchor-phrase splicing for screenshot extractions (v3). When the user dictates…, Splices ordered extractions into a transcript at anchor phrases., Initialize with a phrase list, falling back to the built-in defaults. Args:…, Return non-overlapping anchor matches in left-to-right order., Splice extractions into the transcript. Args: transcript: The dictated text…, Vision (screenshot-to-text) providers (v3). Exports all built-in vision… (+12 more)

### Community 59 - "Community 59"
Cohesion: 0.10
Nodes (16): BoundLogger, Hot-apply every supported field from ``new_config``. Restart-only fields (ASR…, get_logger(), Get a structlog logger instance., AdaptiveStore, Path, Tracks user corrections and promotes frequently corrected terms to the…, Save learned terms and mappings to the persistence file. (+8 more)

### Community 60 - "Community 60"
Cohesion: 0.10
Nodes (15): _harden_directory(), SQLite-backed session + event store for Observer mode (v0.4.0). This module…, A single instruction for the writer thread. A barrier job carries an ``event``…, Open the DB, apply the schema, start the writer thread. Idempotent. Creates…, Block until the write queue is empty. Returns False on timeout. This is the…, status='closed'. Blocks until written (a close must not be lost)., Blocking append that returns the new row id. Only for keyframes, which need the…, Fill in OCR text after the fact. Merges into meta_json, not replace. (+7 more)

### Community 61 - "Community 61"
Cohesion: 0.14
Nodes (23): all_known_paths(), _classify(), is_hot_field(), is_restart_field(), partition(), Restart policy — classify every FullConfig field as hot-apply or restart. A…, Classify ``path`` as ``"hot"``, ``"restart"``, or ``None`` (unknown).…, Return True if the field at dotted ``path`` requires an app restart. (+15 more)

### Community 62 - "Community 62"
Cohesion: 0.11
Nodes (16): config(), event_bus(), EventCollector, pipeline(), fixture, Integration test: full pipeline from RecordingStoppedEvent to…, Collects events of a specific type from an event bus., End-to-end pipeline tests with event-driven orchestration. (+8 more)

### Community 63 - "Community 63"
Cohesion: 0.17
Nodes (10): FakeClock, _make_gate(), Tests for ``TriggerGate`` (OBS-13). The gate is the rate-limit chokepoint.…, Monotonic clock fake. ``advance(dt_seconds)`` moves it forward., TestDisabledSourceFlag, TestEnqueueOverflow, TestMinInterval, TestPreGateFilters (+2 more)

### Community 64 - "Community 64"
Cohesion: 0.10
Nodes (15): ContextProvider, ABC, Context provider abstract base class and shared dataclasses. All context…, The resolved context at a point in time. Attributes: app_name: Name of the…, Abstract base for context detection providers. Implementations must handle…, Return True if context detection works on this platform. Returns: True if the…, Return the current context. Must not raise. Returns an empty…, ResolvedContext (+7 more)

### Community 65 - "Community 65"
Cohesion: 0.20
Nodes (11): RapidOCRProvider, Local ONNX OCR. Default provider — no API key, fully offline. The engine is…, Run a one-off inference on a 64×64 blank to load the model. The first real…, _FakeEngine, _install_fake_rapidocr(), Tests for the RapidOCR provider (OBS-16). The provider wraps the…, Stand-in for the real ``RapidOCR`` engine. ``next_result`` controls return., Patch the lazy import so ``RapidOCR`` returns our fake engine. (+3 more)

### Community 66 - "Community 66"
Cohesion: 0.09
Nodes (13): Pure session-lifecycle state machine for Observer mode (v0.4.0). Owns the…, Trigger gate and sources for Observer keyframe capture (v0.4.0, OBS-13). The…, _baseline_thread_count(), event_bus(), loop_thread(), _NoopActiveApp, fixture, 10-minute simulated session budget test (OBS-19). The hard acceptance gate:… (+5 more)

### Community 67 - "Community 67"
Cohesion: 0.10
Nodes (12): Connection, _now_ms(), Create a session with status='open'. Synchronous. We open a short-lived…, Crash recovery: sessions left status='open' by a previous process., Execute a SELECT against the sessions table. ``clause`` is the part after…, Total blob bytes for a session, for the max_session_mb cap., Delete rows, blobs, and exports for one session. Irreversible., Delete every session. Returns the count. Irreversible. (+4 more)

### Community 68 - "Community 68"
Cohesion: 0.11
Nodes (15): Context passed to a vision (VLM) provider for image extraction. Attributes:…, VisionContext, ABC, Vision provider abstract base class (v3). All vision/VLM adapters must subclass…, Abstract base class for screenshot-to-text vision providers. Implementations…, Prime connection pool / load local model. Must not raise. Default no-op., Return the registry key for this provider., Return True if the provider can accept requests right now. This should check… (+7 more)

### Community 69 - "Community 69"
Cohesion: 0.12
Nodes (10): CountingClient, _provider(), Tests for the OpenAI-compatible OCR provider (OBS-17). Modeled on…, ``AsyncClient``-like fake: counts constructions, records posts., Subclass that uses CountingClient for its HTTP client., Build a provider backed by CountingClient., _TestableProvider, TestErrorHandling (+2 more)

### Community 70 - "Community 70"
Cohesion: 0.13
Nodes (10): ClipboardInsertionStrategy, Inserts text by writing to clipboard and sending paste hotkey. Args: config:…, Clipboard is always available on supported platforms., patch, Non-ASCII text bypasses typewrite and goes via clipboard., Text containing newlines bypasses typewrite and goes via clipboard., Clipboard strategy writes to clipboard and sends paste hotkey., TestClipboardInsertion (+2 more)

### Community 71 - "Community 71"
Cohesion: 0.16
Nodes (14): _build_config(), _build_registry(), _empty_extract(), _FakeCapturer, asyncio, Tests for R10: parallel multi-screenshot vision extraction. Verifies that…, 3 shots × 300ms must finish in well under 900ms (parallel)., If one of three shots raises VisionError, the other two still splice — and in… (+6 more)

### Community 72 - "Community 72"
Cohesion: 0.13
Nodes (16): CountingClient, _provider(), asyncio, Tests for R8: persistent HTTP client in OpenAICompatibleCleanupProvider.…, ``shutdown()`` calls aclose() and a second call does not raise., Providers without a ``shutdown`` attribute (e.g. mocks, other adapters) are…, AsyncClient-like stand-in: counts constructions, records posts., A subclass that uses CountingClient for its shared HTTP client. (+8 more)

### Community 73 - "Community 73"
Cohesion: 0.11
Nodes (15): _all_kinds(), _events_by_kind(), EventKind, fixture, Path, OBS-9: fixture-session generator tests. The generator writes a deterministic…, Two calls into two different temp stores produce structurally identical bundles…, blocks=0 produces an open session that closes with no events. Useful for the… (+7 more)

### Community 74 - "Community 74"
Cohesion: 0.13
Nodes (12): FasterWhisperProvider, Initialize the provider. Args: config: The ASR configuration block., Return True when streaming is enabled in config., Preload both accurate and streaming models at startup. Also runs a tiny…, Lazy load the accurate Whisper model, with automatic CPU fallback., Lazy load the streaming (small/fast) Whisper model., Return the registry key for this provider., Return True if the model can be loaded. (+4 more)

### Community 75 - "Community 75"
Cohesion: 0.14
Nodes (10): ObserverOCRConfig, OCR provider configuration. ``api_key_env`` is the **name** of an environment…, OpenAICompatibleOCRProvider, AsyncClient, Return True when an endpoint is configured and an API key is set if required., OCR provider using an OpenAI-compatible chat-completions API. Sends the JPEG to…, Construct the shared ``httpx.AsyncClient``. Exposed as a seam so tests can…, Close the pooled HTTP client. Safe to call more than once. (+2 more)

### Community 76 - "Community 76"
Cohesion: 0.14
Nodes (15): CountingClient, _ok_response(), _provider(), asyncio, Tests for R8: persistent HTTP client in OpenAICompatibleVisionProvider.…, AsyncClient-like stand-in: counts constructions, records posts., Subclass that uses CountingClient for its shared HTTP client., Build a vision provider backed by a counting client. (+7 more)

### Community 77 - "Community 77"
Cohesion: 0.16
Nodes (7): Pure state machine for the dictation pipeline. Usage:: sm = StateMachine()…, Return the current state., StateMachine, §6.2 transitions starting from ``idle``., §6.2 transitions starting from ``recording``., TestTransitionsFromIdle, TestTransitionsFromRecording

### Community 78 - "Community 78"
Cohesion: 0.16
Nodes (13): OpenAICompatibleCleanupProvider, Return True if endpoint and API key (if required) are set., Cleanup provider using an OpenAI-compatible LLM API., Close the pooled HTTP client. Safe to call more than once., Prime the HTTP connection pool with a lightweight health check. Sends a minimal…, Return the registry key for this provider., _patch_client(), asyncio (+5 more)

### Community 79 - "Community 79"
Cohesion: 0.14
Nodes (9): ActiveAppDetector, Foreground application detection per platform. Uses ``ctypes`` (Windows:…, Detect foreground app on macOS using AppKit. Requires pyobjc (only available on…, Detects the foreground application and window title. Platform support: -…, Check if platform detection APIs are accessible., Return True if foreground detection works on this platform., Detect the current foreground app and window title. Returns: A tuple…, Detect foreground app on Windows using ctypes + user32. Retrieves the window… (+1 more)

### Community 80 - "Community 80"
Cohesion: 0.16
Nodes (15): block_window(), Return the ``(started_at_ms, ended_at_ms)`` window of a block. Empty block ->…, _parse_block_response(), OpenAI-compatible LLM session compiler (v0.4.0, Track 3, OBS-22). Two-phase…, Split an LLM response into ``(body, summary_line)``. The block prompt asks for…, Compile one block. Returns ``(markdown, summary, block_record)``. On HTTP…, Render a block as a compact JSON-ish text for the LLM. Token-budgeted: stops…, _serialise_block_for_llm() (+7 more)

### Community 81 - "Community 81"
Cohesion: 0.12
Nodes (6): config(), loop_thread(), MockASR, MockCleanup, fixture, Integration test: dictation during an Observer session (OBS-12). Verifies that:…

### Community 82 - "Community 82"
Cohesion: 0.21
Nodes (11): FakeCapturer, _make_orch(), asyncio, Integration tests for the v3 vision splice in the orchestrator pipeline., Minimal capturer stub implementing the orchestrator's interface., _registry(), test_extraction_appended_when_no_anchor(), test_instruction_passed_to_vision_provider() (+3 more)

### Community 83 - "Community 83"
Cohesion: 0.15
Nodes (17): fw_config(), openai_config(), asyncio, fixture, Unit tests for ASR adapters., Test OpenAICompatibleASRProvider error handling., A 4xx must include the provider's response body for diagnosis., Test FasterWhisperProvider's buffering stream implementation. (+9 more)

### Community 84 - "Community 84"
Cohesion: 0.19
Nodes (16): skipif, MonkeyPatch, Path, OBS-6: storage directory ACL hardening (D12). D12 chose no encryption; the…, A raising icacls call must not prevent the store from starting., A raising os.chmod must not prevent the store from starting., Restarting the same store on the same dir does not re-harden. The check is a…, POSIX: the root directory ends up with mode 0o700. (+8 more)

### Community 85 - "Community 85"
Cohesion: 0.22
Nodes (10): CommandProcessor, CommandResult, High-precision match of leading/standalone command phrases. Returns…, DefaultCommandProcessor, Implementation of CommandProcessor with a default set of editing commands., test_command_matching_case_insensitive(), test_command_matching_leading(), test_command_matching_no_match() (+2 more)

### Community 86 - "Community 86"
Cohesion: 0.15
Nodes (11): _build_pattern(), Path, Pattern, Add new terms to the dictionary and rebuild the matching pattern. Args: terms:…, Recompile the match pattern and the casing lookup together., Add a mapping from a misrecognized term to a correct term. Args: wrong: The…, Add many wrong->right mappings with a single pattern rebuild., Read a vocabulary file, one term per line. Lines are stripped. Empty lines and… (+3 more)

### Community 87 - "Community 87"
Cohesion: 0.17
Nodes (13): OpenAI-compatible LLM cleanup provider. Sends transcripts to any OpenAI-…, get_cleanup_prompt(), System prompt templates for cleanup providers. Contains style-specific…, Generate a full system prompt for a cleanup provider. Args: style: The cleanup…, Unit tests for cleanup prompt generation., Test raw style prompt generation., Test custom prompt override., Test prompt generation without technical guardrails. (+5 more)

### Community 88 - "Community 88"
Cohesion: 0.14
Nodes (13): InvalidTransitionError, Any, Exception, State machine for the voice dictation pipeline. Implements the exact state…, Return the list of side-effect symbolic names for a matched transition. These…, Evaluate a single event against the transition table. Args: event_type: The…, Evaluate a named condition against the provided context dict. Each ``if``…, A single entry in the transition table. (+5 more)

### Community 89 - "Community 89"
Cohesion: 0.20
Nodes (3): QTableWidget, Vocabulary & snippets page — inline tables + file paths., VocabSnippetsPage

### Community 90 - "Community 90"
Cohesion: 0.13
Nodes (9): Cleanup provider using deterministic Python rules., No-op: rules-based cleanup has no model to load or pool to prime., Return the registry key for this provider., Always available (no dependencies)., Return True if 4 or more technical tokens are detected., Clean transcript using deterministic rules., RulesCleanupProvider, provider() (+1 more)

### Community 91 - "Community 91"
Cohesion: 0.19
Nodes (11): Keyboard insertion strategy. Types text into the active application using…, Remove the last inserted text. Strategy (in order): 1. Refocus the window that…, focus_window(), get_foreground_hwnd(), is_windows(), paste_modifier_key(), Windows-specific helpers for text insertion. Provides platform detection,…, Return True if running on Windows. (+3 more)

### Community 92 - "Community 92"
Cohesion: 0.18
Nodes (14): asyncio, Unit tests for the rules-based cleanup provider., Test that common filler words are removed., Test basic sentence capitalization., Test that sentence-end punctuation is added if missing., Test that technical tokens are detected and preserve_code is forced., Test that 'raw' style returns transcript unchanged., Test that empty input is returned as-is. (+6 more)

### Community 93 - "Community 93"
Cohesion: 0.28
Nodes (14): _install_fakes(), MonkeyPatch, Path, OBS-0: VAD wiring tests (pre-existing bug fix). Verified problem (before the…, audio.vad_enabled: True + a healthy VAD → AudioCapture gets a non-None vad., audio.vad_enabled: False → AudioCapture gets vad=None; VAD() never called., If VAD() raises, main must still build the pipeline with vad=None. Fail-open is…, VAD constructed successfully but ``is_available`` is False → vad=None. A silero… (+6 more)

### Community 94 - "Community 94"
Cohesion: 0.22
Nodes (14): ASRProvider abstract base, CleanupProvider abstract base, ClipboardInsertionStrategy, Domain-error wrapping pattern, Six-layer event-bus pipeline, FasterWhisperProvider, InsertionStrategy abstract base, KeyboardInsertionStrategy (+6 more)

### Community 95 - "Community 95"
Cohesion: 0.21
Nodes (13): _build_mock_config(), main(), _percentile(), _print_summary(), Pipeline latency benchmark harness (Phase E, PE-01). Replays audio through the…, A minimal valid config for the mock pipeline (all v2 features off)., Drive one full dictation cycle and record stage + end-to-end timings., Run the mock pipeline ``iterations`` times, discarding ``warmup`` runs. (+5 more)

### Community 96 - "Community 96"
Cohesion: 0.15
Nodes (13): ndarray, Copy the last ``window_s`` seconds out of ``buffer`` with one allocation. A…, _audio_bytes(), asyncio, The new snapshot must be byte-identical to the old implementation., Buffer < window must return the entire buffer, not error., Generate ``seconds`` of float32 zeros (little-endian)., Drive the streaming loop with ~60 s of audio and bound allocation. The old… (+5 more)

### Community 97 - "Community 97"
Cohesion: 0.15
Nodes (9): NoneCleanupProvider, Cleanup provider that performs no changes., Initialize the provider. Args: config: Optional configuration (ignored by this…, Return the registry key for this provider., Return the transcript unchanged., asyncio, Unit tests for the passthrough cleanup provider., test_none_cleanup_available() (+1 more)

### Community 98 - "Community 98"
Cohesion: 0.23
Nodes (5): KeyboardInsertionStrategy, Inserts text character-by-character via keyboard simulation. Args: config:…, patch, Tests for KeyboardInsertionStrategy., TestKeyboardInsertion

### Community 99 - "Community 99"
Cohesion: 0.19
Nodes (8): ObserverEvent, One row in the session timeline. Attributes: id: Database row id. 0 for an…, EventKind, Append an event to the open session. No-op (returns None) when closed. When…, Enqueue an event. Non-blocking. ``event.id`` is ignored., Read a whole session ordered by (ts_ms, id). Read-only connection., Two events must not share the same meta dict via the default factory., TestObserverEvent

### Community 100 - "Community 100"
Cohesion: 0.15
Nodes (13): Config Reference Documentation, adaptive config (v2), app config section, asr config section, commands config (v2), context config (v2), hotkeys config section, insertion config section (+5 more)

### Community 102 - "Community 102"
Cohesion: 0.19
Nodes (10): NoneOCRProvider, No-op OCR. Every keyframe yields an empty ``OCRResult``., Tests for the OCR provider base class and the ``none`` provider. The contract…, The base class cannot be instantiated directly., The contract: a blank image is a success, not an error., test_none_ocr_accepts_hint_but_ignores_it(), test_none_ocr_never_raises(), test_none_ocr_returns_empty_text() (+2 more)

### Community 103 - "Community 103"
Cohesion: 0.15
Nodes (12): counting_build_pattern(), fixture, Tests for R13: batched learned-mapping merge in VocabularyDictionary. Verifies…, Wrap ``_build_pattern`` so the test can count rebuilds., A single ``add_mappings`` call rebuilds the pattern exactly once, regardless of…, All 200 mappings apply to a transcript after a single bulk insert., ``add_mapping`` (singular) still rebuilds the pattern — used by the adaptive…, An empty batch is a no-op and does not trigger a rebuild. (+4 more)

### Community 104 - "Community 104"
Cohesion: 0.17
Nodes (5): SessionStatus, Owned by the writer thread. Owns the single sqlite3 connection., Insert the schema_version row if missing. Idempotent., Insert a single event. Enforces ts_ms monotonicity per session. Returns: The…, Fill in OCR text after the fact. Merges into meta_json, not replace.

### Community 105 - "Community 105"
Cohesion: 0.18
Nodes (4): Raised when a vision (VLM) extraction fails., VisionError, DummyClient, DummyResponse

### Community 106 - "Community 106"
Cohesion: 0.17
Nodes (9): loop_thread(), fixture, Unit tests for AsyncLoopThread and EventBus loop routing (v2 wiring)., A task spawned by a coroutine must keep running on the persistent loop., Publishing from a thread with no running loop routes to the loop., With no persistent loop set, async handlers run synchronously., test_create_task_inside_submitted_coro_survives(), test_event_bus_routes_async_handler_to_persistent_loop() (+1 more)

### Community 107 - "Community 107"
Cohesion: 0.21
Nodes (11): config(), provider(), asyncio, fixture, Unit tests for the OpenAI-compatible cleanup provider., Test successful cleanup via OpenAI API., Test API error handling., Test that it returns raw transcript if LLM returns empty. (+3 more)

### Community 108 - "Community 108"
Cohesion: 0.17
Nodes (7): Unit tests for the StateMachine. Covers every transition in the architecture…, Force-reset the state machine., A cycle where cleanup fails and insertion uses clipboard., Reach error state and recover to idle., TestErrorRecovery, TestFallbackCycle, TestReset

### Community 109 - "Community 109"
Cohesion: 0.17
Nodes (11): Tests for the R12 O(1) casing lookup in VocabularyDictionary. Verifies that the…, Plain terms: behavior identical to the previous linear-scan lookup., ``wrong -> right`` mappings take precedence over the casing lookup., For duplicate case-variants (e.g. ``polars`` and ``Polars``), the first added…, Terms with non-word characters (``C++``, ``C#``) match and keep their original…, Scale: 5,000-term dictionary applied to a ~1,000-word transcript with ~50…, test_behavior_arrow_mappings(), test_behavior_first_wins_for_case_variants() (+3 more)

### Community 110 - "Community 110"
Cohesion: 0.20
Nodes (7): Return True if we can simulate keyboard on this platform., has_accessibility_permissions(), is_macos(), Return True if running on macOS., Check whether the app has accessibility permissions on macOS. This is a best-…, Tests for platform detection utilities., TestPlatformHelpers

### Community 111 - "Community 111"
Cohesion: 0.35
Nodes (10): _install_fakes(), Path, Startup-ordering tests for ``agentvoca.main.main``. The critical guarantee…, A broken OCR provider must not block app startup. The wire-up in main.py wraps…, Replace every heavy collaborator in ``agentvoca.main`` with a fake. Returns a…, test_existing_config_starts_pipeline_without_a_modal_wizard(), test_existing_config_with_missing_api_key_does_not_crash(), test_first_run_builds_pipeline_only_after_the_wizard() (+2 more)

### Community 112 - "Community 112"
Cohesion: 0.22
Nodes (10): cleanup config section, Observer Mode Documentation, Observer Compile Providers, Observer Crash Recovery, Observer Privacy & Consent, Observer Resource Budget, Observer Session Lifecycle, Token Bucket Rate Limiting (+2 more)

### Community 113 - "Community 113"
Cohesion: 0.20
Nodes (4): _MockInsertion, Insertion strategy that always succeeds instantly., Run the real local pipeline (faster-whisper + rules) over WAV fixtures., _run_real()

### Community 114 - "Community 114"
Cohesion: 0.22
Nodes (6): Clipboard insertion strategy. Writes text to the system clipboard and sends the…, Text insertion strategies., paste_modifier_key(), macOS-specific helpers for text insertion. Provides platform detection,…, Return the paste modifier key for macOS. Returns: ``"cmd"`` for macOS., Unit tests for keyboard and clipboard insertion strategies. Tests cover…

### Community 115 - "Community 115"
Cohesion: 0.22
Nodes (6): Return sessions left 'open' by a crashed process, for the prompt., ObserverSession, A recording session. Attributes: id: Database row id. uuid: Stable external…, Close the current session. Returns the closed session, or None., FakeStore, Minimal store stand-in. We never need the full ObserverStore here.

### Community 116 - "Community 116"
Cohesion: 0.33
Nodes (8): _probe_compute_type(), Return the best CTranslate2 compute type supported on ``device``. Queries…, Unit tests for the auto compute-type probe (Phase E, PE-03)., test_cpu_falls_back_to_float32(), test_cpu_prefers_int8(), test_cuda_falls_through_to_int8_when_float16_unsupported(), test_cuda_prefers_float16(), test_probe_failure_returns_safe_default()

### Community 118 - "Community 118"
Cohesion: 0.25
Nodes (8): _provider_with_prompt(), Tests for R9: mtime-keyed cache of the custom cleanup prompt file. Verifies…, Two rewrite() calls with the same mtime should open the file only once., Touching the file with newer content + newer mtime causes the next call to re-…, A missing custom_prompt_path raises CleanupError with the same message prefix…, test_missing_prompt_raises_cleanup_error(), test_prompt_cache_invalidated_by_mtime(), test_prompt_read_once_per_mtime()

### Community 119 - "Community 119"
Cohesion: 0.29
Nodes (4): observer config (v0.4.0), Four Keyframe Triggers, speech_onset Trigger (D9), config.streaming.yaml example: streaming ASR + per-app cleanup profiles via context + voice commands + adaptive vocabulary

### Community 120 - "Community 120"
Cohesion: 0.25
Nodes (8): First-time Setup Documentation, Hot-Reload vs Restart, AgentVoca README, Adaptive Vocabulary (v2/v0.3.6), Context-Aware Formatting (v2), Setup Wizard (v0.3.5), Live Streaming Transcription (v2/v0.3.6), Voice Commands (v2)

### Community 121 - "Community 121"
Cohesion: 0.25
Nodes (5): Write ``text`` to clipboard and send paste hotkey. Args: text: The text to…, Undo clipboard paste by sending Ctrl+Z / Cmd+Z. Returns: True if the undo was…, get_input_executor(), Return the single shared input executor, creating it on first use and replacing…, Type the text at the current cursor position. Args: text: The text to insert.…

### Community 122 - "Community 122"
Cohesion: 0.25
Nodes (6): Single-worker executor serializing all OS input injection. pyautogui (and the…, Tests for R11: a single shared executor serializes pyautogui/pyperclip.…, Both strategies route through the same single-worker executor., Stubs that record start/end timestamps: the two calls' intervals must not…, test_concurrent_insert_and_undo_do_not_interleave(), test_keyboard_and_clipboard_share_executor()

### Community 123 - "Community 123"
Cohesion: 0.25
Nodes (5): ExporterCoordinator, Path, Bundle-aware exporter coordinator (Track 3, OBS-28). The concrete exporters…, Wraps the per-format exporter factory and runs it per-session. The controller…, Build exporters for ``bundle`` and run them. Args: compiled: The compiled…

### Community 124 - "Community 124"
Cohesion: 0.33
Nodes (4): Context manager that measures elapsed time for a pipeline stage. Usage: timer =…, Measure the duration of a pipeline stage. Args: stage: Name of the stage (e.g.,…, Convenience: call timer(stage) instead of timer.measure(stage)., StageTimer

### Community 125 - "Community 125"
Cohesion: 0.33
Nodes (6): event_bus(), fixture, Shared pytest fixtures for the agentvoca test suite., Return a fresh EventBus for each test., Return a ProviderRegistry with all built-in providers registered., registry()

### Community 126 - "Community 126"
Cohesion: 0.33
Nodes (6): _make_jpeg_bytes(), Path, Fixture-session generator for Observer mode (v0.4.0). Unblocks Track 3 to work…, Build a tiny valid JPEG so the blob path is non-empty. Real keyframes will be…, Write a real JPEG into the session's blob subdirectory. Returns the relative…, _write_blob()

### Community 127 - "Community 127"
Cohesion: 0.33
Nodes (6): _force_offscreen_qt(), fixture, qapp(), Shared fixtures for integration tests in this directory., Force the offscreen Qt platform so the wizard renders in CI., Return a single QApplication for the duration of the test.

### Community 128 - "Community 128"
Cohesion: 0.47
Nodes (6): CI Workflow, Performance & Latency Documentation, Benchmark Harness (scripts/benchmark.py), Latency Budgets (v2), v0.3.6 Performance Optimizations (R2–R6), Dedicated VAD Worker Thread (R2)

### Community 129 - "Community 129"
Cohesion: 0.33
Nodes (3): Any, Call the engine synchronously. Returns the (boxes, txts, scores) tuple., Return the cached engine, building it on first call. The import is inside this…

### Community 130 - "Community 130"
Cohesion: 0.47
Nodes (5): mock_config(), asyncio, fixture, test_adaptive_vocabulary_learning(), test_voice_command_newline()

### Community 131 - "Community 131"
Cohesion: 0.40
Nodes (5): Adaptive vocabulary learning (v2), Per-app context engine (v2), CorrectionLearnedEvent, Voice editing commands (v2), Context, Commands & Adaptive Vocabulary

### Community 132 - "Community 132"
Cohesion: 0.40
Nodes (4): Screenshot-to-Text Documentation, Vision Anchor Phrases, Local VLM (GOT-OCR 2.0) — Planned, Screenshot-to-Text (v3/v0.3.6)

### Community 133 - "Community 133"
Cohesion: 0.40
Nodes (3): model_validator, Resolve ``compile.output_dir`` against ``storage.dir`` when empty. The empty…, Check that api_key_env vars are set when a provider is remote. A provider is…

### Community 134 - "Community 134"
Cohesion: 0.40
Nodes (3): RuntimeError, Open a new session. Fails if one is already open., The controller bound to this page (never None inside a wizard/window).

### Community 135 - "Community 135"
Cohesion: 0.40
Nodes (3): AsyncClient, Initialize the provider with config. Args: config: The cleanup configuration…, Construct the shared ``httpx.AsyncClient``. Exposed as a seam so tests can…

### Community 136 - "Community 136"
Cohesion: 0.30
Nodes (3): Match, Return the original vocabulary term or mapped term for a match., Apply vocabulary substitution to the given text. Terms are matched as case-…

### Community 137 - "Community 137"
Cohesion: 0.40
Nodes (5): fixture, Path, The OBS-9 fixture (3 blocks) must split into three blocks. The fixture writes a…, temp_store_root(), test_fixture_session_block_count_is_three()

### Community 138 - "Community 138"
Cohesion: 0.40
Nodes (3): parametrize, The ``open_settings`` event does not change state from any state., TestOpenSettingsNonBlocking

### Community 146 - "Community 146"
Cohesion: 0.67
Nodes (3): audio config section, invalid_sample_rate.yaml fixture, invalid_silence_timeout.yaml fixture

## Knowledge Gaps
- **42 isolated node(s):** `agentvoca`, `build.sh script`, `release.sh script`, `Per-app context engine (v2)`, `Voice editing commands (v2)` (+37 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `EventBus` connect `Community 6` to `Community 0`, `Community 1`, `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 130`, `Community 8`, `Community 9`, `Community 10`, `Community 11`, `Community 14`, `Community 17`, `Community 23`, `Community 25`, `Community 27`, `Community 28`, `Community 39`, `Community 42`, `Community 44`, `Community 46`, `Community 49`, `Community 50`, `Community 62`, `Community 66`, `Community 70`, `Community 71`, `Community 81`, `Community 82`, `Community 95`, `Community 106`, `Community 113`, `Community 125`?**
  _High betweenness centrality (0.132) - this node is a cross-community bridge._
- **Why does `Orchestrator` connect `Community 0` to `Community 1`, `Community 2`, `Community 130`, `Community 4`, `Community 5`, `Community 6`, `Community 8`, `Community 9`, `Community 10`, `Community 11`, `Community 144`, `Community 23`, `Community 26`, `Community 27`, `Community 28`, `Community 37`, `Community 41`, `Community 58`, `Community 59`, `Community 62`, `Community 64`, `Community 68`, `Community 70`, `Community 71`, `Community 77`, `Community 79`, `Community 81`, `Community 82`, `Community 85`, `Community 95`, `Community 105`, `Community 113`?**
  _High betweenness centrality (0.109) - this node is a cross-community bridge._
- **Why does `FullConfig` connect `Community 11` to `Community 0`, `Community 1`, `Community 2`, `Community 4`, `Community 133`, `Community 5`, `Community 6`, `Community 8`, `Community 9`, `Community 10`, `Community 12`, `Community 13`, `Community 14`, `Community 19`, `Community 20`, `Community 23`, `Community 27`, `Community 44`, `Community 45`, `Community 46`, `Community 48`, `Community 50`, `Community 62`, `Community 66`, `Community 70`, `Community 71`, `Community 81`, `Community 82`, `Community 95`, `Community 113`?**
  _High betweenness centrality (0.079) - this node is a cross-community bridge._
- **Are the 123 inferred relationships involving `EventBus` (e.g. with `_MockASR` and `_MockCleanup`) actually correct?**
  _`EventBus` has 123 INFERRED edges - model-reasoned connections that need verification._
- **Are the 101 inferred relationships involving `FullConfig` (e.g. with `_MockASR` and `_MockCleanup`) actually correct?**
  _`FullConfig` has 101 INFERRED edges - model-reasoned connections that need verification._
- **Are the 103 inferred relationships involving `Orchestrator` (e.g. with `_MockASR` and `_MockCleanup`) actually correct?**
  _`Orchestrator` has 103 INFERRED edges - model-reasoned connections that need verification._
- **Are the 84 inferred relationships involving `ProviderRegistry` (e.g. with `_MockASR` and `_MockCleanup`) actually correct?**
  _`ProviderRegistry` has 84 INFERRED edges - model-reasoned connections that need verification._