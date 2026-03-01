"""Orchestrate publishing across platforms."""

from __future__ import annotations

from dataclasses import dataclass, field

from herald.config import HeraldSettings
from herald.platforms.base import Publisher, PublishResult
from herald.platforms.discord import DiscordPublisher
from herald.platforms.twitter import TwitterPublisher


@dataclass
class PublishReport:
    results: list[PublishResult] = field(default_factory=list)

    @property
    def all_success(self) -> bool:
        return all(r.success for r in self.results)

    @property
    def summary(self) -> str:
        lines = []
        for r in self.results:
            status = "OK" if r.success else "FAILED"
            lines.append(f"  [{status}] {r.platform}: {r.message}")
            if r.url:
                lines.append(f"         {r.url}")
        return "\n".join(lines)


def get_publishers(settings: HeraldSettings) -> list[Publisher]:
    """Build the list of configured publishers from settings."""
    publishers: list[Publisher] = []

    if settings.has_discord:
        publishers.append(DiscordPublisher(settings.discord_webhook_url))

    if settings.has_twitter:
        publishers.append(TwitterPublisher(
            consumer_key=settings.twitter_consumer_key,
            consumer_secret=settings.twitter_consumer_secret,
            access_token=settings.twitter_access_token,
            access_token_secret=settings.twitter_access_token_secret,
        ))

    return publishers


def publish_content(
    content: dict,
    publishers: list[Publisher],
    dry_run: bool = False,
    embed_title: str = "",
) -> PublishReport:
    """Publish composed content to all configured platforms.

    content should be a dict with platform-specific keys like "discord", "twitter".
    Falls back to "summary" or the first available value.
    """
    report = PublishReport()

    for publisher in publishers:
        if not publisher.is_configured():
            report.results.append(PublishResult(
                platform=publisher.platform_name,
                success=False,
                message="Not configured",
            ))
            continue

        # Get platform-specific content, fall back to summary
        platform = publisher.platform_name
        text = content.get(platform, content.get("summary", ""))

        if not text:
            report.results.append(PublishResult(
                platform=platform,
                success=False,
                message="No content for this platform",
            ))
            continue

        if dry_run:
            report.results.append(PublishResult(
                platform=platform,
                success=True,
                message=f"[DRY RUN] Would post: {text[:100]}...",
            ))
            continue

        kwargs = {}
        if platform == "discord" and embed_title:
            kwargs["embed_title"] = embed_title

        result = publisher.publish(text, **kwargs)
        report.results.append(result)

    return report
