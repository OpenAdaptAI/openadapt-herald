"""Twitter/X publisher using tweepy."""

from __future__ import annotations

from herald.platforms.base import Publisher, PublishResult


class TwitterPublisher(Publisher):
    """Post tweets to Twitter/X via API v2."""

    def __init__(
        self,
        consumer_key: str,
        consumer_secret: str,
        access_token: str,
        access_token_secret: str,
    ):
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret
        self._access_token = access_token
        self._access_token_secret = access_token_secret

    @property
    def platform_name(self) -> str:
        return "twitter"

    def is_configured(self) -> bool:
        return all([
            self._consumer_key,
            self._consumer_secret,
            self._access_token,
            self._access_token_secret,
        ])

    def publish(self, content: str, **kwargs) -> PublishResult:
        """Post a tweet. Content is truncated to 280 chars if needed."""
        import tweepy

        text = content[:280] if len(content) > 280 else content

        try:
            client = tweepy.Client(
                consumer_key=self._consumer_key,
                consumer_secret=self._consumer_secret,
                access_token=self._access_token,
                access_token_secret=self._access_token_secret,
            )
            response = client.create_tweet(text=text)
            tweet_id = response.data.get("id", "") if response.data else ""
            url = f"https://x.com/i/status/{tweet_id}" if tweet_id else ""
            return PublishResult(
                platform="twitter",
                success=True,
                message="Posted to Twitter/X",
                url=url,
            )
        except Exception as e:
            return PublishResult(
                platform="twitter",
                success=False,
                message=f"Twitter error: {e}",
            )
