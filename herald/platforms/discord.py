"""Discord webhook publisher."""

from __future__ import annotations

from herald.platforms.base import Publisher, PublishResult


class DiscordPublisher(Publisher):
    """Post messages to Discord via webhook."""

    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url

    @property
    def platform_name(self) -> str:
        return "discord"

    def is_configured(self) -> bool:
        return bool(self._webhook_url)

    def publish(self, content: str, **kwargs) -> PublishResult:
        """Post content to Discord.

        kwargs:
            username: Bot display name (default: "Herald")
            embed_title: If set, post as an embed instead of plain text
            embed_color: Hex color for embed (default: "2105893" / blue)
        """
        from discord_webhook import DiscordEmbed, DiscordWebhook

        username = kwargs.get("username", "Herald")
        embed_title = kwargs.get("embed_title")
        embed_color = kwargs.get("embed_color", 2105893)

        webhook = DiscordWebhook(url=self._webhook_url, username=username)

        if embed_title:
            # Truncate to Discord's 4096-char embed description limit
            truncated = content[:4096] if len(content) > 4096 else content
            embed = DiscordEmbed(
                title=embed_title,
                description=truncated,
                color=embed_color,
            )
            webhook.add_embed(embed)
        else:
            # Truncate to Discord's 2000-char message limit
            webhook.content = content[:2000] if len(content) > 2000 else content

        try:
            response = webhook.execute()
            # discord-webhook returns the response object
            if response and hasattr(response, "status_code"):
                if response.status_code in (200, 204):
                    return PublishResult(
                        platform="discord",
                        success=True,
                        message="Posted to Discord",
                    )
                return PublishResult(
                    platform="discord",
                    success=False,
                    message=f"Discord returned status {response.status_code}",
                )
            # If no response object, assume success (some versions behave differently)
            return PublishResult(
                platform="discord",
                success=True,
                message="Posted to Discord",
            )
        except Exception as e:
            return PublishResult(
                platform="discord",
                success=False,
                message=f"Discord error: {e}",
            )
