"""Collect artifacts from git repos and GitHub API."""

from __future__ import annotations

import json
import os
import subprocess
import sys
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


def _run_gh(cmd: list[str], what: str, github_token: str) -> str | None:
    """Run a gh command and return its output, or None after printing why it failed.

    A failure here would otherwise look like a repository with nothing new.
    """
    env = {**os.environ, "GH_TOKEN": github_token} if github_token else None
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
    except FileNotFoundError:
        _warn(f"couldn't read {what}: the gh command isn't installed.")
        return None
    except subprocess.TimeoutExpired:
        _warn(f"couldn't read {what}: gh didn't answer within 30 seconds.")
        return None
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines() if isinstance(result.stderr, str) else []
        reason = detail[-1] if detail else f"gh exited with code {result.returncode}"
        _warn(f"couldn't read {what}: {reason}")
        return None
    return result.stdout


def _warn(message: str) -> None:
    print(f"herald: {message}", file=sys.stderr)


def collect_github_releases(
    repo: str,
    since_days: int = 7,
    github_token: str = "",
) -> list[Release]:
    """Collect published releases from a GitHub repo via gh CLI.

    Drafts have no publish date, so they're skipped.
    """
    what = f"releases for {repo}"
    stdout = _run_gh(["gh", "api", f"repos/{repo}/releases"], what, github_token)
    if stdout is None:
        return []

    # Parse the JSON rather than one line per release: release notes span
    # many lines and can contain any separator.
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        _warn(f"couldn't read {what}: gh returned something other than JSON.")
        return []
    if not isinstance(data, list):
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    releases = []
    for item in data:
        published = item.get("published_at") or ""
        if not published:
            continue
        try:
            pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            if pub_dt < cutoff:
                continue
        except ValueError:
            pass
        releases.append(Release(
            tag=item.get("tag_name") or "",
            name=item.get("name") or "",
            body=item.get("body") or "",
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
    what = f"merged pull requests for {repo}"
    stdout = _run_gh(cmd, what, github_token)
    if stdout is None:
        return []

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        _warn(f"couldn't read {what}: gh returned something other than JSON.")
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


def _git_root(path: Path) -> Path | None:
    """Return the top folder of the git checkout that contains path, if any."""
    try:
        path = path.expanduser().resolve()
    except OSError:
        return None
    if not path.exists():
        return None
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _looks_like_github_repo(repo: str) -> bool:
    """True for "owner/repo"; false for paths such as "/x", "./x" or "../x"."""
    return "/" in repo and not repo.startswith(("/", ".", "~"))


def collect_all(
    repos: list[str],
    since_days: int = 7,
    github_token: str = "",
    local_base: str | Path | None = None,
) -> list[Artifacts]:
    """Collect artifacts from multiple repos.

    Each repo can be:
    - A GitHub "owner/repo" string (fetches releases + PRs via API)
    - A local path inside a git checkout (fetches git commits). The artifacts
      are named after the checkout's folder, so "." gets a real name.
    """
    all_artifacts = []

    for repo in repos:
        artifacts = Artifacts(repo_name=repo)
        is_github = _looks_like_github_repo(repo)

        # Check if it's a local path
        repo_path = Path(repo)
        if not repo_path.is_absolute() and local_base:
            # Try treating as relative to local_base
            candidate = Path(local_base) / repo.split("/")[-1]
            if candidate.exists():
                repo_path = candidate

        if is_github:
            # Only a clone found under local_base, never an enclosing checkout.
            root = repo_path if (repo_path / ".git").exists() else None
        else:
            root = _git_root(repo_path)
        if root is not None:
            artifacts.commits = collect_git_commits(root, since_days=since_days)
            if not is_github:
                artifacts.repo_name = root.name

        # If it looks like owner/repo, try GitHub API
        if is_github:
            artifacts.releases = collect_github_releases(
                repo, since_days=since_days, github_token=github_token
            )
            artifacts.pull_requests = collect_github_prs(
                repo, since_days=since_days, github_token=github_token
            )

        if not artifacts.is_empty:
            all_artifacts.append(artifacts)

    return all_artifacts
