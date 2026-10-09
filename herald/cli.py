"""CLI interface for herald."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="herald",
    help="LLM-powered social media announcements from your git history.",
    no_args_is_help=True,
)
console = Console()


def _get_settings(**overrides):
    from herald.config import get_settings
    return get_settings(**overrides)


@app.command()
def collect(
    repos: str = typer.Option("", help="Comma-separated repos (owner/repo or local paths)"),
    days: int = typer.Option(7, help="Look back this many days"),
    github_token: str = typer.Option("", envvar="HERALD_GITHUB_TOKEN", help="GitHub token"),
):
    """Collect artifacts from repos and display them."""
    from herald.collector import collect_all

    settings = _get_settings()
    repo_list = [r.strip() for r in repos.split(",") if r.strip()] if repos else settings.repo_list

    if not repo_list:
        console.print("[red]No repos configured. Use --repos or set HERALD_REPOS.[/red]")
        raise typer.Exit(1)

    token = github_token or settings.github_token
    artifacts_list = collect_all(repo_list, since_days=days, github_token=token)

    if not artifacts_list:
        console.print("[yellow]No artifacts found in the last {days} days.[/yellow]")
        raise typer.Exit(0)

    for artifacts in artifacts_list:
        console.print(Panel(
            artifacts.to_prompt_text(),
            title=f"[bold]{artifacts.repo_name}[/bold]",
        ))

    total = sum(
        len(a.commits) + len(a.releases) + len(a.pull_requests)
        for a in artifacts_list
    )
    console.print(f"\n[green]Collected {total} artifacts from {len(artifacts_list)} repos.[/green]")


@app.command()
def compose(
    repos: str = typer.Option("", help="Comma-separated repos"),
    days: int = typer.Option(7, help="Look back this many days"),
    content_type: str = typer.Option("release", help="Content type: release, digest, spotlight"),
    model: str = typer.Option("", help="LLM model to use"),
    project_context: str = typer.Option("", help="Extra context about the project"),
    use_consilium: bool = typer.Option(False, help="Use consilium multi-model council"),
):
    """Compose social media content from collected artifacts."""
    from herald.collector import collect_all
    from herald.composer import compose as compose_content
    from herald.composer import compose_with_consilium

    settings = _get_settings()
    repo_list = [r.strip() for r in repos.split(",") if r.strip()] if repos else settings.repo_list

    if not repo_list:
        console.print("[red]No repos configured.[/red]")
        raise typer.Exit(1)

    artifacts_list = collect_all(
        repo_list,
        since_days=days,
        github_token=settings.github_token,
    )

    if not artifacts_list:
        console.print("[yellow]No artifacts found.[/yellow]")
        raise typer.Exit(0)

    console.print("[dim]Composing content...[/dim]")

    if use_consilium or settings.use_consilium:
        content = compose_with_consilium(
            artifacts_list,
            content_type=content_type,
            project_context=project_context,
        )
    else:
        content = compose_content(
            artifacts_list,
            content_type=content_type,
            api_key=settings.anthropic_api_key,
            model=model or settings.default_model,
            project_context=project_context,
        )

    for platform, text in content.items():
        console.print(Panel(str(text), title=f"[bold]{platform}[/bold]"))


@app.command()
def publish(
    repos: str = typer.Option("", help="Comma-separated repos"),
    days: int = typer.Option(7, help="Look back this many days"),
    content_type: str = typer.Option("release", help="Content type: release, digest, spotlight"),
    model: str = typer.Option("", help="LLM model to use"),
    project_context: str = typer.Option("", help="Extra context about the project"),
    platforms: str = typer.Option(
        "", help="Comma-separated platforms to publish to (default: all)"
    ),
    embed_title: str = typer.Option("", help="Title for Discord embeds"),
    username: str = typer.Option("", help="Display name for bot posts"),
    dry_run: bool = typer.Option(False, help="Preview without posting"),
    use_consilium: bool = typer.Option(False, help="Use consilium multi-model council"),
):
    """Collect, compose, and publish in one step."""
    from herald.collector import collect_all
    from herald.composer import compose as compose_content
    from herald.composer import compose_with_consilium
    from herald.publisher import get_publishers, publish_content

    settings = _get_settings()
    repo_list = [r.strip() for r in repos.split(",") if r.strip()] if repos else settings.repo_list

    if not repo_list:
        console.print("[red]No repos configured.[/red]")
        raise typer.Exit(1)

    # Collect
    console.print("[dim]Collecting artifacts...[/dim]")
    artifacts_list = collect_all(
        repo_list,
        since_days=days,
        github_token=settings.github_token,
    )

    if not artifacts_list:
        console.print("[yellow]No artifacts found. Nothing to publish.[/yellow]")
        raise typer.Exit(0)

    total = sum(
        len(a.commits) + len(a.releases) + len(a.pull_requests)
        for a in artifacts_list
    )
    console.print(f"[green]Found {total} artifacts.[/green]")

    # Compose
    console.print("[dim]Composing content...[/dim]")
    if use_consilium or settings.use_consilium:
        content = compose_with_consilium(
            artifacts_list,
            content_type=content_type,
            project_context=project_context,
        )
    else:
        content = compose_content(
            artifacts_list,
            content_type=content_type,
            api_key=settings.anthropic_api_key,
            model=model or settings.default_model,
            project_context=project_context,
        )

    # Preview
    for platform, text in content.items():
        console.print(Panel(str(text), title=f"[bold]{platform}[/bold]"))

    # Publish
    publishers = get_publishers(settings)

    if platforms:
        platform_filter = {p.strip() for p in platforms.split(",")}
        publishers = [p for p in publishers if p.platform_name in platform_filter]

    if not publishers:
        console.print("[yellow]No platforms configured for publishing.[/yellow]")
        raise typer.Exit(0)

    is_dry = dry_run or settings.dry_run
    if is_dry:
        console.print("[yellow]DRY RUN — not actually posting.[/yellow]")

    report = publish_content(
        content,
        publishers,
        dry_run=is_dry,
        embed_title=embed_title,
        username=username,
    )

    console.print("\n[bold]Publish results:[/bold]")
    console.print(report.summary)

    if not report.all_success:
        raise typer.Exit(1)


@app.command()
def post(
    file: str = typer.Option(..., "--file", help="UTF-8 text file to post exactly as written"),
    platform: str = typer.Option("x", help="x (posts) or linkedin (always manual)"),
    ledger: str = typer.Option(
        "", envvar="HERALD_POST_LEDGER",
        help="Append-only JSON Lines ledger. Required for a live post.",
    ),
    expect_sha256: str = typer.Option(
        "",
        help="Refuse unless the text's SHA-256 (without trailing newlines) equals this "
        "approved hash. --dry-run --json prints it as content_sha256.",
    ),
    dry_run: bool = typer.Option(
        False, help="Run the local checks (hash, length, ledger); never open the X account"
    ),
    retry: bool = typer.Option(
        False,
        help="Post again after a check of recent posts found no match for an "
        "uncertain attempt",
    ),
    precheck_timeline: bool = typer.Option(
        False, help="Read the account's recent posts first and skip if the text is there"
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the result as JSON"),
):
    """Post an approved file verbatim. No model call, no truncation.

    Exit codes: 0 published, 3 not sent, 4 uncertain (a post may exist;
    the next run checks the account's recent posts before sending again).
    """
    import json
    from pathlib import Path

    from herald.verbatim import (
        LINKEDIN_MANUAL_MESSAGE,
        Ledger,
        Outcome,
        PostResult,
        TweepyXAccount,
        VerbatimError,
        VerbatimXPoster,
        content_sha256,
        read_post_file,
        x_weighted_length,
    )

    def finish(result: PostResult) -> None:
        if json_output:
            typer.echo(json.dumps(result.to_dict(), sort_keys=True))
        else:
            typer.echo(f"outcome: {result.outcome.value}")
            typer.echo(f"platform: {result.platform}")
            typer.echo(f"content_sha256: {result.content_sha256}")
            if result.weighted_length is not None:
                typer.echo(f"weighted_length: {result.weighted_length}")
            if result.url:
                typer.echo(f"url: {result.url}")
            typer.echo(f"message: {result.message}")
        raise typer.Exit(result.exit_code)

    target = platform.strip().lower()
    try:
        text = read_post_file(Path(file))
    except VerbatimError as exc:
        finish(PostResult(Outcome.NOT_SENT, target, "", str(exc)))
        return

    sha = content_sha256(text)
    if target == "linkedin":
        finish(PostResult(Outcome.NOT_SENT, "linkedin", sha, LINKEDIN_MANUAL_MESSAGE))
        return
    if target not in {"x", "twitter"}:
        finish(PostResult(Outcome.NOT_SENT, target, sha,
                          f"verbatim posting supports x only, not {platform!r}",
                          weighted_length=x_weighted_length(text)))
        return

    settings = _get_settings()

    def account_factory():
        return TweepyXAccount(
            consumer_key=settings.twitter_consumer_key,
            consumer_secret=settings.twitter_consumer_secret,
            access_token=settings.twitter_access_token,
            access_token_secret=settings.twitter_access_token_secret,
        )

    # The option also reads HERALD_POST_LEDGER from the process environment;
    # the settings fallback picks it up from a .env file.
    ledger_path = ledger or settings.post_ledger
    poster = VerbatimXPoster(account_factory, Ledger(Path(ledger_path)) if ledger_path else None)
    result = poster.post(
        text,
        expect_sha256=expect_sha256,
        dry_run=dry_run,
        retry=retry,
        precheck_timeline=precheck_timeline,
    )
    finish(result)


@app.command()
def preview(
    repos: str = typer.Option("", help="Comma-separated repos"),
    days: int = typer.Option(7, help="Look back this many days"),
    content_type: str = typer.Option("release", help="Content type: release, digest, spotlight"),
    model: str = typer.Option("", help="LLM model to use"),
    project_context: str = typer.Option("", help="Extra context about the project"),
):
    """Shortcut for compose — shows content without publishing."""
    compose(
        repos=repos,
        days=days,
        content_type=content_type,
        model=model,
        project_context=project_context,
        use_consilium=False,
    )


if __name__ == "__main__":
    app()
