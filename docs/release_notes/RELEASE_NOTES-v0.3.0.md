# AgentVoca Release Notes

## v0.3.0 - Screenshot-to-Text (Vision) Feature

**Released:** 2026-06-27
**Version:** 0.3.0

### 🎯 Overview
AgentVoca v0.3.0 introduces the revolutionary **Screenshot-to-Text** feature, allowing you to snip regions mid-dictation and have a vision model extract their content as markdown/text, seamlessly woven into your dictation.

> **Opt-in and API-based.** Vision is off by default; when enabled, snipped screenshots are sent to the configured endpoint. Everything else stays local.

### ✨ New Features

#### Screenshot-to-Text (Vision)
- **Region Sniping:** Press `Ctrl+Shift+S` (configurable) while recording to snip any screen region
- **Vision Model Integration:** Extract tables, values, descriptions as markdown/text
- **Anchor-Based Splicing:** Say anchor phrases like "as in the attached screenshot" to place extractions precisely
- **Multiple Snips:** Support for multiple screenshots in one dictation session
- **API-Based:** Works with any OpenAI-compatible vision endpoint (OpenAI, OpenRouter, Anthropic, Ollama)

#### Configuration
```yaml
vision:
  enabled: true
  endpoint: https://openrouter.ai/api/v1
  api_key_env: OPENROUTER_API_KEY
  model: openai/gpt-4o-mini
  output_format: auto
  capture_timeout_s: 30

hotkeys:
  capture_screenshot: ctrl+shift+s
```

#### Supported Vision Providers
| Provider | Endpoint | Example Models |
|----------|----------|----------------|
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini`, `gpt-4o` |
| OpenRouter | `https://openrouter.ai/api/v1` | `anthropic/claude-opus-4-8`, `openai/gpt-4o-mini` |
| Anthropic | `https://api.anthropic.com/v1` | Claude vision models |
| Ollama (Local) | `http://localhost:11434/v1` | `qwen2.5-vl`, `minicpm-v` |

### 🔧 Technical Details

#### How It Works
1. **Start Recording:** Begin dictation with `Ctrl+Space`
2. **Capture Screenshot:** Press `Ctrl+Shift+S` to open OS snipping tool
3. **Dictate Instruction:** Say "make a table of the expenses" or "describe the chart"
4. **Anchor Placement:** Use phrases like "as in the attached screenshot" for precise placement
5. **Processing:** VLM extracts content, passes through cleanup with code preservation
6. **Insertion:** Merged text appears at cursor position

#### Anchor Phrases
Built-in anchors: "the attached screenshot", "this screenshot", "as shown", "as in the screenshot", etc.

#### Privacy
- Screenshots only leave machine when explicitly snipped
- Requires vision-capable model and API key
- All other AgentVoca processing stays local

### 📋 What's New in v0.3.0

#### Major Additions
- **Screenshot-to-Text:** Core v0.3.0 feature
- **Vision Provider:** OpenAI-compatible VLM adapter
- **Screenshot Capturer:** OS-native snipping (Windows/macOS/Linux)
- **AnchorSplicer:** Intelligent text splicing based on anchor phrases
- **VisionConfig:** Configuration management with validation

#### Files Added/Modified
- **New:** `src/agentvoca/vision/` - Vision provider package
- **New:** `src/agentvoca/capture/screenshot.py` - OS-native snipping
- **New:** `docs/vision.md` - Complete vision documentation
- **Updated:** `config.example.yaml` - Vision configuration block
- **Updated:** `README.md` - v0.3.0 section and features

### 🧪 Testing
- **Vision Pipeline Tests:** `tests/integration/test_vision_pipeline.py`
- **Anchor Tests:** `tests/unit/test_vision_anchors.py`
- **Provider Tests:** `tests/unit/test_vision_openai_compatible.py`
- **Capture Tests:** `tests/unit/test_screenshot_capture.py`
- **Config Tests:** `tests/unit/test_config_vision.py`

All tests pass successfully ✅

### 🔄 Migration
- **Backward Compatible:** v2 features remain opt-in
- **Configuration:** Existing `config.yaml` files work unchanged
- **Hotkeys:** New vision hotkey doesn't interfere with existing ones

### 📚 Documentation
- **Vision Guide:** `docs/vision.md` - Complete feature documentation
- **Config Reference:** `docs/config-reference.md` - Vision configuration options
- **README Updates:** v3 section with examples and setup instructions

### 🚀 Installation

#### Option A: Download the `.exe` (Windows)
1. Download latest release from GitHub
2. Extract and run `AgentVoca.exe`
3. Create config folder: `mkdir "$env:USERPROFILE\.agentvoca"`
4. Download `config.example.yaml` as `config.yaml`

#### Option B: Run from Source
```bash
git clone https://github.com/NANInithin/AgentVoca.git
cd AgentVoca
uv sync
uv run agentvoca
```

### 🔧 Configuration Example
```yaml
# Add this to your config.yaml to enable vision:
vision:
  enabled: true
  endpoint: https://openrouter.ai/api/v1
  api_key_env: OPENROUTER_API_KEY
  model: openai/gpt-4o-mini
  output_format: auto

hotkeys:
  capture_screenshot: ctrl+shift+s
```

### 📝 Usage Example
1. Start recording: `Ctrl+Space`
2. Dictate: "Here's a table of the monthly expenses"
3. Press `Ctrl+Shift+S` to snip the table
4. Say: "as in the attached screenshot"
5. Text appears: A markdown table of the expenses

### ⚠️ Known Limitations
- **API-Based Only:** Local VLM (GOT-OCR 2.0) planned for future release
- **Opt-in Required:** Vision is disabled by default for privacy
- **API Key Required:** Need vision-capable model and API key

### 🔮 Future Plans
- **Local VLM:** In-process offline vision model (GOT-OCR 2.0)
- **Enhanced Anchors:** More intelligent anchor phrase recognition
- **Template Support:** Pre-defined extraction templates
- **Batch Processing:** Process multiple screenshots with single instruction

### 🐛 Troubleshooting
- **Vision not working:** Ensure `vision.enabled: true` and API key set
- **No native screenshot tool:** Install platform-specific snipping tool
- **Tables mangled:** Use stronger vision model or `output_format: markdown`

### 📈 Version History
- **v0.1.0:** Initial release
- **v0.2.0:** Streaming, context engine, voice commands, adaptive vocab
- **v3.0.0:** Screenshot-to-text (vision) feature

### 🔗 Links
- **GitHub Repository:** https://github.com/NANInithin/AgentVoca
- **Documentation:** https://github.com/NANInithin/AgentVoca/tree/main/docs
- **Releases:** https://github.com/NANInithin/AgentVoca/releases
- **Issues:** https://github.com/NANInithin/AgentVoca/issues

---

*For support, questions, or feature requests, please visit the GitHub repository.*