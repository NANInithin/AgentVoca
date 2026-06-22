"""System prompt templates for vision (VLM) extraction (v3).

The vision prompt turns a screenshot into clean markdown/text. The user's
spoken dictation is supplied as the extraction instruction so the model can
infer the desired format. Technical-text guardrails mirror the cleanup
provider so values, code, and identifiers survive extraction unchanged.
"""

# Non-negotiable guardrails — kept consistent with cleanup/prompts.py so an
# extracted table's numbers, code, and identifiers are never altered.
VISION_GUARDRAILS = """
Rules you must follow without exception:
- Transcribe all numbers, currency amounts, dates, and units exactly as shown.
- Preserve all code identifiers, file paths, URLs, and version strings exactly.
- Do not invent, add, omit, or guess any data that is not visible in the image.
- If a value is unreadable, write [unreadable] rather than guessing.
- Output only the extracted content. Do not add commentary, preamble, or
  closing remarks such as "Here is the table:" or "I hope this helps".
"""

_FORMAT_HINTS = {
    "markdown": (
        "Format the output as GitHub-flavored Markdown. Render any tabular data"
        " as a Markdown table with a header row and a separator row."
    ),
    "plain": ("Format the output as plain text. Do not use Markdown syntax, tables, or backticks."),
    "auto": (
        "Choose the output format that best matches what the instruction asks for."
        " If the instruction asks for a table, or the image clearly contains"
        " tabular data, render a GitHub-flavored Markdown table. Otherwise return"
        " clean prose or a list as appropriate."
    ),
}


def get_vision_prompt(instruction: str = "", output_format: str = "auto") -> str:
    """Build the system prompt for a vision extraction request.

    Args:
        instruction: The spoken dictation text guiding extraction.
        output_format: One of ``"auto"``, ``"markdown"``, ``"plain"``.

    Returns:
        The complete system prompt string.
    """
    format_hint = _FORMAT_HINTS.get(output_format, _FORMAT_HINTS["auto"])

    prompt = (
        "You extract the useful content from a screenshot into clean text that"
        " can be pasted directly into a document. The user is dictating and the"
        " screenshot supplements what they are saying."
        f"\n\n{format_hint}"
    )

    if instruction.strip():
        prompt += (
            "\n\nThe user said the following while attaching this screenshot; use"
            " it to decide what to extract and how to format it:\n"
            f'"{instruction.strip()}"'
        )

    prompt += f"\n\n{VISION_GUARDRAILS}"
    return prompt
