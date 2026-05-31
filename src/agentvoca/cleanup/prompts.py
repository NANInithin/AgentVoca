"""System prompt templates for cleanup providers.

Contains style-specific instructions for LLM-based transcript cleanup.
All prompts include non-negotiable guardrails for technical text preservation.
"""

from typing import Optional

# Non-negotiable guardrails for technical text preservation
TECHNICAL_GUARDRAILS = """
Rules you must follow without exception:
- Preserve all code identifiers exactly: variable names, function names, class names,
  constants, CLI flags, shell commands.
- Preserve all file paths exactly: absolute paths, relative paths, tilde-expanded paths.
- Preserve all URLs exactly.
- Preserve all environment variable names exactly.
- Preserve all version numbers, semver strings, and numeric identifiers exactly.
- Do not invent, add, or remove content.
- Do not paraphrase technical terms.
- Do not change capitalization of identifiers (e.g., do not change camelCase to sentence case).
"""

# Style-specific instructions
STYLE_INSTRUCTIONS = {
    "raw": "Return the transcript exactly as provided. Do not change a single character.",
    "light": (
        "Add basic punctuation and capitalization to the transcript."
        " Do not remove filler words or rewrite anything."
    ),
    "standard": (
        "Clean up the transcript by removing filler words (uh, um, you know, etc.),"
        " adding proper punctuation, and fixing basic grammar. Keep the tone natural."
    ),
    "technical": (
        "Clean up the transcript by removing filler words and adding punctuation."
        " Focus on preserving technical accuracy and concise phrasing. Do not add paragraphs."
    ),
    "professional": (
        "Clean up the transcript for a professional context. Remove filler words,"
        " add punctuation, and ensure clear paragraphing and formal grammar."
    ),
}


def get_cleanup_prompt(
    style: str = "standard",
    custom_prompt: Optional[str] = None,
    preserve_code: bool = True,
) -> str:
    """Generate a full system prompt for a cleanup provider.

    Args:
        style: The cleanup style mode (raw, light, standard, technical, professional).
        custom_prompt: An optional custom prompt override.
        preserve_code: If True, include technical text preservation guardrails.

    Returns:
        The complete system prompt string.
    """
    if custom_prompt:
        base_instruction = custom_prompt
    else:
        base_instruction = STYLE_INSTRUCTIONS.get(style, STYLE_INSTRUCTIONS["standard"])

    prompt = (
        "You are a transcript cleaner. Clean the following speech transcript."
        f"\n\n{base_instruction}"
    )

    if preserve_code:
        prompt += f"\n\n{TECHNICAL_GUARDRAILS}"

    return prompt
