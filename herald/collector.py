"""Collect artifacts from git repos and GitHub API."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class Commit:
    hash: str
    author: str
    date: str
    message: str
    repo: str = ""


@dataclass
class Release:
    tag: str
    name: str
    body: str
    published_at: str
    repo: str = ""


@dataclass
class PullRequest:
    number: int
    title: str
    body: str
    merged_at: str
    author: str
    repo: str = ""


@dataclass
class Artifacts:
    commits: list[Commit] = field(default_factory=list)
    releases: list[Release] = field(default_factory=list)
    pull_requests: list[PullRequest] = field(default_factory=list)
    repo_name: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.commits and not self.releases and not self.pull_requests

    def to_prompt_text(self) -> str:
        """Format artifacts as text for an LLM prompt."""
        parts = []
        if self.repo_name:
            parts.append(f"Repository: {self.repo_name}")

        if self.releases:
            parts.append("\n## Releases")
            for r in self.releases:
                parts.append(f"\n### {r.tag} ({r.name})")
                parts.append(f"Published: {r.published_at}")
                if r.body:
                    parts.append(r.body)

        if self.pull_requests:
            parts.append("\n## Merged pull requests")
            for pr in self.pull_requests:
                line = f"\n- #{pr.number}: {pr.title}"
                line += f" (by @{pr.author}, merged {pr.merged_at})"
                parts.append(line)
                if pr.body:
                    # Truncate long PR bodies
                    body = pr.body[:500] + "..." if len(pr.body) > 500 else pr.body
                    parts.append(f"  {body}")

        if self.commits:
            parts.append("\n## Commits")
            for c in self.commits:
                parts.append(f"- {c.hash[:8]} {c.message} ({c.author}, {c.date})")

        return "\n".join(parts)


def collect_git_commits(
    repo_path: str | Path,
    since_days: int = 7,
    since_tag: str | None = None,
) -> list[Commit]:
    """Collect commits from a local git repo."""
    repo_path = Path(repo_path)
    if not (repo_path / ".git").exists():
        return []

    cmd = ["git", "-C", str(repo_path), "log", "--format=%H|%an|%aI|%s"]
    if since_tag:
        cmd.append(f"{since_tag}..HEAD")
    else:
        since_date = datetime.now(timezone.utc) - timedelta(days=since_days)
        cmd.extend(["--since", since_date.isoformat()])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    commits = []
    repo_name = repo_path.name
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 3)
        if len(parts) == 4:
            commits.append(Commit(
                hash=parts[0],
                author=parts[1],
                date=parts[2],
                message=parts[3],
                repo=repo_name,
            ))
    return commits


def collect_github_releases(
    repo: str,
    since_days: int = 7,
    github_token: str = "",
) -> list[Release]:
    """Collect releases from a GitHub repo via gh CLI."""
    cmd = [
        "gh", "api",
        f"repos/{repo}/releases",
        "--jq", ".[].tag_name + \"|\" + .name + \"|\" + .body + \"|\" + .published_at",
    ]
    env_additions = {}
    if github_token:
        env_additions["GH_TOKEN"] = github_token

    try:
        import os
        env = {**os.environ, **env_additions} if env_additions else None
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    releases = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 3)
        if len(parts) >= 4:
            published = parts[3]
            try:
                pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                if pub_dt < cutoff:
                    continue
            except ValueError:
                pass
            releases.append(Release(
                tag=parts[0],
                name=parts[1],
                body=parts[2],
                published_at=published,
                repo=repo,
            ))
    return releases


def collect_github_prs(
    repo: str,
    since_days: int = 7,
    github_token: str = "",
) -> list[PullRequest]:
    """Collect recently merged PRs from a GitHub repo via gh CLI."""
    since_date = datetime.now(timezone.utc) - timedelta(days=since_days)
    cmd = [
        "gh", "pr", "list",
        "--repo", repo,
        "--state", "merged",
        "--limit", "50",
        "--json", "number,title,body,mergedAt,author",
    ]
    env_additions = {}
    if github_token:
        env_additions["GH_TOKEN"] = github_token

    try:
        import os
        env = {**os.environ, **env_additions} if env_additions else None
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    prs = []
    for item in data:
        merged_at = item.get("mergedAt", "")
        if merged_at:
            try:
                merged_dt = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
                if merged_dt < since_date:
                    continue
            except ValueError:
                pass

        author = item.get("author", {})
        author_login = author.get("login", "") if isinstance(author, dict) else str(author)

        prs.append(PullRequest(
            number=item.get("number", 0),
            title=item.get("title", ""),
            body=item.get("body", ""),
            merged_at=merged_at,
            author=author_login,
            repo=repo,
        ))
    return prs


def collect_all(
    repos: list[str],
    since_days: int = 7,
    github_token: str = "",
    local_base: str | Path | None = None,
) -> list[Artifacts]:
    """Collect artifacts from multiple repos.

    Each repo can be:
    - A GitHub "owner/repo" string (fetches releases + PRs via API)
    - A local path (fetches git commits)
    """
    all_artifacts = []

    for repo in repos:
        artifacts = Artifacts(repo_name=repo)

        # Check if it's a local path
        repo_path = Path(repo)
        if not repo_path.is_absolute() and local_base:
            # Try treating as relative to local_base
            candidate = Path(local_base) / repo.split("/")[-1]
            if candidate.exists():
                repo_path = candidate

        if repo_path.exists() and (repo_path / ".git").exists():
            artifacts.commits = collect_git_commits(repo_path, since_days=since_days)

        # If it looks like owner/repo, try GitHub API
        if "/" in repo and not repo.startswith("/"):
            artifacts.releases = collect_github_releases(
                repo, since_days=since_days, github_token=github_token
            )
            artifacts.pull_requests = collect_github_prs(
                repo, since_days=since_days, github_token=github_token
            )

        if not artifacts.is_empty:
            all_artifacts.append(artifacts)

    return all_artifacts
