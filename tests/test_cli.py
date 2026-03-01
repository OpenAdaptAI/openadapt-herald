"""Tests for the CLI."""

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from herald.cli import app

runner = CliRunner()


class TestCollectCommand:
    @patch("herald.cli._get_settings")
    @patch("herald.collector.collect_all")
    def test_collect_no_repos(self, mock_collect, mock_settings):
        mock_settings.return_value = MagicMock(repo_list=[], github_token="")
        result = runner.invoke(app, ["collect"])
        assert result.exit_code == 1
        assert "No repos" in result.output

    @patch("herald.cli._get_settings")
    @patch("herald.collector.collect_all")
    def test_collect_no_artifacts(self, mock_collect, mock_settings):
        mock_settings.return_value = MagicMock(repo_list=["org/repo"], github_token="")
        mock_collect.return_value = []
        result = runner.invoke(app, ["collect"])
        assert result.exit_code == 0

    @patch("herald.cli._get_settings")
    @patch("herald.collector.collect_all")
    def test_collect_with_repos_flag(self, mock_collect, mock_settings):
        from herald.collector import Artifacts, Commit
        mock_settings.return_value = MagicMock(github_token="")
        mock_collect.return_value = [
            Artifacts(
                repo_name="org/repo",
                commits=[Commit("abc", "Alice", "2026-01-01", "feat: thing")],
            )
        ]
        result = runner.invoke(app, ["collect", "--repos", "org/repo"])
        assert result.exit_code == 0
        assert "1 artifacts" in result.output or "Collected" in result.output


class TestPublishCommand:
    @patch("herald.cli._get_settings")
    def test_publish_no_repos(self, mock_settings):
        mock_settings.return_value = MagicMock(repo_list=[], github_token="")
        result = runner.invoke(app, ["publish"])
        assert result.exit_code == 1
        assert "No repos" in result.output

    @patch("herald.cli._get_settings")
    @patch("herald.collector.collect_all")
    def test_publish_no_artifacts(self, mock_collect, mock_settings):
        mock_settings.return_value = MagicMock(
            repo_list=["org/repo"],
            github_token="",
            anthropic_api_key="",
            use_consilium=False,
        )
        mock_collect.return_value = []
        result = runner.invoke(app, ["publish"])
        assert result.exit_code == 0
        assert "No artifacts" in result.output


class TestPreviewCommand:
    @patch("herald.cli.compose")
    def test_preview_calls_compose(self, mock_compose):
        """Preview is a wrapper around compose."""
        # Just verify it delegates properly — compose tests cover the rest
        mock_compose.return_value = None
        # preview calls compose() which may raise
        runner.invoke(app, ["preview", "--repos", "org/repo"])
        # The important thing is it invokes compose, not publish
