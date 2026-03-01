"""Configuration via environment variables and .env files."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class HeraldSettings(BaseSettings):
    """Herald configuration. All values can be set via HERALD_ prefixed env vars."""

    model_config = SettingsConfigDict(
        env_prefix="HERALD_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    default_model: str = "claude-sonnet-4-20250514"

    # Discord
    discord_webhook_url: str = ""

    # Twitter/X
    twitter_consumer_key: str = ""
    twitter_consumer_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_token_secret: str = ""

    # GitHub
    github_token: str = ""
    github_org: str = ""

    # Repos (comma-separated: "owner/repo" or local paths)
    repos: str = ""

    # Defaults
    lookback_days: int = 7
    use_consilium: bool = False
    dry_run: bool = False

    @property
    def repo_list(self) -> list[str]:
        if not self.repos:
            return []
        return [r.strip() for r in self.repos.split(",") if r.strip()]

    @property
    def has_discord(self) -> bool:
        return bool(self.discord_webhook_url)

    @property
    def has_twitter(self) -> bool:
        return all([
            self.twitter_consumer_key,
            self.twitter_consumer_secret,
            self.twitter_access_token,
            self.twitter_access_token_secret,
        ])

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)


def get_settings(**overrides: str) -> HeraldSettings:
    """Load settings with optional overrides."""
    return HeraldSettings(**overrides)
