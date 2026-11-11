"""Endpoint presets for the provider dropdowns on the ASR / Cleanup pages."""

from __future__ import annotations

CUSTOM = "custom"

ASR_PRESETS: list[tuple[str, str]] = [
    ("OpenAI", "https://api.openai.com/v1"),
    ("Groq", "https://api.groq.com/openai/v1"),
    ("OpenRouter", "https://openrouter.ai/api/v1"),
]

LLM_PRESETS: list[tuple[str, str]] = [
    ("OpenAI", "https://api.openai.com/v1"),
    ("OpenRouter", "https://openrouter.ai/api/v1"),
    ("Groq", "https://api.groq.com/openai/v1"),
    ("Anthropic", "https://api.anthropic.com/v1"),
    ("Ollama (local)", "http://localhost:11434/v1"),
]


def preset_for(endpoint: str | None, presets: list[tuple[str, str]]) -> str:
    """Return the preset endpoint matching ``endpoint`` or ``CUSTOM``."""
    ep = (endpoint or "").strip().rstrip("/")
    if not ep:
        return presets[0][1]
    for _label, url in presets:
        if ep == url:
            return url
    return CUSTOM
