"""Tests for the composer module."""

import json
from unittest.mock import MagicMock, patch

import pytest
from anthropic.types import TextBlock, ThinkingBlock

from herald.collector import Artifacts, Commit, Release
from herald.composer import (
    _build_system_prompt,
    _format_artifacts_for_prompt,
    _load_prompt,
    _load_writing_guide,
    compose,
)


def _text(text: str) -> TextBlock:
    return TextBlock(type="text", text=text)


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
        mock_response.content = [_text(json.dumps(expected))]
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
        mock_response.content = [_text(wrapped)]
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
        mock_response.content = [_text("Just a plain text response about the release.")]
        mock_client.messages.create.return_value = mock_response

        result = compose(
            [Artifacts(commits=[Commit("a", "A", "2026-01-01", "fix")])],
            api_key="test-key",
        )
        assert "discord" in result
        assert "twitter" in result
        assert "Just a plain text response" in result["discord"]

    @patch("herald.composer.anthropic.Anthropic")
    def test_non_json_fallback_does_not_cut_mid_word(self, mock_anthropic_cls):
        # The X publisher shortens to X's count; the fallback must not cut first.
        reply = " ".join(f"word{i}" for i in range(80))
        mock_anthropic_cls.return_value.messages.create.return_value = MagicMock(
            content=[_text(reply)]
        )

        result = compose([Artifacts(commits=[Commit("a", "A", "2026-01-01", "fix")])], api_key="k")

        assert result["twitter"] == reply
        summary = result["summary"]
        assert len(summary) <= 200 and summary.endswith("\u2026")
        assert reply[len(summary.removesuffix("\u2026"))] == " "

    @patch("herald.composer.anthropic.Anthropic")
    def test_compose_passes_extra_instructions(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [_text('{"discord":"x","twitter":"y","summary":"z"}')]
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
        mock_response.content = [_text('{"discord":"x","twitter":"y","summary":"z"}')]
        mock_client.messages.create.return_value = mock_response

        compose(
            [Artifacts(commits=[Commit("a", "A", "2026-01-01", "fix")])],
            api_key="test-key",
            model="claude-opus-4-6",
        )

        call_args = mock_client.messages.create.call_args
        assert call_args[1]["model"] == "claude-opus-4-6"


    @patch("herald.composer.anthropic.Anthropic")
    def test_compose_without_model_uses_the_setting(self, mock_anthropic_cls, monkeypatch):
        monkeypatch.setenv("HERALD_DEFAULT_MODEL", "claude-test-model")
        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.create.return_value = MagicMock(
            content=[_text('{"discord":"x"}')]
        )

        compose([Artifacts(commits=[Commit("a", "A", "2026-01-01", "fix")])], api_key="k")

        assert mock_client.messages.create.call_args[1]["model"] == "claude-test-model"

    @patch("herald.composer.anthropic.Anthropic")
    def test_compose_reads_text_after_a_thinking_block(self, mock_anthropic_cls):
        # Current models think by default, so the reply can start with a
        # thinking block whose text is empty.
        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.create.return_value = MagicMock(
            content=[
                ThinkingBlock(type="thinking", thinking="", signature="sig"),
                _text('{"discord": "Shipped v2", "twitter": "v2 is out"}'),
            ],
            stop_reason="end_turn",
        )

        result = compose(
            [Artifacts(commits=[Commit("a", "A", "2026-01-01", "fix")])], api_key="k"
        )

        assert result == {"discord": "Shipped v2", "twitter": "v2 is out"}
        # Thinking counts toward max_tokens, so leave room for it and the drafts.
        assert mock_client.messages.create.call_args[1]["max_tokens"] >= 16000

    # These two check the exception by name, so on code without ComposeError
    # they fail on the behavior (AttributeError, or no error) and not on an import.

    @patch("herald.composer.anthropic.Anthropic")
    def test_compose_without_text_raises(self, mock_anthropic_cls):
        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.create.return_value = MagicMock(
            content=[ThinkingBlock(type="thinking", thinking="", signature="sig")],
            stop_reason="end_turn",
        )

        with pytest.raises(Exception) as raised:
            compose([Artifacts(commits=[Commit("a", "A", "2026-01-01", "fix")])], api_key="k")
        assert type(raised.value).__name__ == "ComposeError", repr(raised.value)
        assert "returned no text" in str(raised.value)

    @pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
    @patch("herald.composer.anthropic.Anthropic")
    def test_compose_rejects_an_unfinished_reply(self, mock_anthropic_cls, stop_reason):
        # A reply cut off by max_tokens (thinking counts toward it) or by a
        # refusal is unfinished. It used to fall through to the plain-text
        # fallback, which made the cut-off JSON the draft for every platform.
        mock_client = mock_anthropic_cls.return_value
        mock_client.messages.create.return_value = MagicMock(
            content=[_text('{"discord": "Shipped v2 with the new')],
            stop_reason=stop_reason,
        )

        with pytest.raises(Exception) as raised:
            compose([Artifacts(commits=[Commit("a", "A", "2026-01-01", "fix")])], api_key="k")
        assert type(raised.value).__name__ == "ComposeError", repr(raised.value)
        assert stop_reason in str(raised.value)


class TestComposeWithConsilium:
    def test_uses_consilium_council(self, monkeypatch):
        import sys
        import types

        from herald.composer import compose_with_consilium

        calls = {}

        class FakeCouncil:
            def __init__(self, models=None, chairman=None):
                calls["models"] = models
                calls["chairman"] = chairman

            def ask(self, prompt, system=None, budget=None):
                calls["prompt"] = prompt
                calls["system"] = system
                return MagicMock(final_answer=json.dumps({"discord": "council draft"}))

        fake = types.ModuleType("consilium")
        fake.Council = FakeCouncil
        monkeypatch.setitem(sys.modules, "consilium", fake)

        artifacts = [Artifacts(
            repo_name="test/repo",
            commits=[Commit("abc", "Alice", "2026-01-01", "feat: X")],
        )]
        result = compose_with_consilium(artifacts, content_type="digest")
        assert result == {"discord": "council draft"}
        assert calls["models"] and calls["chairman"]
        assert "feat: X" in calls["prompt"]
        assert "Writing style guide" in calls["system"]

    def test_missing_consilium_names_the_install_command(self, monkeypatch):
        import sys

        from herald.composer import compose_with_consilium

        monkeypatch.setitem(sys.modules, "consilium", None)
        with pytest.raises(ImportError, match=r"herald-announce\[consilium\]"):
            compose_with_consilium([], content_type="digest")
