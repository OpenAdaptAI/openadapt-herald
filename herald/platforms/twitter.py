"""Twitter/X publisher using tweepy."""

from __future__ import annotations

from herald.platforms.base import Publisher, PublishResult, shorten
from herald.verbatim import X_MAX_WEIGHTED_LENGTH, x_weighted_length


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
        """Post a tweet, shortened at a word to X's 280 weighted characters if needed."""
        import tweepy

        text = shorten(content, X_MAX_WEIGHTED_LENGTH, measure=x_weighted_length)

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
