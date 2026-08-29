"""CLI interface for herald."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel

app = typer.Typer(
    name="herald",
    help="Internal social-copy tooling. Not the OpenAdapt product.",
    no_args_is_help=True,
)
console = Console()


def _get_settings(**overrides):
    from herald.config import get_settings
    return get_settings(**overrides)


def _compose_payload(
    artifacts_list,
    *,
    content_type: str,
    project_context: str,
    template: bool,
    use_consilium: bool,
    api_key: str,
    model: str,
):
    from herald.composer import compose as compose_content
    from herald.composer import compose_from_template, compose_with_consilium

    if template:
        return compose_from_template(
            artifacts_list,
            content_type=content_type,
        )
    if use_consilium:
        return compose_with_consilium(
            artifacts_list,
            content_type=content_type,
            project_context=project_context,
        )
    return compose_content(
        artifacts_list,
        content_type=content_type,
        api_key=api_key,
        model=model,
        project_context=project_context,
    )


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
    template: bool = typer.Option(
        False,
        "--template",
        help="Fill a product-correct template. No Anthropic call.",
    ),
):
    """Compose social media content from collected artifacts."""
    from herald.collector import collect_all

    settings = _get_settings()
    repo_list = [r.strip() for r in repos.split(",") if r.strip()] if repos else settings.repo_list

    # Spotlight --template is the canned --break-it example. No repos, no LLM.
    if template and content_type == "spotlight" and not repo_list:
        artifacts_list = []
    else:
        if not repo_list:
            console.print("[red]No repos configured.[/red]")
            raise typer.Exit(1)

        artifacts_list = collect_all(
            repo_list,
            since_days=days,
            github_token=settings.github_token,
        )

        if not artifacts_list and not template:
            console.print("[yellow]No artifacts found.[/yellow]")
            raise typer.Exit(0)

    console.print("[dim]Composing content...[/dim]")
    content = _compose_payload(
        artifacts_list,
        content_type=content_type,
        project_context=project_context,
        template=template,
        use_consilium=use_consilium or settings.use_consilium,
        api_key=settings.anthropic_api_key,
        model=model or settings.default_model,
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
    template: bool = typer.Option(
        False,
        "--template",
        help="Fill a product-correct template. No Anthropic call.",
    ),
):
    """Collect, compose, and publish in one step."""
    from herald.collector import collect_all
    from herald.publisher import get_publishers, publish_content

    settings = _get_settings()
    repo_list = [r.strip() for r in repos.split(",") if r.strip()] if repos else settings.repo_list

    if template and content_type == "spotlight" and not repo_list:
        artifacts_list = []
        total = 0
    else:
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

        if not artifacts_list and not template:
            console.print("[yellow]No artifacts found. Nothing to publish.[/yellow]")
            raise typer.Exit(0)

        total = sum(
            len(a.commits) + len(a.releases) + len(a.pull_requests)
            for a in artifacts_list
        )
        console.print(f"[green]Found {total} artifacts.[/green]")

    # Compose
    console.print("[dim]Composing content...[/dim]")
    content = _compose_payload(
        artifacts_list,
        content_type=content_type,
        project_context=project_context,
        template=template,
        use_consilium=use_consilium or settings.use_consilium,
        api_key=settings.anthropic_api_key,
        model=model or settings.default_model,
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
def preview(
    repos: str = typer.Option("", help="Comma-separated repos"),
    days: int = typer.Option(7, help="Look back this many days"),
    content_type: str = typer.Option("release", help="Content type: release, digest, spotlight"),
    model: str = typer.Option("", help="LLM model to use"),
    project_context: str = typer.Option("", help="Extra context about the project"),
    template: bool = typer.Option(
        False,
        "--template",
        help="Fill a product-correct template. No Anthropic call.",
    ),
):
    """Shortcut for compose. Shows content without publishing."""
    compose(
        repos=repos,
        days=days,
        content_type=content_type,
        model=model,
        project_context=project_context,
        use_consilium=False,
        template=template,
    )


if __name__ == "__main__":
    app()
