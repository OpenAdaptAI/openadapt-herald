"""Tests for the collector module."""

import json
import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from herald.collector import (
    Artifacts,
    Commit,
    PullRequest,
    Release,
    collect_all,
    collect_git_commits,
    collect_github_prs,
    collect_github_releases,
)


def _iso_days_ago(days: float) -> str:
    """A GitHub-style UTC timestamp `days` before now.

    The collectors filter by a window relative to `datetime.now`, so fixtures
    that must fall inside (or outside) that window have to be computed relative
    to now too. A hardcoded literal only stays inside a 7-day window for 7 days.
    """
    moment = datetime.now(timezone.utc) - timedelta(days=days)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class TestCommitCollection:
    def test_collect_git_commits_no_git_dir(self, tmp_path):
        """Returns empty list if .git doesn't exist."""
        result = collect_git_commits(tmp_path, since_days=7)
        assert result == []

    @patch("herald.collector.subprocess.run")
    def test_collect_git_commits_parses_output(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "abc123|Alice|2026-02-28T10:00:00+00:00|feat: add login\n"
                "def456|Bob|2026-02-27T09:00:00+00:00|fix: typo\n"
            ),
        )
        result = collect_git_commits(tmp_path, since_days=7)
        assert len(result) == 2
        assert result[0].hash == "abc123"
        assert result[0].author == "Alice"
        assert result[0].message == "feat: add login"
        assert result[0].repo == tmp_path.name
        assert result[1].hash == "def456"

    @patch("herald.collector.subprocess.run")
    def test_collect_git_commits_with_tag(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        collect_git_commits(tmp_path, since_tag="v1.0.0")
        cmd = mock_run.call_args[0][0]
        assert "v1.0.0..HEAD" in cmd

    @patch("herald.collector.subprocess.run")
    def test_collect_git_commits_failure(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = collect_git_commits(tmp_path)
        assert result == []

    @patch("herald.collector.subprocess.run")
    def test_collect_git_commits_timeout(self, mock_run, tmp_path):
        (tmp_path / ".git").mkdir()
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        result = collect_git_commits(tmp_path)
        assert result == []


class TestGitHubReleases:
    @patch("herald.collector.subprocess.run")
    def test_collect_releases_parses_output(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "v1.0.0|Release 1.0|Bug fixes and improvements"
                f"|{_iso_days_ago(1)}\n"
            ),
        )
        result = collect_github_releases("owner/repo", since_days=7)
        assert len(result) == 1
        assert result[0].tag == "v1.0.0"
        assert result[0].name == "Release 1.0"
        assert result[0].repo == "owner/repo"

    @patch("herald.collector.subprocess.run")
    def test_collect_releases_filters_old(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="v0.1.0|Old|Old stuff|2020-01-01T00:00:00Z\n",
        )
        result = collect_github_releases("owner/repo", since_days=7)
        assert result == []

    @patch("herald.collector.subprocess.run")
    def test_collect_releases_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = collect_github_releases("owner/repo")
        assert result == []

    @patch("herald.collector.subprocess.run")
    def test_collect_releases_with_token(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        collect_github_releases("owner/repo", github_token="ghp_test123")
        env = mock_run.call_args[1].get("env", {})
        assert env.get("GH_TOKEN") == "ghp_test123"


class TestGitHubPRs:
    @patch("herald.collector.subprocess.run")
    def test_collect_prs_parses_json(self, mock_run):
        data = [
            {
                "number": 42,
                "title": "feat: add auth",
                "body": "Added authentication",
                "mergedAt": _iso_days_ago(1),
                "author": {"login": "alice"},
            }
        ]
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(data),
        )
        result = collect_github_prs("owner/repo", since_days=7)
        assert len(result) == 1
        assert result[0].number == 42
        assert result[0].title == "feat: add auth"
        assert result[0].author == "alice"

    @patch("herald.collector.subprocess.run")
    def test_collect_prs_filters_old(self, mock_run):
        data = [
            {
                "number": 1,
                "title": "old PR",
                "body": "",
                "mergedAt": "2020-01-01T00:00:00Z",
                "author": {"login": "bob"},
            }
        ]
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(data),
        )
        result = collect_github_prs("owner/repo", since_days=7)
        assert result == []

    @patch("herald.collector.subprocess.run")
    def test_collect_prs_bad_json(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="not json")
        result = collect_github_prs("owner/repo")
        assert result == []


class TestArtifacts:
    def test_is_empty(self):
        a = Artifacts()
        assert a.is_empty

    def test_not_empty_with_commits(self):
        a = Artifacts(commits=[Commit("abc", "Alice", "2026-01-01", "test")])
        assert not a.is_empty

    def test_to_prompt_text(self):
        a = Artifacts(
            repo_name="test/repo",
            commits=[Commit("abc123", "Alice", "2026-01-01", "feat: new thing")],
            releases=[Release("v1.0", "v1.0", "Release notes", "2026-01-01")],
        )
        text = a.to_prompt_text()
        assert "test/repo" in text
        assert "v1.0" in text
        assert "feat: new thing" in text
        assert "abc123" in text

    def test_to_prompt_text_truncates_long_pr_body(self):
        long_body = "x" * 600
        a = Artifacts(
            pull_requests=[PullRequest(1, "test", long_body, "2026-01-01", "alice")]
        )
        text = a.to_prompt_text()
        assert "..." in text


class TestCollectAll:
    @patch("herald.collector.collect_github_prs")
    @patch("herald.collector.collect_github_releases")
    @patch("herald.collector.collect_git_commits")
    def test_collect_all_github_repo(self, mock_commits, mock_releases, mock_prs):
        mock_commits.return_value = []
        mock_releases.return_value = [
            Release("v1.0", "v1.0", "notes", "2026-01-01", "org/repo")
        ]
        mock_prs.return_value = []

        result = collect_all(["org/repo"], since_days=7)
        assert len(result) == 1
        assert result[0].repo_name == "org/repo"
        assert len(result[0].releases) == 1

    @patch("herald.collector.collect_git_commits")
    def test_collect_all_local_repo(self, mock_commits, tmp_path):
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        mock_commits.return_value = [
            Commit("abc", "Alice", "2026-01-01", "fix: bug", "myrepo")
        ]

        result = collect_all([str(repo_dir)], since_days=7)
        assert len(result) == 1

    @patch("herald.collector.collect_github_prs")
    @patch("herald.collector.collect_github_releases")
    @patch("herald.collector.collect_git_commits")
    def test_collect_all_skips_empty(self, mock_commits, mock_releases, mock_prs):
        mock_commits.return_value = []
        mock_releases.return_value = []
        mock_prs.return_value = []

        result = collect_all(["org/empty-repo"], since_days=7)
        assert result == []
