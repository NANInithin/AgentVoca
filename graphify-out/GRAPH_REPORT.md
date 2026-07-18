# Graph Report - .  (2026-07-18)

## Corpus Check
- 186 files · ~95,271 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2638 nodes · 5740 edges · 175 communities (132 shown, 43 thin omitted)
- Extraction: 62% EXTRACTED · 38% INFERRED · 0% AMBIGUOUS · INFERRED: 2188 edges (avg confidence: 0.61)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Orchestrator, Overlay & Events
- ASR Providers
- Cancel Semantics & Registry
- Event Types (bus)
- UI Helpers & Shell Snippets
- Documentation Concepts
- EventBus & Config Core
- Snippet Expansion
- App State Machine
- Screenshot Capture (v3)
- Hotkey Presets
- Config Controller
- Per-App Cleanup Profiles
- Benchmark & Mocks
- Config Loader Tests
- Vision Pipeline Integration
- Warm-up & Insertion
- Rules-Based Cleanup
- Setup Persistence
- Config Schema Tests
- Model Catalog
- Streaming Pipeline Integration
- Lenient Config Loader
- Device Probe
- VAD Worker Capture
- Cross-cutting Utilities
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
- Community 161
- Community 162
- Community 163
- Community 164
- Community 171

## God Nodes (most connected - your core abstractions)
1. `EventBus` - 195 edges
2. `Orchestrator` - 168 edges
3. `FullConfig` - 145 edges
4. `ProviderRegistry` - 145 edges
5. `InsertionConfig` - 133 edges
6. `CleanupConfig` - 132 edges
7. `ASRConfig` - 121 edges
8. `TranscriptSegment` - 93 edges
9. `RecordingStoppedEvent` - 92 edges
10. `ConfigError` - 84 edges

## Surprising Connections (you probably didn't know these)
- `provider()` --calls--> `OpenAICompatibleCleanupProvider`  [INFERRED]
  tests/unit/test_openai_cleanup.py → src/agentvoca/cleanup/openai_compatible.py
- `fw_config()` --calls--> `ASRConfig`  [INFERRED]
  tests/unit/test_asr_adapters.py → src/agentvoca/config/schema.py
- `openai_config()` --calls--> `ASRConfig`  [INFERRED]
  tests/unit/test_asr_adapters.py → src/agentvoca/config/schema.py
- `config()` --calls--> `CleanupConfig`  [INFERRED]
  tests/unit/test_openai_cleanup.py → src/agentvoca/config/schema.py
- `loop_thread()` --calls--> `AsyncLoopThread`  [INFERRED]
  tests/unit/test_async_loop.py → src/agentvoca/core/async_loop.py

## Import Cycles
- 1-file cycle: `src/agentvoca/asr/faster_whisper.py -> src/agentvoca/asr/faster_whisper.py`

## Hyperedges (group relationships)
- **AgentVoca provider plug-in system** — concept_provider_registry, concept_asr_provider_base, concept_cleanup_provider_base, concept_insertion_strategy_base, concept_faster_whisper_provider, concept_openai_compatible_asr, concept_rules_cleanup, concept_openai_compatible_cleanup, concept_keyboard_insertion, concept_clipboard_insertion, concept_vision_provider, concept_domain_error_pattern, concept_lazy_provider_imports [EXTRACTED 0.95]
- **v2 intelligence layer (opt-in)** — concept_streaming_asr, concept_context_engine, concept_voice_commands, concept_adaptive_vocabulary, concept_undo_hotkey, concept_warm_up, concept_correction_learned_event [EXTRACTED 0.90]
- **v0.3.6 performance/stability pass** — concept_vad_worker_thread, concept_persistent_http_client, concept_parallel_vision_extraction, concept_serialized_input, concept_o1_vocab_lookup, concept_bulk_vocab_merges, concept_lazy_provider_imports, concept_prompt_cache [EXTRACTED 0.95]
- **Track 1: Audio & Streaming items implemented on branch v0.3.6-audio-streaming** — r1_delete_duplicate_vad, r2_vad_worker_thread, r3_stop_recording_offthread, r4_streaming_asr_on_memory, r5_chunker_buffer_compaction, r6_cancel_wiring, r7_remove_dead_frame_attrs [EXTRACTED 1.00]
- **Track 2: I/O, Text & Startup items implemented on branch v0.3.6-io-text-startup** — r8_persistent_http_clients, r9_prompt_path_cache, r10_parallel_vision, r11_shared_input_executor, r12_o1_casing_lookup, r13_bulk_mapping_merge, r14_lazy_provider_imports [EXTRACTED 1.00]
- **v0.3.6 Threading-model contract: audio callback does near-zero work, Qt main triggers hotkeys, asyncio loop owns pipeline + chunker + VAD worker rendezvous** — threading_model_three_threads, r1_delete_duplicate_vad, r2_vad_worker_thread, r3_stop_recording_offthread, r6_cancel_wiring [INFERRED 0.85]

## Communities (175 total, 43 thin omitted)

### Community 0 - "Orchestrator, Overlay & Events"
Cohesion: 0.04
Nodes (76): Place the overlay in the top-right corner of the screen., Emit the state change onto the GUI thread., Emit the transcript text onto the GUI thread., Emit a partial transcript onto the GUI thread., Emit warm-up completion onto the GUI thread., Update the state label when the app state changes (GUI thread)., Update the transcript display (GUI thread)., Update the transcript display with a live partial (GUI thread).          Partial (+68 more)

### Community 1 - "ASR Providers"
Cohesion: 0.04
Nodes (33): _MockASR, ASR provider that returns fixed text after an optional simulated delay., ASRProvider, Abstract base class for automatic speech recognition providers.      Implementat, Return True if stream_transcribe yields true interim partials.          Default, Preload models / prime connections. Must not raise.          Default no-op for p, Return True if the provider can accept requests right now.          This should, Transcribe a complete audio buffer.          Always returns a final segment (``i (+25 more)

### Community 2 - "Cancel Semantics & Registry"
Cohesion: 0.05
Nodes (40): ASRConfig, ASR provider configuration., AsyncLoopThread, A single asyncio event loop owned by a dedicated daemon thread., AudioChunkEvent, PartialTranscriptEvent, Published by the AudioChunker during recording (Chunker → Bus).      Attributes:, Published when a streaming partial transcript is available.      Attributes: (+32 more)

### Community 3 - "Event Types (bus)"
Cohesion: 0.04
Nodes (40): CommandRecognizedEvent, ContextResolvedEvent, CorrectionLearnedEvent, Published when the context engine resolves the current context.      Attributes:, Published when a voice command is recognized.      Attributes:         action: T, Published when a correction is learned by the adaptive vocab.      Attributes:, Published when vision extraction completes for the captured screenshots (v3)., VisionExtractedEvent (+32 more)

### Community 4 - "UI Helpers & Shell Snippets"
Cohesion: 0.05
Nodes (38): QGroupBox, all_snippets(), bash_snippet(), EnvStatus, fish_snippet(), powershell_snippet(), Env-var helper — the UI's "Set this API key now" affordance.  AgentVoca never wr, Return the most useful persistence snippet for the host OS.      Args:         n (+30 more)

### Community 5 - "Documentation Concepts"
Cohesion: 0.05
Nodes (58): CI Workflow, Adaptive vocabulary learning (v2), Anchor-based splicing, api_key_env indirection, ASRProvider abstract base, Pipeline benchmark harness, Bulk adaptive vocab promotion (v0.3.6 R13), CleanupProvider abstract base (+50 more)

### Community 6 - "EventBus & Config Core"
Cohesion: 0.06
Nodes (32): QWidget, FullConfig, Top-level configuration model combining all sections., EventBus, Synchronous-first event bus for the agentvoca pipeline.  Handlers are called in, Simple synchronous event bus.      Modules subscribe to event types and publish, Register a persistent event loop for async handlers.          When set, coroutin, Publish an event to all registered handlers.          Synchronous handlers are c (+24 more)

### Community 7 - "Snippet Expansion"
Cohesion: 0.05
Nodes (31): _build_pattern(), _load_snippets(), Path, Pattern, Snippet expansion module.  Loads a snippets YAML file (trigger → expansion) and, Initialize the snippet expander.          Args:             path: Optional path, The trigger → expansion mapping (read-only)., True if no snippets are registered. (+23 more)

### Community 8 - "App State Machine"
Cohesion: 0.06
Nodes (42): Return the current application state., Force-reset the machine to a given state., AppState, config_exists(), config_path(), load_state(), mark_first_run_complete(), Any (+34 more)

### Community 9 - "Screenshot Capture (v3)"
Cohesion: 0.08
Nodes (23): _png_dimensions(), Screenshot capture using OS-native snip tools (v3).  The capturer invokes the pl, Block until no captures are in flight, or until ``timeout`` elapses.          Re, Return all captured screenshots in order and clear the queue., Return True if any captures are queued or in flight., Discard any queued screenshots (e.g. at the start of a recording)., Run the platform snip and return PNG bytes, or None if cancelled., Return (width, height) for PNG bytes, or (None, None) if not parseable. (+15 more)

### Community 10 - "Hotkey Presets"
Cohesion: 0.07
Nodes (28): action_by_field(), find_preset(), HotkeyAction, HotkeyPreset, labels_for_dropdown(), Hotkey preset catalogue.  Per the v0.3.5 UI decision, the hotkey fields expose a, Return the config value for a dropdown label, or ``CUSTOM`` sentinel.      Retur, Return the warning string for ``value``, or None if it has none. (+20 more)

### Community 11 - "Config Controller"
Cohesion: 0.07
Nodes (26): ConfigController, defaults_controller(), _diff_paths(), _join(), Any, Path, ConfigController — the wizard and settings window's source of truth.  A ``Config, Replace the entire draft (used by "Restore defaults" and similar). (+18 more)

### Community 12 - "Per-App Cleanup Profiles"
Cohesion: 0.07
Nodes (20): ProfileResolver, Resolves an app name to a cleanup style profile.      Args:         profiles: A, Return a copy of the raw mapping (profile name → style)., Resolve an app name to a style profile.          Args:             app_name: The, Unit tests for the ProfileResolver context engine component., With no profiles, resolve should return None., Exact app name match should return the configured style., When no pattern matches, the '*' fallback should be used. (+12 more)

### Community 13 - "Benchmark & Mocks"
Cohesion: 0.09
Nodes (23): _build_mock_config(), main(), _make_orchestrator(), _MockCleanup, _MockInsertion, _percentile(), _print_summary(), Pipeline latency benchmark harness (Phase E, PE-01).  Replays audio through the (+15 more)

### Community 14 - "Config Loader Tests"
Cohesion: 0.09
Nodes (21): load_config_from_dict(), Load config from an in-memory dictionary (useful for testing).      Environment, _load_fixture(), A full config with all fields should load cleanly., A remote provider with api_key_env=null should not require the env var., A remote provider with a set api_key_env should pass., A remote provider with a missing api_key_env should fail., A remote cleanup provider with a missing api_key_env should fail. (+13 more)

### Community 15 - "Vision Pipeline Integration"
Cohesion: 0.09
Nodes (14): _config(), FakeCapturer, FakeVision, _make_orch(), MockCleanup, MockInsertion, Integration tests for the v3 vision splice in the orchestrator pipeline., Minimal capturer stub implementing the orchestrator's interface. (+6 more)

### Community 16 - "Warm-up & Insertion"
Cohesion: 0.08
Nodes (14): CleanupContext, Context passed to a cleanup provider.      Attributes:         style: Cleanup st, _make_config(), _make_registry(), _MockCleanup, Integration tests for insertion strategies via the full pipeline.  Verifies that, Keyboard strategy inserts ASCII text via pyautogui.typewrite., recording_event() (+6 more)

### Community 17 - "Rules-Based Cleanup"
Cohesion: 0.07
Nodes (22): Deterministic rules-based cleanup provider.  Performs basic filler removal, capi, Cleanup provider using deterministic Python rules., No-op: rules-based cleanup has no model to load or pool to prime., Return the registry key for this provider., Always available (no dependencies)., Return True if 4 or more technical tokens are detected., Clean transcript using deterministic rules., RulesCleanupProvider (+14 more)

### Community 18 - "Setup Persistence"
Cohesion: 0.13
Nodes (27): _backup_existing(), _ensure_parent(), load_from_disk(), Any, Path, Persistence helpers for the interactive setup wizard / settings window.  The wiz, Backup + write helper shared by the two save paths., Load and validate a YAML config from disk.      Thin wrapper around ``load_confi (+19 more)

### Community 19 - "Config Schema Tests"
Cohesion: 0.11
Nodes (12): AppConfig, Snippet expansion settings., Application-level settings., SnippetsConfig, Tests for config schema and loader.  Covers all validation rules from Section 5., Extra fields in YAML should be ignored (strict=False)., Numeric values in place of strings should be coerced., TestDefaults (+4 more)

### Community 20 - "Model Catalog"
Cohesion: 0.18
Nodes (24): ModelCatalog, ModelCatalogError, Raised when the catalog cannot be fetched.      The wizard shows the message in, Fetches and caches the list of models available at an endpoint.      Usage (sync, _FakeResponse, _openai_shape(), Unit tests for the model catalog controller.  The catalog is a thin wrapper arou, Some self-hosted servers (Ollama) return a bare JSON list. (+16 more)

### Community 21 - "Streaming Pipeline Integration"
Cohesion: 0.08
Nodes (12): event_bus(), MockCleanup, MockInsertion, MockNonStreamingASR, non_streaming_config(), Integration tests for the streaming dictation pipeline.  Tests cover: - Mock str, Simple mock cleanup that uppercases text., Mock insertion that always succeeds. (+4 more)

### Community 22 - "Lenient Config Loader"
Cohesion: 0.13
Nodes (24): _construct_lenient(), _expand_env_vars(), load_config_lenient(), _load_yaml(), Any, Path, Config loader: YAML parsing, environment variable expansion, validation.  Usage:, Build a ``FullConfig`` without running the model validators.      The pydantic ` (+16 more)

### Community 23 - "Device Probe"
Cohesion: 0.11
Nodes (19): DeviceEntry, DeviceProbe, _devices_module(), Device probe — thin wrapper around ``audio.devices`` for the UI layer.  The wiza, Return at least the 'default' entry when PortAudio is unavailable., Return the cached entries, refreshing once on first call., Resolve a config value to a concrete device info dict, or None.          Used by, Return ``agentvoca.audio.devices``, importing lazily.      Imported lazily so he (+11 more)

### Community 24 - "VAD Worker Capture"
Cohesion: 0.11
Nodes (20): _drain_worker(), _make_block(), _make_indata(), ndarray, Tests for ``AudioCapture`` VAD inference on a dedicated worker thread (R2).  Cov, R2: the VAD worker thread joins cleanly on stream close., R2: ``start_recording`` clears leftover blocks from a prior recording., R2: callback p99 stays under real-time even when VAD is slow. (+12 more)

### Community 25 - "Cross-cutting Utilities"
Cohesion: 0.08
Nodes (14): BoundLogger, Minimal transparent status overlay showing recording state and interim transcrip, Audio capture using sounddevice.  Captures microphone audio with configurable de, Audio chunker — emits raw audio deltas during recording.  The chunker feeds inco, Voice activity detection wrapper around silero-vad.  Wraps the silero-vad librar, App → style profile resolution.  Maps detected application names to cleanup styl, Persistent asyncio event loop running on a background thread.  The desktop app's, Orchestrator — coordinates the voice dictation pipeline.  The orchestrator owns (+6 more)

### Community 26 - "Community 26"
Cohesion: 0.14
Nodes (12): QCloseEvent, QWidget, Push every page's UI state back into the controller draft., Reload every page from the controller and update the banner., Tabbed editor for ``FullConfig`` with apply / discard / restart banner., SettingsWindow, Path, Integration tests for the tabbed SettingsWindow.  Drives the window headlessly: (+4 more)

### Community 27 - "Community 27"
Cohesion: 0.14
Nodes (10): InsertionConfig, Text insertion configuration., ClipboardInsertionStrategy, Inserts text by writing to clipboard and sending paste hotkey.      Args:, Clipboard strategy writes to clipboard and sends paste hotkey., TestClipboardInsertion, Tests for ClipboardInsertionStrategy., TestClipboardInsertion (+2 more)

### Community 28 - "Community 28"
Cohesion: 0.14
Nodes (23): all_known_paths(), _classify(), is_hot_field(), is_restart_field(), partition(), Restart policy — classify every FullConfig field as hot-apply or restart.  A "ho, Classify ``path`` as ``"hot"``, ``"restart"``, or ``None`` (unknown).      ``_di, Return True if the field at dotted ``path`` requires an app restart. (+15 more)

### Community 29 - "Community 29"
Cohesion: 0.08
Nodes (13): Tests for the vocabulary dictionary module., A vocabulary term should not match inside another word., The terms property returns a copy, not the internal list., A vocabulary term matched case-insensitively is preserved with its original casi, If the term is already correctly cased, it stays the same., Multiple terms are all matched., Terms with regex special characters are escaped., Terms from a file are loaded correctly. (+5 more)

### Community 30 - "Community 30"
Cohesion: 0.13
Nodes (17): Vision / screenshot-to-text configuration (v3).      When enabled, a dedicated h, VisionConfig, OpenAICompatibleVisionProvider, AsyncClient, OpenAI-compatible vision provider (v3).  Sends a screenshot plus the spoken inst, Vision provider using an OpenAI-compatible chat-completions API., Initialize the provider with config.          Args:             config: The visi, Construct the shared ``httpx.AsyncClient``.          Exposed as a seam so tests (+9 more)

### Community 31 - "Community 31"
Cohesion: 0.12
Nodes (19): AnchorSplicer, Match, Anchor-phrase splicing for screenshot extractions (v3).  When the user dictates, Splices ordered extractions into a transcript at anchor phrases., Initialize with a phrase list, falling back to the built-in defaults.          A, Return non-overlapping anchor matches in left-to-right order., Splice extractions into the transcript.          Args:             transcript: T, Unit tests for the vision anchor splicer (v3). (+11 more)

### Community 32 - "Community 32"
Cohesion: 0.25
Nodes (22): v0.3.6 Performance & Reliability Pass (rev 2, rescoped proposal), v0.3.6 Agent 1 Execution Plan: Audio & Streaming Track (R1-R7), v0.3.6 Agent 2 Execution Plan: I/O, Text & Startup Track (R8-R14), pyautogui thread-safety constraint: pyautogui is not thread-safe so concurrent insert+undo interleave keystrokes, requiring a single shared single-worker executor (not per-class pools), R10: Parallelize multi-screenshot vision extraction via asyncio.gather (order-preserving, per-shot error isolation), R11: One module-level single-worker ThreadPoolExecutor serializing all pyautogui/pyperclip calls (shared between keyboard and clipboard strategies), R12: O(1) casing lookup in VocabularyDictionary via first-wins lowercased dict rebuilt in _rebuild(), R13: Batch the learned-mapping merge via new add_mappings() bulk API (one pattern rebuild per merge instead of per mapping) (+14 more)

### Community 33 - "Community 33"
Cohesion: 0.11
Nodes (12): QAction, Update the tray icon to reflect the given state., Emit the state change onto the GUI thread., Update icon and tooltip for the given state (GUI thread)., Action that triggers the settings window., Action that triggers the setup wizard., Action that quits the application., Show a balloon notification from the tray.          Safe to call from any thread (+4 more)

### Community 34 - "Community 34"
Cohesion: 0.12
Nodes (11): Publish ``VADSpeechEvent`` when the speech state flips.          Args:, Run inference once and emit a transition event.          Args:             audio, Voice activity detector using silero-vad.      Args:         event_bus: Event bu, Release VAD resources., Return True if the VAD model is loaded., Check whether an audio chunk contains speech.          Args:             audio_c, VAD, Published when VAD detects speech or silence.      Attributes:         is_speech (+3 more)

### Community 35 - "Community 35"
Cohesion: 0.12
Nodes (15): CountingClient, _provider(), Tests for R8: persistent HTTP client in OpenAICompatibleCleanupProvider.  Verifi, ``shutdown()`` calls aclose() and a second call does not raise., Providers without a ``shutdown`` attribute (e.g. mocks, other     adapters) are, AsyncClient-like stand-in: counts constructions, records posts., A subclass that uses CountingClient for its shared HTTP client., Build a provider with a counting client plugged in via the seam. (+7 more)

### Community 36 - "Community 36"
Cohesion: 0.12
Nodes (12): AdaptiveStore, Path, Tracks user corrections and promotes frequently corrected terms to the vocabular, Save learned terms and mappings to the persistence file., Return the current list of learned vocabulary terms., Return the current list of learned vocabulary mappings., Initialize the adaptive store.          Args:             learned_vocab_path: Pa, Load learned terms from the persistence file. (+4 more)

### Community 37 - "Community 37"
Cohesion: 0.17
Nodes (13): _build_config(), _build_registry(), _empty_extract(), _FakeCapturer, _PassThroughSplicer, Tests for R10: parallel multi-screenshot vision extraction.  Verifies that ``_ap, 3 shots × 300ms must finish in well under 900ms (parallel)., If one of three shots raises VisionError, the other two still     splice — and i (+5 more)

### Community 38 - "Community 38"
Cohesion: 0.14
Nodes (7): MockInsertionStrategy, Tests for the ProviderRegistry class., InsertionConfig.strategy is a Literal['keyboard','clipboard'];          so we re, Each registry namespace is independent., Use a valid literal strategy key that matches registration., Minimal InsertionStrategy stub for testing., TestProviderRegistry

### Community 39 - "Community 39"
Cohesion: 0.14
Nodes (14): CountingClient, _ok_response(), _provider(), Tests for R8: persistent HTTP client in OpenAICompatibleVisionProvider.  Verifie, AsyncClient-like stand-in: counts constructions, records posts., Subclass that uses CountingClient for its shared HTTP client., Build a vision provider backed by a counting client., Three ``extract()`` calls must construct the client exactly once. (+6 more)

### Community 40 - "Community 40"
Cohesion: 0.11
Nodes (9): QWizardPage, AppBasicsPage, App basics page — language hint, recording mode, debug toggle., FinishPage, Finish page — review the diff before saving., _as_wizard_page(), QWidget, Setup wizard — ``QWizard`` composing the page widgets in order.  The wizard auto (+1 more)

### Community 41 - "Community 41"
Cohesion: 0.15
Nodes (10): AudioCapture, Begin capturing audio into the internal buffer., Return True if currently recording., Dedicated daemon thread: silero inference + speech-state cache update., Captures microphone audio and emits events on the event bus.      Args:, Open the audio input stream.          Raises:             AudioError: If the sel, AudioError, Raised when audio capture or playback fails. (+2 more)

### Community 42 - "Community 42"
Cohesion: 0.15
Nodes (13): OpenAICompatibleCleanupProvider, OpenAI-compatible LLM cleanup provider.  Sends transcripts to any OpenAI-compati, Return True if endpoint and API key (if required) are set., Cleanup provider using an OpenAI-compatible LLM API., Close the pooled HTTP client. Safe to call more than once., Prime the HTTP connection pool with a lightweight health check.          Sends a, Return the registry key for this provider., _patch_client() (+5 more)

### Community 43 - "Community 43"
Cohesion: 0.23
Nodes (18): load_controller(), Build a ``ConfigController`` from a YAML file on disk.      Falls back to the v1, Path, Tests for the ConfigController., A field that violates the schema raises during update_section., Drift between dict and pydantic state is caught by validate()., test_controller_changed_paths_include_top_level_for_dict_changes(), test_controller_falls_back_to_defaults_when_missing() (+10 more)

### Community 44 - "Community 44"
Cohesion: 0.12
Nodes (10): RuntimeError, ConfigPage, Base class for wizard and settings-window pages.  Every page is a ``QWidget`` th, Base class for every page in the wizard and settings window.      Subclasses ove, Attach or re-attach a controller and refresh the UI., The controller bound to this page (never None inside a wizard/window)., Build the page's UI. Subclasses should populate ``self._body``.          The def, Sync the UI from the controller's draft. Override in subclasses. (+2 more)

### Community 45 - "Community 45"
Cohesion: 0.12
Nodes (11): ABC, ASR provider abstract base class.  All ASR adapters must subclass ``ASRProvider`, Provider registry for ASR, cleanup, and insertion modules.  The registry maps st, ABC, Vision provider abstract base class (v3).  All vision/VLM adapters must subclass, Abstract base class for screenshot-to-text vision providers.      Implementation, Prime connection pool / load local model. Must not raise. Default no-op., Return the registry key for this provider. (+3 more)

### Community 46 - "Community 46"
Cohesion: 0.14
Nodes (9): load_config(), Load, expand, and validate a YAML config file.      Steps:         1. Read and p, config.example.yaml should load without errors., examples/config.local.yaml should load without errors., examples/config.openai.yaml should load without errors., examples/config.ollama.yaml should load without errors., A YAML file that parses to a string instead of a dict., Load the valid_minimal fixture from file. (+1 more)

### Community 47 - "Community 47"
Cohesion: 0.22
Nodes (7): AudioConfig, Check that api_key_env vars are set when a provider is remote.          A provid, Audio capture settings., ConfigError, Raised when configuration loading or validation fails., TestAudioValidation, TestInsertionStrategyValidation

### Community 48 - "Community 48"
Cohesion: 0.18
Nodes (7): Pure state machine for the dictation pipeline.      Usage::          sm = StateM, Return the current state., StateMachine, §6.2 transitions starting from ``idle``., §6.2 transitions starting from ``recording``., TestTransitionsFromIdle, TestTransitionsFromRecording

### Community 49 - "Community 49"
Cohesion: 0.14
Nodes (8): _asr_endpoint_warning(), AsrPage, QComboBox, ASR (speech-to-text) page — provider, model, endpoint, API key., Show/hide the 'this host can't do speech-to-text' warning., # NOTE: OpenRouter is intentionally NOT in this list. It added a dedicated, Kick off an async model-list fetch for the current endpoint + key., Return a warning if ``endpoint`` is a known chat-only (no-STT) host.

### Community 50 - "Community 50"
Cohesion: 0.17
Nodes (13): Map a ``QWizard`` page id to the index in ``self._pages``., Force a full rebind of every page. Used after external controller mutations., The full first-run wizard with eight pages + welcome + review., SetupWizard, Path, Integration tests for the setup wizard.  Drives the wizard headlessly with the o, A page the user has not visited must keep whatever the controller had     in it., Regression: typing into the ASR page and clicking Next used to clobber     the t (+5 more)

### Community 51 - "Community 51"
Cohesion: 0.12
Nodes (10): config(), event_bus(), MockCleanupProvider, MockInsertionStrategy, pipeline(), Integration test: full pipeline from RecordingStoppedEvent to InsertionCompleteE, Mock insertion that always succeeds., Mock cleanup that uppercases the transcript. (+2 more)

### Community 52 - "Community 52"
Cohesion: 0.14
Nodes (9): _ProviderEntry, Construct and return an ASR provider from config.          Args:             con, Construct and return a cleanup provider from config.          Args:, Construct and return an insertion strategy from config.          Args:, Construct and return a vision provider from config.          Args:             c, Resolve a lazily-registered ``"module:Class"`` path to a class., ProviderNotFoundError, Raised when a requested provider is not registered. (+1 more)

### Community 53 - "Community 53"
Cohesion: 0.16
Nodes (10): get_default_input_device(), list_input_devices(), Audio device enumeration and selection.  Wraps sounddevice to enumerate input de, List all audio input devices available on the system.      Returns:         A li, Return the default input device info, or None if none available.      Returns:, Select an audio input device by name or return the default.      Args:         d, select_device(), Unit tests for audio capture, devices, and VAD modules.  Tests cover device enum (+2 more)

### Community 54 - "Community 54"
Cohesion: 0.15
Nodes (15): Load the silero-vad model.          Raises:             VADError: If the model f, AgentVocaError, CaptureError, HotkeyError, InsertionError, ProviderNotAvailableError, Exception, Domain exception hierarchy for the AgentVoca application.  All modules surface e (+7 more)

### Community 55 - "Community 55"
Cohesion: 0.13
Nodes (15): HotkeyEvent, Published when a global hotkey is pressed.      Attributes:         action: The, Single-worker executor serializing all OS input injection.  pyautogui (and the c, Best-effort shutdown; wait=False so a stuck typewrite can't hang exit.      A su, shutdown_input_executor(), _build_registry(), main(), Entry point for the agentvoca dictation app.  Run with::      python -m agentvoc (+7 more)

### Community 56 - "Community 56"
Cohesion: 0.17
Nodes (13): _FakeResponse, Path, Integration tests for the "Fetch models…" flow on the ASR / Cleanup pages.  Two, Regression: OpenRouter now has an STT endpoint, so it must NOT warn., Regression: picking a "(free)"-tagged entry must not save the label., Pump the Qt event loop until ``predicate()`` is true or we time out., Regression: the fetch callback must actually populate the combobox., A chat-only host (Anthropic) must surface a visible no-STT warning. (+5 more)

### Community 57 - "Community 57"
Cohesion: 0.17
Nodes (7): AudioChunker, Clear the internal buffer without stopping., Emits raw audio delta ``AudioChunkEvent`` s during recording.      Args:, True if the chunker is actively emitting chunks., Feed incoming audio data into the chunker buffer.          Args:             dat, Start/stop/reset behavior., TestChunkerLifecycle

### Community 58 - "Community 58"
Cohesion: 0.13
Nodes (9): CleanupProvider, ABC, Cleanup provider abstract base class.  All cleanup/rewriting adapters must subcl, Abstract base class for transcript cleanup providers.      Implementations must, Return True if the provider can clean partial segments coherently.          Defa, Prime connection pool / load local model. Must not raise. Default no-op., Return the registry key for this provider.          Returns:             The uni, Return True if the provider can accept requests right now.          This should (+1 more)

### Community 59 - "Community 59"
Cohesion: 0.14
Nodes (13): InvalidTransitionError, Any, Exception, State machine for the voice dictation pipeline.  Implements the exact state tran, Return the list of side-effect symbolic names for a matched transition.      The, Evaluate a single event against the transition table.          Args:, Evaluate a named condition against the provided context dict.          Each ``if, A single entry in the transition table. (+5 more)

### Community 60 - "Community 60"
Cohesion: 0.12
Nodes (9): The list of registered vocabulary terms (read-only)., True if no vocabulary terms are registered., Apply vocabulary substitution to the given text.          Terms are matched as c, User-defined vocabulary for term substitution in transcripts.      Usage::, VocabularyDictionary, No terms means no substitutions., Empty text returns empty text., A term that appears as a substring of another word should not match. (+1 more)

### Community 61 - "Community 61"
Cohesion: 0.16
Nodes (12): BaseModel, AdaptiveConfig, CommandsConfig, ContextConfig, Pydantic models for agentvoca configuration.  All config sections are validated, Vocabulary/substitution settings., Context engine configuration (v2)., Voice commands configuration (v2). (+4 more)

### Community 62 - "Community 62"
Cohesion: 0.20
Nodes (3): QTableWidget, Vocabulary & snippets page — inline tables + file paths., VocabSnippetsPage

### Community 63 - "Community 63"
Cohesion: 0.14
Nodes (9): HotkeyManager, Global hotkey binding for voice dictation.  Uses pynput.keyboard.HotKey (with li, Register a hotkey to emit a specific action.          Args:             hotkey_s, Start the global hotkey listener., Stop the global hotkey listener., Forget every registered hotkey.          Used by the v0.3.5 settings window to c, Convert our config format to pynput HotKey.parse() format.      Examples::, Manages global hotkey registration and dispatch.      Args:         event_bus: S (+1 more)

### Community 64 - "Community 64"
Cohesion: 0.18
Nodes (13): ndarray, Copy the last ``window_s`` seconds out of ``buffer`` with one allocation., _audio_bytes(), Tests for the streaming-ASR O(N) memory fix (R4).  Covers: - Churn bound: peak a, The new snapshot must be byte-identical to the old implementation., Buffer < window must return the entire buffer, not error., Generate ``seconds`` of float32 zeros (little-endian)., Drive the streaming loop with ~60 s of audio and bound allocation.      The old (+5 more)

### Community 65 - "Community 65"
Cohesion: 0.14
Nodes (9): NoneCleanupProvider, Passthrough cleanup provider.  Returns the transcript unchanged. Used when clean, Cleanup provider that performs no changes., Initialize the provider.          Args:             config: Optional configurati, Return the registry key for this provider., Return the transcript unchanged., Unit tests for the passthrough cleanup provider., test_none_cleanup_available() (+1 more)

### Community 66 - "Community 66"
Cohesion: 0.16
Nodes (8): ActiveAppDetector, Foreground application detection per platform.  Uses ``ctypes`` (Windows: user32, Detect foreground app on macOS using AppKit.          Requires pyobjc (only avai, Detects the foreground application and window title.      Platform support:, Check if platform detection APIs are accessible., Return True if foreground detection works on this platform., Detect the current foreground app and window title.          Returns:, Detect foreground app on Windows using ctypes + user32.          Retrieves the w

### Community 67 - "Community 67"
Cohesion: 0.19
Nodes (6): KeyboardInsertionStrategy, Inserts text character-by-character via keyboard simulation.      Args:, Non-ASCII text bypasses typewrite and goes via clipboard., Text containing newlines bypasses typewrite and goes via clipboard., Tests for KeyboardInsertionStrategy., TestKeyboardInsertion

### Community 68 - "Community 68"
Cohesion: 0.19
Nodes (11): QComboBox, Small helpers shared between page widgets.  Kept in a private module so the page, Pick the authoritative id from an editable QComboBox.      The combobox is popul, resolve_editable_combo_id(), _combo(), QComboBox, Tests for resolve_editable_combo_id.  Regression: the combobox is populated with, test_empty_combo_returns_empty_string() (+3 more)

### Community 69 - "Community 69"
Cohesion: 0.13
Nodes (5): MockCleanupProvider, Ensure ABCs cannot be instantiated without subclassing., Mocks with all abstract methods implemented can be instantiated., Minimal CleanupProvider stub for testing., TestABCContracts

### Community 70 - "Community 70"
Cohesion: 0.16
Nodes (7): QWizard, Welcome page for the setup wizard.  Always shown first. Three options:  - **Use, Display an amber banner explaining a config that failed to load.          Called, Reset the controller to v1 zero-config and jump to the finish page., No-op: customize means letting the wizard proceed naturally., Return the enclosing QWizard, if any (None inside the settings window)., WelcomePage

### Community 71 - "Community 71"
Cohesion: 0.18
Nodes (12): get_cleanup_prompt(), System prompt templates for cleanup providers.  Contains style-specific instruct, Generate a full system prompt for a cleanup provider.      Args:         style:, Unit tests for cleanup prompt generation., Test raw style prompt generation., Test custom prompt override., Test prompt generation without technical guardrails., Test standard style prompt generation. (+4 more)

### Community 72 - "Community 72"
Cohesion: 0.15
Nodes (9): make_default_catalog(), ModelEntry, Model catalog — fetch the list of models available at an OpenAI-compatible ``/v1, Fetch on a background thread; deliver result via ``on_done``.          ``on_done, Turn a ``/v1/models`` payload into ``ModelEntry`` rows.          Handles the Ope, Best-effort free-tier detection for OpenRouter-style payloads., Build a fresh ``ModelCatalog`` (factory used by tests)., One row in the model dropdown.      Attributes:         id: The model id exactly (+1 more)

### Community 73 - "Community 73"
Cohesion: 0.20
Nodes (8): Path, Add new terms to the dictionary and rebuild the matching pattern.          Args:, Recompile the match pattern and the casing lookup together., Add a mapping from a misrecognized term to a correct term.          Args:, Add many wrong->right mappings with a single pattern rebuild., Read a vocabulary file, one term per line.      Lines are stripped. Empty lines, Initialize the dictionary.          Args:             path: Optional path to a v, _read_vocab_file()

### Community 74 - "Community 74"
Cohesion: 0.15
Nodes (5): MockASRProvider, MockAsyncIterator, Unit tests for the provider registry and abstract base classes.  Tests cover: -, Minimal ASRProvider stub for testing., Minimal async iterator stub for stream_transcribe tests.

### Community 75 - "Community 75"
Cohesion: 0.15
Nodes (8): CallbackFlags, CallbackStop, ndarray, Close the audio input stream and join the VAD worker (R2)., Stop capturing audio and emit ``RecordingStoppedEvent``.          Cheap (callbac, Join the buffer and publish ``RecordingStoppedEvent`` (loop thread).          Ru, Stop recording and discard the audio buffer.          R6: only schedule the chun, Callback invoked by sounddevice for each audio block.

### Community 76 - "Community 76"
Cohesion: 0.15
Nodes (8): FasterWhisperProvider, Initialize the provider.          Args:             config: The ASR configuratio, Return True when streaming is enabled in config., Return the registry key for this provider., Return True if the model can be loaded., Local ASR provider using faster-whisper.      Supports v1 batch transcription vi, __getattr__(), ASR provider adapters.  Provider classes are imported lazily (PEP 562) so that i

### Community 77 - "Community 77"
Cohesion: 0.17
Nodes (8): InsertionStrategy, ABC, Insertion strategy abstract base class.  All text insertion strategies must subc, Abstract base class for text insertion strategies.      Implementations must han, Return the registry key for this strategy.          Returns:             The uni, Return True if insertion can proceed on this platform.          This should chec, Insert text at the current cursor position.          Must not raise. On failure,, Attempt to undo the last insertion.          Returns:             True if the un

### Community 78 - "Community 78"
Cohesion: 0.19
Nodes (10): Remove the last inserted text.          Strategy (in order):         1. Refocus, focus_window(), get_foreground_hwnd(), is_windows(), paste_modifier_key(), Windows-specific helpers for text insertion.  Provides platform detection, foreg, Return True if running on Windows., Return the paste modifier key for Windows. (+2 more)

### Community 79 - "Community 79"
Cohesion: 0.19
Nodes (4): CleanupPage, QComboBox, Cleanup page — provider, style, endpoint, API key., Kick off an async model-list fetch for the current endpoint + key.

### Community 80 - "Community 80"
Cohesion: 0.17
Nodes (9): OpenAICompatibleASRProvider, ASR provider using an OpenAI-compatible API., Initialize the provider with config.          Args:             config: The ASR, Return the registry key for this provider., Return True if endpoint and API key (if required) are set., A 4xx must include the provider's response body for diagnosis., Regression: raw PCM must be wrapped in a valid WAV before upload.      Previousl, test_openai_asr_surfaces_provider_error_body() (+1 more)

### Community 81 - "Community 81"
Cohesion: 0.23
Nodes (8): DefaultCommandProcessor, Implementation of CommandProcessor with a default set of editing commands., Hot-apply every supported field from ``new_config``.          Restart-only field, test_command_matching_case_insensitive(), test_command_matching_leading(), test_command_matching_no_match(), test_command_matching_standalone(), test_command_overrides()

### Community 82 - "Community 82"
Cohesion: 0.17
Nodes (11): fw_config(), openai_config(), Unit tests for ASR adapters., Test OpenAICompatibleASRProvider error handling., Test FasterWhisperProvider's buffering stream implementation., Test FasterWhisperProvider transcription with a mock model., Test OpenAICompatibleASRProvider transcription with mock httpx., test_faster_whisper_stream_fallback() (+3 more)

### Community 83 - "Community 83"
Cohesion: 0.17
Nodes (7): Unit tests for the StateMachine.  Covers every transition in the architecture sp, Force-reset the state machine., A cycle where cleanup fails and insertion uses clipboard., Reach error state and recover to idle., TestErrorRecovery, TestFallbackCycle, TestReset

### Community 84 - "Community 84"
Cohesion: 0.17
Nodes (11): counting_build_pattern(), Tests for R13: batched learned-mapping merge in VocabularyDictionary.  Verifies, Wrap ``_build_pattern`` so the test can count rebuilds., A single ``add_mappings`` call rebuilds the pattern exactly once,     regardless, All 200 mappings apply to a transcript after a single bulk insert., ``add_mapping`` (singular) still rebuilds the pattern — used by the     adaptive, An empty batch is a no-op and does not trigger a rebuild., test_bulk_mappings_apply_correctly() (+3 more)

### Community 85 - "Community 85"
Cohesion: 0.17
Nodes (11): Tests for the R12 O(1) casing lookup in VocabularyDictionary.  Verifies that the, Plain terms: behavior identical to the previous linear-scan lookup., ``wrong -> right`` mappings take precedence over the casing lookup., For duplicate case-variants (e.g. ``polars`` and ``Polars``), the first     adde, Terms with non-word characters (``C++``, ``C#``) match and keep their     origin, Scale: 5,000-term dictionary applied to a ~1,000-word transcript with     ~50 ma, test_behavior_arrow_mappings(), test_behavior_first_wins_for_case_variants() (+3 more)

### Community 86 - "Community 86"
Cohesion: 0.22
Nodes (3): CleanupConfig, Cleanup provider configuration., TestCustomPromptPath

### Community 87 - "Community 87"
Cohesion: 0.22
Nodes (8): ContextProvider, ABC, Context provider abstract base class and shared dataclasses.  All context detect, The resolved context at a point in time.      Attributes:         app_name: Name, Abstract base for context detection providers.      Implementations must handle, Return True if context detection works on this platform.          Returns:, Return the current context.          Must not raise. Returns an empty ``Resolved, ResolvedContext

### Community 88 - "Community 88"
Cohesion: 0.18
Nodes (6): LanguageResolver, Language hint resolution for the context engine.  Consumes the ``language_detect, Tracks the latest detected language from ASR and provides it as a hint.      The, Update the latest detected language.          Args:             language_detecte, Return the latest detected language as a hint for the next utterance.          R, Reset the detected language (e.g. when the user changes the configured language)

### Community 89 - "Community 89"
Cohesion: 0.18
Nodes (5): Register a cleanup provider class under the given name.          Args:, Register an insertion strategy class under the given name.          Args:, Register a vision provider class under the given name.          Args:, Register all built-in providers and strategies as dotted paths.          No prov, Register an ASR provider class under the given name.          Args:

### Community 90 - "Community 90"
Cohesion: 0.20
Nodes (4): Context passed to a vision (VLM) provider for image extraction.      Attributes:, VisionContext, DummyClient, DummyResponse

### Community 91 - "Community 91"
Cohesion: 0.22
Nodes (8): Return True if we can simulate keyboard on this platform., has_accessibility_permissions(), is_macos(), paste_modifier_key(), macOS-specific helpers for text insertion.  Provides platform detection, accessi, Return True if running on macOS., Check whether the app has accessibility permissions on macOS.      This is a bes, Return the paste modifier key for macOS.      Returns:         ``"cmd"`` for mac

### Community 92 - "Community 92"
Cohesion: 0.18
Nodes (8): loop_thread(), Unit tests for AsyncLoopThread and EventBus loop routing (v2 wiring)., A task spawned by a coroutine must keep running on the persistent loop., Publishing from a thread with no running loop routes to the loop., With no persistent loop set, async handlers run synchronously., test_create_task_inside_submitted_coro_survives(), test_event_bus_routes_async_handler_to_persistent_loop(), test_event_bus_without_loop_still_runs_async_handler()

### Community 93 - "Community 93"
Cohesion: 0.22
Nodes (5): ChunkCollector, Chunk emission correctness., Audio data should appear in either a non-flush chunk or the flush., Collects AudioChunkEvent emissions for assertions., TestChunkerEmission

### Community 94 - "Community 94"
Cohesion: 0.33
Nodes (3): HotkeysConfig, Hotkey binding configuration., TestHotkeyValidation

### Community 95 - "Community 95"
Cohesion: 0.24
Nodes (5): Cancel the active streaming task if one exists., Reset all per-recording streaming and pipelined-cleanup state.          Safe to, Reset streaming state at the start of a new recording.          Called (schedule, Abort the current dictation: stream task, in-flight pipeline, state.          Ru, Clean up resources and stop all background tasks.

### Community 96 - "Community 96"
Cohesion: 0.20
Nodes (9): Tests for R14: lazy provider imports (cold-start).  Verifies that building a ``P, A fresh registry must not import ctranslate2, faster_whisper, or     numpy — the, ``get_asr(ASRConfig(provider='faster_whisper'))`` returns a     working ``Faster, An unknown provider name raises ProviderNotFoundError that lists     the availab, register_asr / register_cleanup / register_insertion / register_vision     all s, test_get_asr_resolves_faster_whisper_class(), test_get_unknown_provider_raises_listing_available_names(), test_register_class_then_string_in_same_slot() (+1 more)

### Community 97 - "Community 97"
Cohesion: 0.20
Nodes (9): config(), provider(), Unit tests for the OpenAI-compatible cleanup provider., Test successful cleanup via OpenAI API., Test API error handling., Test that it returns raw transcript if LLM returns empty., test_openai_cleanup_empty_response(), test_openai_cleanup_failure() (+1 more)

### Community 98 - "Community 98"
Cohesion: 0.22
Nodes (6): Write ``text`` to clipboard and send paste hotkey.          Args:             te, Undo clipboard paste by sending Ctrl+Z / Cmd+Z.          Returns:             Tr, get_input_executor(), Return the single shared input executor, creating it on first use     and replac, Type the text at the current cursor position.          Args:             text: T, ThreadPoolExecutor

### Community 99 - "Community 99"
Cohesion: 0.25
Nodes (5): Stage timer context manager that emits TimingEvent.  Used to measure and log per, Context manager that measures elapsed time for a pipeline stage.      Usage:, Measure the duration of a pipeline stage.          Args:             stage: Name, Convenience: call timer(stage) instead of timer.measure(stage)., StageTimer

### Community 100 - "Community 100"
Cohesion: 0.22
Nodes (5): chunker(), event_bus(), Unit tests for the AudioChunker.  Tests cover: - Chunk emission cadence. - Delta, Audio data feeding and buffer management., TestChunkerAudioFeed

### Community 102 - "Community 102"
Cohesion: 0.25
Nodes (8): _provider_with_prompt(), Tests for R9: mtime-keyed cache of the custom cleanup prompt file.  Verifies tha, Two rewrite() calls with the same mtime should open the file only once., Touching the file with newer content + newer mtime causes the     next call to r, A missing custom_prompt_path raises CleanupError with the same     message prefi, test_missing_prompt_raises_cleanup_error(), test_prompt_cache_invalidated_by_mtime(), test_prompt_read_once_per_mtime()

### Community 103 - "Community 103"
Cohesion: 0.25
Nodes (4): Return new audio since the last emission and compact the buffer.          ``end`, Emit audio deltas at the configured cadence., Begin the chunk emission loop., Stop the chunker and optionally flush remaining audio.          When ``flush`` i

### Community 104 - "Community 104"
Cohesion: 0.29
Nodes (4): Raised when a vision (VLM) extraction fails., VisionError, Vision provider that sleeps per call, recording its call order., _SleepyVision

### Community 105 - "Community 105"
Cohesion: 0.25
Nodes (7): event_bus(), minimal_config(), Shared pytest fixtures for the agentvoca test suite., Return a fresh EventBus for each test., Return a minimal valid FullConfig suitable for unit tests., Return a ProviderRegistry with all built-in providers registered., registry()

### Community 106 - "Community 106"
Cohesion: 0.25
Nodes (5): R5: ``_get_delta`` compacts the buffer; size stays bounded., Sum of all emitted deltas equals the sum of all added audio.          With or wi, After every ``_get_delta``, ``_buffer`` is empty (compacted)., ``stop(flush=True)`` publishes exactly one flush chunk holding the tail., TestChunkerRP5Compact

### Community 107 - "Community 107"
Cohesion: 0.33
Nodes (4): Preload both accurate and streaming models at startup.          Also runs a tiny, Lazy load the accurate Whisper model, with automatic CPU fallback., Lazy load the streaming (small/fast) Whisper model., WhisperModel

### Community 109 - "Community 109"
Cohesion: 0.29
Nodes (3): Delta emission — only new audio since the last emission., Sum of all deltas must equal the full recorded audio., TestChunkerDelta

### Community 111 - "Community 111"
Cohesion: 0.33
Nodes (4): Future, Any, Schedule a coroutine on the loop from any thread.          Returns a ``concurren, Schedule a plain callable to run on the loop thread.

### Community 112 - "Community 112"
Cohesion: 0.40
Nodes (5): _probe_compute_type(), Faster-Whisper ASR provider.  Inference is performed locally using the faster-wh, Register pip-installed NVIDIA DLL directories with the Windows DLL loader., Return the best CTranslate2 compute type supported on ``device``.      Queries `, _register_cuda_dlls()

### Community 113 - "Community 113"
Cohesion: 0.40
Nodes (3): CommandProcessor, CommandResult, High-precision match of leading/standalone command phrases.         Returns matc

### Community 114 - "Community 114"
Cohesion: 0.33
Nodes (4): Extract image content via the VLM.          Args:             image_data: Encode, get_vision_prompt(), System prompt templates for vision (VLM) extraction (v3).  The vision prompt tur, Build the system prompt for a vision extraction request.      Args:         inst

### Community 115 - "Community 115"
Cohesion: 0.33
Nodes (5): _force_offscreen_qt(), qapp(), Shared fixtures for integration tests in this directory., Force the offscreen Qt platform so the wizard renders in CI., Return a single QApplication for the duration of the test.

### Community 118 - "Community 118"
Cohesion: 0.33
Nodes (4): Tests for AudioCapture.stop_recording offloading the join + publish (R3).  Cover, The audio callback no longer executes the buffer join inline., Simulate auto-stop happening inside ``_audio_callback`` and         verify the c, TestAutoStopFromCallbackDoesNotBlockOnJoin

### Community 120 - "Community 120"
Cohesion: 0.33
Nodes (3): A missing env var should be replaced with empty string., Test that load_config expands env vars in a real YAML file., TestEnvVarExpansion

### Community 121 - "Community 121"
Cohesion: 0.33
Nodes (3): Unit tests for keyboard and clipboard insertion strategies.  Tests cover strateg, Tests for platform detection utilities., TestPlatformHelpers

### Community 122 - "Community 122"
Cohesion: 0.33
Nodes (5): Tests for R11: a single shared executor serializes pyautogui/pyperclip.  Concurr, Both strategies route through the same single-worker executor., Stubs that record start/end timestamps: the two calls' intervals     must not ov, test_concurrent_insert_and_undo_do_not_interleave(), test_keyboard_and_clipboard_share_executor()

### Community 123 - "Community 123"
Cohesion: 0.40
Nodes (4): QIcon, _make_icon(), System tray icon and menu for voice dictation.  Uses PySide6 to create a system, Create a solid-colour circle icon.      Args:         r, g, b: RGB colour values

### Community 124 - "Community 124"
Cohesion: 0.40
Nodes (3): AsyncClient, Initialize the provider with config.          Args:             config: The clea, Construct the shared ``httpx.AsyncClient``.          Exposed as a seam so tests

### Community 125 - "Community 125"
Cohesion: 0.40
Nodes (3): Register a handler for the given event type.          Args:             event_ty, Remove a previously registered handler.          Args:             event_type: T, T

### Community 126 - "Community 126"
Cohesion: 0.40
Nodes (4): _build_pattern(), Pattern, Vocabulary substitution module.  Loads a user-defined vocabulary (one term per l, Build a compiled regex for whole-word matching of the given terms.      Uses ``(

### Community 132 - "Community 132"
Cohesion: 0.50
Nodes (3): _pcm_f32_to_wav(), OpenAI-compatible ASR provider.  Sends audio to any OpenAI-compatible /v1/audio/, Wrap raw little-endian float32 PCM in a standard 16-bit PCM WAV container.

### Community 135 - "Community 135"
Cohesion: 0.50
Nodes (4): invalid_hotkey.yaml test fixture: hotkeys.toggle_recording set to malformed 'invalid+key+here' (exercises hotkey format validation), invalid_sample_rate.yaml test fixture: audio.sample_rate=96000 (exercises sample-rate bound validation), invalid_silence_timeout.yaml test fixture: audio.silence_timeout_ms=-100 (exercises positive-int validation), valid_full.yaml test fixture: complete valid config (app/audio/asr/cleanup/insertion/hotkeys/vocabulary/snippets) with openai_compatible providers

## Knowledge Gaps
- **28 isolated node(s):** `agentvoca`, `build.sh script`, `release.sh script`, `CI Workflow`, `Windows Version Info` (+23 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **43 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Orchestrator` connect `Event Types (bus)` to `Orchestrator, Overlay & Events`, `ASR Providers`, `Cancel Semantics & Registry`, `EventBus & Config Core`, `Snippet Expansion`, `App State Machine`, `Screenshot Capture (v3)`, `Per-App Cleanup Profiles`, `Benchmark & Mocks`, `Vision Pipeline Integration`, `Warm-up & Insertion`, `Streaming Pipeline Integration`, `Cross-cutting Utilities`, `Community 27`, `Community 31`, `Community 36`, `Community 37`, `Community 48`, `Community 51`, `Community 60`, `Community 66`, `Community 81`, `Community 88`, `Community 90`, `Community 95`, `Community 104`, `Community 116`, `Community 117`, `Community 127`?**
  _High betweenness centrality (0.202) - this node is a cross-community bridge._
- **Why does `EventBus` connect `EventBus & Config Core` to `Orchestrator, Overlay & Events`, `ASR Providers`, `Cancel Semantics & Registry`, `Event Types (bus)`, `Screenshot Capture (v3)`, `Benchmark & Mocks`, `Vision Pipeline Integration`, `Warm-up & Insertion`, `Streaming Pipeline Integration`, `VAD Worker Capture`, `Community 27`, `Community 33`, `Community 34`, `Community 37`, `Community 41`, `Community 51`, `Community 53`, `Community 55`, `Community 57`, `Community 63`, `Community 92`, `Community 93`, `Community 100`, `Community 104`, `Community 105`, `Community 106`, `Community 109`, `Community 116`, `Community 117`, `Community 118`, `Community 119`, `Community 125`, `Community 127`?**
  _High betweenness centrality (0.127) - this node is a cross-community bridge._
- **Why does `ConfigController` connect `Config Controller` to `Cancel Semantics & Registry`, `EventBus & Config Core`, `Community 43`, `Community 44`, `Community 47`, `Community 50`, `Community 55`, `Community 26`?**
  _High betweenness centrality (0.124) - this node is a cross-community bridge._
- **Are the 106 inferred relationships involving `EventBus` (e.g. with `_MockASR` and `_MockCleanup`) actually correct?**
  _`EventBus` has 106 INFERRED edges - model-reasoned connections that need verification._
- **Are the 117 inferred relationships involving `Orchestrator` (e.g. with `_MockASR` and `_MockCleanup`) actually correct?**
  _`Orchestrator` has 117 INFERRED edges - model-reasoned connections that need verification._
- **Are the 86 inferred relationships involving `FullConfig` (e.g. with `_MockASR` and `_MockCleanup`) actually correct?**
  _`FullConfig` has 86 INFERRED edges - model-reasoned connections that need verification._
- **Are the 91 inferred relationships involving `ProviderRegistry` (e.g. with `_make_orchestrator()` and `_MockASR`) actually correct?**
  _`ProviderRegistry` has 91 INFERRED edges - model-reasoned connections that need verification._