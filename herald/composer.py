"""LLM-powered content composition from collected artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import anthropic

from herald.collector import Artifacts

ContentType = Literal["release", "digest", "spotlight"]

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
    model: str = "claude-sonnet-4-20250514",
    project_context: str = "",
    extra_instructions: str = "",
) -> dict:
    """Generate social media content from artifacts using an LLM.

    Returns a dict with keys like "discord", "twitter", "summary".
    """
    system_prompt = _build_system_prompt(content_type, project_context)
    user_message = _format_artifacts_for_prompt(artifacts_list)

    if extra_instructions:
        user_message += f"\n\nAdditional instructions: {extra_instructions}"

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    # Extract the text content
    text = response.content[0].text

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

    Requires consilium to be installed: pip install herald[consilium]
    """
    try:
        from consilium import LLMCouncil
    except ImportError:
        raise ImportError(
            "consilium is not installed. Install with: pip install herald[consilium]"
        )

    system_prompt = _build_system_prompt(content_type, project_context)
    user_message = _format_artifacts_for_prompt(artifacts_list)

    if extra_instructions:
        user_message += f"\n\nAdditional instructions: {extra_instructions}"

    council = LLMCouncil(
        models=["claude-sonnet-4-20250514", "gpt-4o"],
        chairman="claude-sonnet-4-20250514",
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
