"""LinkedIn publisher using the LinkedIn API v2."""

from __future__ import annotations

from herald.platforms.base import Publisher, PublishResult


class LinkedInPublisher(Publisher):
    """Post articles to LinkedIn via the UGC Posts API."""

    # LinkedIn text posts have a 3000-character limit
    MAX_CONTENT_LENGTH = 3000

    def __init__(self, access_token: str):
        self._access_token = access_token

    @property
    def platform_name(self) -> str:
        return "linkedin"

    def is_configured(self) -> bool:
        return bool(self._access_token)

    def _get_user_urn(self) -> str:
        """Fetch the authenticated user's URN (sub) from the LinkedIn userinfo endpoint."""
        import requests

        response = requests.get(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {self._access_token}"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        sub = data.get("sub", "")
        if not sub:
            raise ValueError("LinkedIn userinfo response missing 'sub' field")
        return f"urn:li:person:{sub}"

    def publish(self, content: str, **kwargs) -> PublishResult:
        """Post content to LinkedIn as a text post.

        kwargs:
            visibility: "PUBLIC" (default) or "CONNECTIONS"
        """
        import requests

        visibility = kwargs.get("visibility", "PUBLIC")
        text = (
            content[: self.MAX_CONTENT_LENGTH]
            if len(content) > self.MAX_CONTENT_LENGTH
            else content
        )

        try:
            author_urn = self._get_user_urn()

            payload = {
                "author": author_urn,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": text},
                        "shareMediaCategory": "NONE",
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": visibility,
                },
            }

            response = requests.post(
                "https://api.linkedin.com/v2/ugcPosts",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "X-Restli-Protocol-Version": "2.0.0",
                },
                timeout=30,
            )

            if response.status_code == 201:
                post_id = response.json().get("id", "")
                return PublishResult(
                    platform="linkedin",
                    success=True,
                    message="Posted to LinkedIn",
                    url=f"https://www.linkedin.com/feed/update/{post_id}" if post_id else "",
                )

            return PublishResult(
                platform="linkedin",
                success=False,
                message=f"LinkedIn returned status {response.status_code}: {response.text}",
            )
        except Exception as e:
            return PublishResult(
                platform="linkedin",
                success=False,
                message=f"LinkedIn error: {e}",
            )
