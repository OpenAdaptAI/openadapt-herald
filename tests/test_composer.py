"""Tests for the composer module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from herald.collector import Artifacts, Commit, Release
from herald.composer import (
    _build_system_prompt,
    _format_artifacts_for_prompt,
    _load_prompt,
    _load_writing_guide,
    compose,
)


class TestPromptLoading:
    def test_load_writing_guide(self):
        guide = _load_writing_guide()
        assert "banned" in guide.lower() or "ban" in guide.lower()
        assert "delve" in guide
        assert len(guide) > 100

    def test_load_release_prompt(self):
        prompt = _load_prompt("release")
        assert "release" in prompt.lower()
        assert "JSON" in prompt or "json" in prompt.lower()

    def test_load_digest_prompt(self):
        prompt = _load_prompt("digest")
        assert "digest" in prompt.lower()

    def test_load_spotlight_prompt(self):
        prompt = _load_prompt("spotlight")
        assert "spotlight" in prompt.lower() or "feature" in prompt.lower()

    def test_load_nonexistent_prompt_raises(self):
        with pytest.raises(FileNotFoundError):
            _load_prompt("nonexistent_prompt_template")


class TestSystemPrompt:
    def test_build_system_prompt_includes_writing_guide(self):
        prompt = _build_system_prompt("release")
        assert "delve" in prompt  # banned word from writing guide
        assert "writing style guide" in prompt.lower()

    def test_build_system_prompt_includes_content_instructions(self):
        prompt = _build_system_prompt("release")
        assert "release" in prompt.lower()

    def test_build_system_prompt_with_project_context(self):
        ctx = "OpenAdapt is a desktop automation tool"
        prompt = _build_system_prompt("release", project_context=ctx)
        assert "OpenAdapt" in prompt
        assert "desktop automation" in prompt

    def test_build_system_prompt_without_project_context(self):
        prompt = _build_system_prompt("release")
        assert "project context" not in prompt.lower()


class TestFormatArtifacts:
    def test_empty_artifacts(self):
        result = _format_artifacts_for_prompt([])
        assert "No artifacts" in result

    def test_formats_commits(self):
        artifacts = [Artifacts(
            repo_name="test/repo",
            commits=[Commit("abc123", "Alice", "2026-01-01", "feat: add thing")],
        )]
        result = _format_artifacts_for_prompt(artifacts)
        assert "abc123" in result
        assert "feat: add thing" in result

    def test_formats_releases(self):
        artifacts = [Artifacts(
            repo_name="test/repo",
            releases=[Release("v2.0.0", "Version 2", "Major update", "2026-01-01")],
        )]
        result = _format_artifacts_for_prompt(artifacts)
        assert "v2.0.0" in result
        assert "Major update" in result


class TestCompose:
    @patch("herald.composer.anthropic.Anthropic")
    def test_compose_returns_parsed_json(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        expected = {
            "discord": "Check out v1.0! New feature X.",
            "twitter": "v1.0 shipped with feature X #opensource",
            "summary": "v1.0 with feature X",
        }
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(expected))]
        mock_client.messages.create.return_value = mock_response

        artifacts = [Artifacts(
            repo_name="test/repo",
            commits=[Commit("abc", "Alice", "2026-01-01", "feat: X")],
        )]

        result = compose(artifacts, api_key="test-key")
        assert result["discord"] == expected["discord"]
        assert result["twitter"] == expected["twitter"]

    @patch("herald.composer.anthropic.Anthropic")
    def test_compose_handles_markdown_json(self, mock_anthropic_cls):
        """LLMs sometimes wrap JSON in ```json blocks."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        expected = {"discord": "test", "twitter": "test", "summary": "test"}
        wrapped = f"```json\n{json.dumps(expected)}\n```"
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=wrapped)]
        mock_client.messages.create.return_value = mock_response

        result = compose(
            [Artifacts(commits=[Commit("a", "A", "2026-01-01", "fix")])],
            api_key="test-key",
        )
        assert result["discord"] == "test"

    @patch("herald.composer.anthropic.Anthropic")
    def test_compose_handles_non_json_response(self, mock_anthropic_cls):
        """Falls back gracefully when LLM doesn't return JSON."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Just a plain text response about the release.")]
        mock_client.messages.create.return_value = mock_response

        result = compose(
            [Artifacts(commits=[Commit("a", "A", "2026-01-01", "fix")])],
            api_key="test-key",
        )
        assert "discord" in result
        assert "twitter" in result
        assert "Just a plain text response" in result["discord"]

    @patch("herald.composer.anthropic.Anthropic")
    def test_compose_passes_extra_instructions(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"discord":"x","twitter":"y","summary":"z"}')]
        mock_client.messages.create.return_value = mock_response

        compose(
            [Artifacts(commits=[Commit("a", "A", "2026-01-01", "fix")])],
            api_key="test-key",
            extra_instructions="Focus on the bug fix.",
        )

        call_args = mock_client.messages.create.call_args
        user_msg = call_args[1]["messages"][0]["content"]
        assert "Focus on the bug fix" in user_msg

    @patch("herald.composer.anthropic.Anthropic")
    def test_compose_uses_correct_model(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"discord":"x","twitter":"y","summary":"z"}')]
        mock_client.messages.create.return_value = mock_response

        compose(
            [Artifacts(commits=[Commit("a", "A", "2026-01-01", "fix")])],
            api_key="test-key",
            model="claude-opus-4-6",
        )

        call_args = mock_client.messages.create.call_args
        assert call_args[1]["model"] == "claude-opus-4-6"
