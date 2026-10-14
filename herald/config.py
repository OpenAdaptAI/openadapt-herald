"""Configuration via environment variables and .env files."""

from __future__ import annotations

import os

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The one place the default drafting model is named. Use an alias without a
# date suffix: the dated Sonnet 4 snapshot used before started returning 404
# and stopped the weekly digest. Override it with HERALD_DEFAULT_MODEL or
# --model.
DEFAULT_MODEL = "claude-sonnet-5-5"


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

    @model_validator(mode="after")
    def _fallback_api_keys(self):
        """Fall back to non-prefixed env vars for common API keys."""
        if not self.anthropic_api_key:
            self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not self.openai_api_key:
            self.openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        if not self.github_token:
            self.github_token = os.environ.get("GH_TOKEN", "")
        return self
    openai_api_key: str = ""
    default_model: str = DEFAULT_MODEL

    @field_validator("default_model")
    @classmethod
    def _blank_model_means_default(cls, value: str) -> str:
        """An empty HERALD_DEFAULT_MODEL (an unset workflow variable) keeps the default."""
        return value.strip() or DEFAULT_MODEL

    # Discord
    discord_webhook_url: str = ""

    # Twitter/X
    twitter_consumer_key: str = ""
    twitter_consumer_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_token_secret: str = ""

    # LinkedIn
    linkedin_access_token: str = ""

    # GitHub
    github_token: str = ""
    github_org: str = ""

    # Repos (comma-separated: "owner/repo" or local paths)
    repos: str = ""

    # Verbatim posting (`herald post`): append-only ledger path
    post_ledger: str = ""

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
    def has_linkedin(self) -> bool:
        return bool(self.linkedin_access_token)

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)


def get_settings(**overrides: str) -> HeraldSettings:
    """Load settings with optional overrides."""
    return HeraldSettings(**overrides)
