"""LLM-powered content composition from collected artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import anthropic

from herald.collector import Artifacts
from herald.config import get_settings

ContentType = Literal["release", "digest", "spotlight", "introduction"]

# Thinking counts toward max_tokens, and current models think by default.
_MAX_TOKENS = 16000

# consilium reads the first block of a reply as its text, so it can't use a
# model that starts its reply with a thinking block. Keep its Claude seat on a
# model that doesn't think unless asked.
COUNCIL_CLAUDE_MODEL = "claude-sonnet-4-6"


class ComposeError(RuntimeError):
    """The model answered without any draft text."""

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    """Load a prompt template from the prompts directory."""
    path = _PROMPTS_DIR / f"{name}.md"
    return path.read_text()


def _load_writing_guide() -> str:
    """Load the writing guide for use as system context."""
    path = _PROMPTS_DIR / "writing_guide.md"
    return path.read_text()


def _build_system_prompt(content_type: ContentType, project_context: str = "") -> str:
    """Build the full system prompt with writing guide and content-type instructions."""
    writing_guide = _load_writing_guide()
    content_instructions = _load_prompt(content_type)

    parts = [
        "You are a developer advocate writing social media content for an open-source project.",
        "",
        "## Writing style guide",
        "Follow this guide strictly. Your output MUST sound human, not AI-generated.",
        "",
        writing_guide,
        "",
        "## Content instructions",
        "",
        content_instructions,
    ]

    if project_context:
        parts.extend([
            "",
            "## Project context",
            "",
            project_context,
        ])

    return "\n".join(parts)


def _format_artifacts_for_prompt(artifacts_list: list[Artifacts]) -> str:
    """Combine multiple repos' artifacts into a single prompt."""
    if not artifacts_list:
        return "No artifacts collected."

    parts = []
    for artifacts in artifacts_list:
        parts.append(artifacts.to_prompt_text())
        parts.append("")

    return "\n".join(parts)


def compose(
    artifacts_list: list[Artifacts],
    content_type: ContentType = "release",
    api_key: str = "",
    model: str = "",
    project_context: str = "",
    extra_instructions: str = "",
) -> dict:
    """Generate social media content from artifacts using an LLM.

    Without ``model``, uses the ``default_model`` setting (HERALD_DEFAULT_MODEL).
    Returns a dict with keys like "discord", "twitter", "summary".
    """
    model = model or get_settings().default_model
    system_prompt = _build_system_prompt(content_type, project_context)
    user_message = _format_artifacts_for_prompt(artifacts_list)

    if extra_instructions:
        user_message += f"\n\nAdditional instructions: {extra_instructions}"

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    # Read blocks by type: the reply can start with a thinking block.
    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
    if not text.strip():
        raise ComposeError(
            f"The model returned no text (stop reason: {response.stop_reason}). "
            "Nothing was drafted."
        )

    # Try to parse as JSON (the prompts ask for JSON output)
    try:
        # Handle case where LLM wraps JSON in markdown code block
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        # If JSON parsing fails, return the raw text as discord content
        return {
            "discord": text,
            "twitter": text[:280] if len(text) > 280 else text,
            "summary": text[:200] if len(text) > 200 else text,
        }


def compose_with_consilium(
    artifacts_list: list[Artifacts],
    content_type: ContentType = "release",
    project_context: str = "",
    extra_instructions: str = "",
    budget: float = 0.10,
) -> dict:
    """Generate content using consilium's multi-model council for higher quality.

    Requires the ``consilium`` extra (the ``openadapt-consilium`` package).
    """
    try:
        from consilium import Council
    except ImportError as exc:
        raise ImportError(
            "consilium is not installed. Install the extra with: "
            "pip install 'herald-announce[consilium] @ "
            "git+https://github.com/OpenAdaptAI/openadapt-herald.git'"
        ) from exc

    system_prompt = _build_system_prompt(content_type, project_context)
    user_message = _format_artifacts_for_prompt(artifacts_list)

    if extra_instructions:
        user_message += f"\n\nAdditional instructions: {extra_instructions}"

    council = Council(
        models=[COUNCIL_CLAUDE_MODEL, "gpt-4o"],
        chairman=COUNCIL_CLAUDE_MODEL,
    )
    result = council.ask(
        user_message,
        system=system_prompt,
        budget=budget,
    )

    text = result.final_answer

    try:
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        return {
            "discord": text,
            "twitter": text[:280] if len(text) > 280 else text,
            "summary": text[:200] if len(text) > 200 else text,
        }
