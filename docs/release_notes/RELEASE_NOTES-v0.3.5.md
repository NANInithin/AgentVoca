# AgentVoca Release Notes

## v0.3.5 - Enhanced Setup, Robust Configuration, and ASR Improvements

**Released:** 2026-07-12
**Version:** 0.3.5

### 🎯 Overview
AgentVoca v0.3.5 delivers **significant improvements to the setup experience**, **lenient configuration loading**, and **WAV conversion for OpenAI-compatible ASR**. This release focuses on making the application more robust, user-friendly, and feature-complete with enhanced device support, better error handling, and improved UI workflows.

> **More resilient, user-friendly, and feature-complete.** AgentVoca now handles broken configurations gracefully, ensures proper audio format for ASR providers, and provides a smoother setup experience.

### ✨ New Features & Improvements

#### Enhanced Setup Experience
- **Complete Setup Wizard:** Full-featured wizard with all configuration pages
- **Persistent User Input:** Preserves typed values across page navigation
- **Improved Navigation:** Smoother flow between wizard pages
- **Better Error Handling:** In-wizard warnings instead of modal dialogs
- **Settings Window:** Tabbed interface for post-setup configuration
- **Restart Management:** Clear indication of settings requiring application restart

#### Lenient Config Loader
- **Graceful Error Handling:** Loads configurations even when API keys are missing or invalid
- **Wizard Integration:** Shows warnings and opens the setup wizard for users to fix issues
- **Preserves User Input:** Maintains user's saved values instead of silently replacing them with defaults
- **Structural Error Recovery:** Falls back to sensible defaults when configuration schema is invalid
- **First Run Detection:** Properly handles first-run scenarios

#### WAV Conversion for OpenAI ASR
- **Proper Audio Format:** Converts raw PCM audio to valid WAV format before upload
- **Prevents API Errors:** Eliminates 400 errors from Whisper-compatible endpoints
- **Better Provider Compatibility:** Works seamlessly with all OpenAI-compatible ASR providers
- **Error Reporting:** More descriptive error messages from API providers

#### Model Catalog Enhancements
- **OpenRouter Transcription Filter:** Supports filtering for speech-to-text models
- **Improved Caching:** Better cache management per endpoint and API key
- **Error Handling:** More descriptive error messages for troubleshooting
- **Free Model Support:** Proper labeling and handling of free models
- **Endpoint Validation:** Better handling of different API endpoint formats

#### Device Support
- **Audio Device Probe:** Automatic detection of available audio devices
- **Device Caching:** Improved performance for device enumeration
- **Default Device Support:** Guaranteed availability of default audio device

#### Hotkey Management
- **Hotkey Presets:** Predefined hotkey configurations for common workflows
- **Hotkey Validation:** Better validation of hotkey combinations
- **Hotkey Customization:** Enhanced customization options in setup wizard

#### Application Improvements
- **Tray Icon:** Improved system tray integration
- **Settings Management:** Better handling of application settings
- **Version Tracking:** Proper version tracking for first-run detection
- **Restart Policy:** Clearer indication of settings requiring restart

### 🔧 Technical Details

#### Lenient Configuration Loading
1. **Broken Config Detection:** Identifies missing API keys or invalid configurations
2. **Warning Generation:** Creates human-readable warnings for users
3. **Fallback Mechanism:** Provides usable defaults while preserving user settings
4. **Wizard Integration:** Opens setup wizard to fix issues before pipeline initialization

#### WAV Conversion Process
1. **Audio Capture:** Receives raw float32 PCM audio from the pipeline
2. **WAV Packaging:** Wraps PCM data in RIFF/WAVE container format
3. **API Upload:** Sends properly formatted WAV file to ASR provider
4. **Response Handling:** Processes transcription results as before

#### Setup Wizard Navigation
- **State Preservation:** Captures page state before navigation
- **Controller Updates:** Only updates controller with user-modified values
- **Page Rebinding:** Only rebinds the arriving page from controller
- **Navigation Flow:** Maintains proper order of operations during wizard navigation

### 📋 What's New in v0.3.5

#### Major Additions
- **Complete Setup System:** Full setup wizard and settings window infrastructure
- **Lenient Config Loader:** `src/agentvoca/config/loader.py`
- **WAV Conversion:** `src/agentvoca/asr/openai_compatible.py`
- **Model Catalog Controller:** `src/agentvoca/setup/controllers/model_catalog.py`
- **Device Probe:** `src/agentvoca/setup/controllers/device_probe.py`
- **Hotkey Presets:** `src/agentvoca/setup/controllers/hotkey_presets.py`
- **Combobox Utilities:** `src/agentvoca/setup/pages/_combobox_utils.py`
- **Settings Window:** `src/agentvoca/setup/settings_window.py`

#### Files Added/Modified
- **New:** `src/agentvoca/setup/` - Complete setup system infrastructure
- **New:** `tests/unit/test_loader_lenient.py` - Lenient loader tests
- **New:** `tests/unit/test_model_catalog.py` - Model catalog tests
- **New:** `tests/unit/test_device_probe.py` - Device probe tests
- **New:** `tests/unit/test_hotkey_presets.py` - Hotkey presets tests
- **New:** `tests/integration/test_model_fetch.py` - Model fetching integration tests
- **New:** `tests/integration/test_settings_window.py` - Settings window tests
- **New:** `tests/integration/test_wizard.py` - Wizard integration tests
- **Updated:** `src/agentvoca/main.py` - Lenient loader integration and first-run handling
- **Updated:** `src/agentvoca/setup/controllers/config_controller.py` - Enhanced error handling
- **Updated:** `src/agentvoca/setup/pages/asr_page.py` - Model fetching and warnings
- **Updated:** `src/agentvoca/setup/wizard.py` - Complete wizard implementation
- **Updated:** `src/agentvoca/app/hotkeys.py` - Hotkey management improvements
- **Updated:** `src/agentvoca/app/settings.py` - Settings management
- **Updated:** `src/agentvoca/app/tray.py` - Tray icon improvements
- **Updated:** `tests/unit/test_asr_adapters.py` - WAV conversion tests
- **Updated:** `tests/unit/test_config_controller.py` - Enhanced controller tests
- **Updated:** `README.md` - Updated setup and configuration documentation

### 🧪 Testing
- **Lenient Loader Tests:** `tests/unit/test_loader_lenient.py`
- **Model Catalog Tests:** `tests/unit/test_model_catalog.py`
- **Device Probe Tests:** `tests/unit/test_device_probe.py`
- **Hotkey Presets Tests:** `tests/unit/test_hotkey_presets.py`
- **Config Controller Tests:** `tests/unit/test_config_controller.py`
- **Model Fetch Tests:** `tests/integration/test_model_fetch.py`
- **Wizard Tests:** `tests/integration/test_wizard.py`
- **Settings Window Tests:** `tests/integration/test_settings_window.py`
- **ASR Adapter Tests:** `tests/unit/test_asr_adapters.py`
- **First Run Tests:** `tests/unit/test_first_run.py`
- **Persistence Tests:** `tests/unit/test_persistence.py`

All tests pass successfully ✅

### � Technical Improvements

#### Architecture Enhancements
- **Complete Setup System:** Modular architecture for wizard pages and settings
- **Controller-Based UI:** Consistent state management across wizard and settings window
- **Signal-Based Communication:** Better decoupling between components
- **Thread-Safe Operations:** Improved handling of background operations
- **Error Handling Framework:** Consistent error reporting and recovery

#### Performance Optimizations
- **Device Caching:** Reduced overhead for audio device enumeration
- **Model Catalog Caching:** Improved performance for model fetching
- **Efficient Navigation:** Optimized wizard page loading and state management

### 🔄 Migration
- **Backward Compatible:** v0.3.5 is fully backward compatible with existing configurations
- **Improved Error Handling:** Existing broken configurations will now show warnings instead of crashing
- **No Breaking Changes:** All existing features work as before with enhanced reliability
- **Smoother Upgrades:** Lenient loader ensures smooth transition from previous versions

### 📚 Documentation
- **Config Reference:** `docs/config-reference.md` - Updated with lenient loading behavior
- **Setup Guide:** `docs/user-setup.md` - Improved wizard documentation
- **Troubleshooting:** `docs/troubleshooting.md` - Added common configuration issues

### 🚀 Installation

#### Option A: Download the `.exe` (Windows)
1. Download the latest release from GitHub
2. Run the installer and follow the setup wizard
3. Configure your preferred ASR and cleanup providers

#### Option B: Run from Source
```bash
# Clone the repository
git clone https://github.com/your-repo/agentvoca.git
cd agentvoca

# Install dependencies
uv sync

# Run AgentVoca
uv run agentvoca
```

### 🎨 User Experience Improvements

#### Setup Experience
- **Guided First Run:** Comprehensive wizard guides new users through setup
- **Contextual Help:** Inline warnings and guidance for configuration issues
- **Visual Feedback:** Clear indicators for settings requiring restart
- **Progressive Disclosure:** Advanced options available but not overwhelming

#### Daily Usage
- **Reliable ASR:** Fewer errors and better compatibility with providers
- **Flexible Configuration:** Easier to customize and adjust settings
- **Better Error Messages:** Clearer guidance when things go wrong
- **Improved Device Support:** Better handling of audio devices

### 📢 Feedback Wanted
This release introduces significant improvements to the setup experience and configuration reliability. We'd love to hear about your experience:

- Did the setup wizard help you get started more easily?
- Have you encountered any configuration issues that still need attention?
- What additional features would make AgentVoca even more useful for your workflow?

### 🙏 Acknowledgements
Special thanks to all contributors and users who reported issues and provided feedback that helped shape this release. Your input is invaluable in making AgentVoca more robust, user-friendly, and feature-complete!