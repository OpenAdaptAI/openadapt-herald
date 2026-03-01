"""Tests for platform publishers."""

from unittest.mock import MagicMock, patch

from herald.platforms.base import PublishResult
from herald.platforms.discord import DiscordPublisher
from herald.platforms.twitter import TwitterPublisher
from herald.publisher import PublishReport, get_publishers, publish_content


class TestDiscordPublisher:
    def test_is_configured_with_url(self):
        pub = DiscordPublisher("https://discord.com/api/webhooks/123/abc")
        assert pub.is_configured()

    def test_is_configured_without_url(self):
        pub = DiscordPublisher("")
        assert not pub.is_configured()

    def test_platform_name(self):
        pub = DiscordPublisher("url")
        assert pub.platform_name == "discord"

    @patch("discord_webhook.DiscordEmbed")
    @patch("discord_webhook.DiscordWebhook")
    def test_publish_with_embed(self, mock_webhook_cls, mock_embed_cls):
        mock_webhook = MagicMock()
        mock_webhook.execute.return_value = MagicMock(status_code=200)
        mock_webhook_cls.return_value = mock_webhook

        pub = DiscordPublisher("https://discord.com/api/webhooks/123/abc")
        result = pub.publish("Test content", embed_title="Release v1.0")

        assert result.success
        assert result.platform == "discord"
        mock_webhook.add_embed.assert_called_once()

    @patch("discord_webhook.DiscordWebhook")
    def test_publish_plain_text(self, mock_webhook_cls):
        mock_webhook = MagicMock()
        mock_webhook.execute.return_value = MagicMock(status_code=204)
        mock_webhook_cls.return_value = mock_webhook

        pub = DiscordPublisher("https://discord.com/api/webhooks/123/abc")
        result = pub.publish("Test content")

        assert result.success
        assert mock_webhook.content == "Test content"

    @patch("discord_webhook.DiscordWebhook")
    def test_publish_truncates_long_content(self, mock_webhook_cls):
        mock_webhook = MagicMock()
        mock_webhook.execute.return_value = MagicMock(status_code=200)
        mock_webhook_cls.return_value = mock_webhook

        pub = DiscordPublisher("https://discord.com/api/webhooks/123/abc")
        long_content = "x" * 3000
        pub.publish(long_content)

        assert len(mock_webhook.content) == 2000

    @patch("discord_webhook.DiscordWebhook")
    def test_publish_handles_error(self, mock_webhook_cls):
        mock_webhook = MagicMock()
        mock_webhook.execute.side_effect = ConnectionError("Network error")
        mock_webhook_cls.return_value = mock_webhook

        pub = DiscordPublisher("https://discord.com/api/webhooks/123/abc")
        result = pub.publish("Test")

        assert not result.success
        assert "Network error" in result.message

    @patch("discord_webhook.DiscordWebhook")
    def test_publish_handles_non_200(self, mock_webhook_cls):
        mock_webhook = MagicMock()
        mock_webhook.execute.return_value = MagicMock(status_code=429)
        mock_webhook_cls.return_value = mock_webhook

        pub = DiscordPublisher("https://discord.com/api/webhooks/123/abc")
        result = pub.publish("Test")

        assert not result.success
        assert "429" in result.message


class TestTwitterPublisher:
    def test_is_configured_all_keys(self):
        pub = TwitterPublisher("ck", "cs", "at", "ats")
        assert pub.is_configured()

    def test_is_configured_missing_key(self):
        pub = TwitterPublisher("ck", "", "at", "ats")
        assert not pub.is_configured()

    def test_platform_name(self):
        pub = TwitterPublisher("ck", "cs", "at", "ats")
        assert pub.platform_name == "twitter"

    @patch("tweepy.Client")
    def test_publish_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.create_tweet.return_value = MagicMock(
            data={"id": "12345"}
        )
        mock_client_cls.return_value = mock_client

        pub = TwitterPublisher("ck", "cs", "at", "ats")
        result = pub.publish("Test tweet")

        assert result.success
        assert "12345" in result.url
        mock_client.create_tweet.assert_called_once_with(text="Test tweet")

    @patch("tweepy.Client")
    def test_publish_truncates_to_280(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.create_tweet.return_value = MagicMock(data={"id": "1"})
        mock_client_cls.return_value = mock_client

        pub = TwitterPublisher("ck", "cs", "at", "ats")
        long_text = "a" * 300
        pub.publish(long_text)

        call_args = mock_client.create_tweet.call_args
        assert len(call_args[1]["text"]) == 280

    @patch("tweepy.Client")
    def test_publish_handles_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.create_tweet.side_effect = Exception("Rate limited")
        mock_client_cls.return_value = mock_client

        pub = TwitterPublisher("ck", "cs", "at", "ats")
        result = pub.publish("Test")

        assert not result.success
        assert "Rate limited" in result.message


class TestPublishReport:
    def test_all_success(self):
        report = PublishReport(results=[
            PublishResult("discord", True, "OK"),
            PublishResult("twitter", True, "OK"),
        ])
        assert report.all_success

    def test_not_all_success(self):
        report = PublishReport(results=[
            PublishResult("discord", True, "OK"),
            PublishResult("twitter", False, "Failed"),
        ])
        assert not report.all_success

    def test_summary(self):
        report = PublishReport(results=[
            PublishResult("discord", True, "Posted", url=""),
            PublishResult("twitter", False, "Rate limited"),
        ])
        summary = report.summary
        assert "[OK]" in summary
        assert "[FAILED]" in summary


class TestGetPublishers:
    def test_returns_discord_when_configured(self):
        from herald.config import HeraldSettings
        settings = HeraldSettings(discord_webhook_url="https://example.com/webhook")
        publishers = get_publishers(settings)
        assert any(p.platform_name == "discord" for p in publishers)

    def test_returns_twitter_when_configured(self):
        from herald.config import HeraldSettings
        settings = HeraldSettings(
            twitter_consumer_key="ck",
            twitter_consumer_secret="cs",
            twitter_access_token="at",
            twitter_access_token_secret="ats",
        )
        publishers = get_publishers(settings)
        assert any(p.platform_name == "twitter" for p in publishers)

    def test_returns_empty_when_nothing_configured(self):
        from herald.config import HeraldSettings
        settings = HeraldSettings()
        publishers = get_publishers(settings)
        assert publishers == []


class TestPublishContent:
    def test_dry_run(self):
        pub = DiscordPublisher("https://example.com/webhook")
        content = {"discord": "Test content", "twitter": "Tweet"}

        report = publish_content(content, [pub], dry_run=True)
        assert report.all_success
        assert "DRY RUN" in report.results[0].message

    def test_skips_unconfigured_publishers(self):
        pub = DiscordPublisher("")
        content = {"discord": "Test"}

        report = publish_content(content, [pub])
        assert not report.results[0].success
        assert "Not configured" in report.results[0].message

    def test_no_content_for_platform(self):
        pub = DiscordPublisher("https://example.com/webhook")
        content = {"twitter": "Tweet only"}

        report = publish_content(content, [pub])
        assert not report.results[0].success
        assert "No content" in report.results[0].message
