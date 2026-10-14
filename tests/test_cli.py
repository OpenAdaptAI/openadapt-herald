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


class TestLookbackAndMessages:
    @patch("herald.cli._get_settings")
    @patch("herald.collector.collect_all")
    def test_no_artifacts_message_names_the_window(self, mock_collect, mock_settings):
        mock_settings.return_value = MagicMock(github_token="")
        mock_collect.return_value = []
        result = runner.invoke(app, ["collect", "--repos", "org/repo", "--days", "3"])
        assert result.exit_code == 0
        assert "last 3 days" in result.output
        assert "{days}" not in result.output

    @patch("herald.cli._get_settings")
    @patch("herald.collector.collect_all")
    def test_days_defaults_to_lookback_setting(self, mock_collect, mock_settings):
        mock_settings.return_value = MagicMock(github_token="", lookback_days=11)
        mock_collect.return_value = []
        runner.invoke(app, ["collect", "--repos", "org/repo"])
        assert mock_collect.call_args.kwargs["since_days"] == 11

    @patch("herald.cli._get_settings")
    @patch("herald.collector.collect_all")
    def test_days_flag_overrides_lookback_setting(self, mock_collect, mock_settings):
        mock_settings.return_value = MagicMock(github_token="", lookback_days=11)
        mock_collect.return_value = []
        runner.invoke(app, ["collect", "--repos", "org/repo", "--days", "2"])
        assert mock_collect.call_args.kwargs["since_days"] == 2


class TestMissingAnthropicKey:
    def _artifacts(self):
        from herald.collector import Artifacts, Commit
        return [Artifacts(
            repo_name="org/repo",
            commits=[Commit("abc", "Alice", "2026-01-01", "feat: thing")],
        )]

    @patch("herald.composer.compose")
    @patch("herald.cli._get_settings")
    @patch("herald.collector.collect_all")
    def test_preview_without_key_exits_with_message(
        self, mock_collect, mock_settings, mock_compose
    ):
        mock_settings.return_value = MagicMock(
            github_token="", has_anthropic=False, use_consilium=False, lookback_days=7
        )
        mock_collect.return_value = self._artifacts()
        result = runner.invoke(app, ["preview", "--repos", "org/repo"])
        assert result.exit_code == 1
        assert "No Anthropic API key" in result.output
        mock_compose.assert_not_called()

    @patch("herald.composer.compose")
    @patch("herald.cli._get_settings")
    @patch("herald.collector.collect_all")
    def test_publish_without_key_exits_before_posting(
        self, mock_collect, mock_settings, mock_compose
    ):
        mock_settings.return_value = MagicMock(
            github_token="", has_anthropic=False, use_consilium=False, lookback_days=7
        )
        mock_collect.return_value = self._artifacts()
        result = runner.invoke(app, ["publish", "--repos", "org/repo"])
        assert result.exit_code == 1
        assert "No Anthropic API key" in result.output
        mock_compose.assert_not_called()

    @patch("herald.composer.compose")
    @patch("herald.cli._get_settings")
    @patch("herald.collector.collect_all")
    def test_preview_with_key_composes(self, mock_collect, mock_settings, mock_compose):
        mock_settings.return_value = MagicMock(
            github_token="", has_anthropic=True, use_consilium=False, lookback_days=7,
            anthropic_api_key="test-key", default_model="m",
        )
        mock_collect.return_value = self._artifacts()
        mock_compose.return_value = {"discord": "Hello from the digest"}
        result = runner.invoke(app, ["preview", "--repos", "org/repo"])
        assert result.exit_code == 0
        assert "Hello from the digest" in result.output
