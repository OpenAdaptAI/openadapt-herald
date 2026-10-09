"""Post an approved file exactly as written.

This path never calls a language model, never truncates, and never rewrites
the text. It exists so an approval can bind to the exact bytes that go out.

Every attempt ends in one of three states:

- ``published``: X returned the new post's id. The ledger records it.
- ``not_sent``: nothing was posted. Either the request never left this
  machine, or X processed it and refused it (a 4xx answer).
- ``uncertain``: the request may have reached X and we don't know whether a
  post exists (timeout after sending, a 5xx answer, a reply without an id).

An ``uncertain`` result is never retried blindly. The next run reads the
account's own recent posts first. If the post is there, the ledger records it
as published and nothing is sent. If it isn't (and the attempt is older than
the settle time), the ledger records that check, and a new attempt needs
``retry=True``. A retry reads the recent posts once more before it sends.

A result tells you whether the post exists on X, even when the run itself
sent nothing. A dry run after an uncertain attempt therefore reports
``uncertain`` too.

The ledger is an append-only JSON Lines file keyed by the SHA-256 of the text.
A record with ``state: uncertain`` is written *before* each request is sent,
so a crash or a killed job also leaves an uncertain record behind.
"""

from __future__ import annotations

import enum
import hashlib
import html
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

LEDGER_SCHEMA = "herald.post-ledger/v1"

# X counts text by weight, not by Python characters. These values follow the
# published twitter-text v3 configuration: most Latin text weighs 1, other
# code points (for example CJK and emoji) weigh 2, and every link counts as 23
# no matter how long it is.
X_MAX_WEIGHTED_LENGTH = 280
X_URL_LENGTH = 23
_X_SCALE = 100
_X_DEFAULT_WEIGHT = 200
_X_LIGHT_RANGES = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))

# Explicit links, and bare domains that X may turn into links. The bare-domain
# pattern is deliberately generous, so it also matches dotted words that X
# leaves as plain text (for example a long config key). A bare-domain match
# therefore counts as 23 or as its own length, whichever is longer: the
# estimate can be too long, never too short.
_EXPLICIT_URL = r"https?://[^\s<>\"']+"
_BARE_DOMAIN = (
    r"(?<![\w@.\-/])"
    r"(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}"
    r"(?::\d{2,5})?(?:/[^\s<>\"']*)?"
)
URL_RE = re.compile(f"{_EXPLICIT_URL}|{_BARE_DOMAIN}", re.IGNORECASE)
_EXPLICIT_URL_RE = re.compile(_EXPLICIT_URL, re.IGNORECASE)
_TRAILING_PUNCTUATION = ".,;:!?)]}'\""

EXIT_CODES = {"published": 0, "not_sent": 3, "uncertain": 4}


class Outcome(str, enum.Enum):
    PUBLISHED = "published"
    NOT_SENT = "not_sent"
    UNCERTAIN = "uncertain"


@dataclass
class PostResult:
    outcome: Outcome
    platform: str
    content_sha256: str
    message: str
    post_id: str = ""
    url: str = ""
    weighted_length: int | None = None
    reconciled: bool = False

    @property
    def exit_code(self) -> int:
        return EXIT_CODES[self.outcome.value]

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "platform": self.platform,
            "content_sha256": self.content_sha256,
            "message": self.message,
            "post_id": self.post_id,
            "url": self.url,
            "weighted_length": self.weighted_length,
            "reconciled": self.reconciled,
        }


class VerbatimError(Exception):
    """Raised for input problems. Nothing was sent."""


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------


def read_post_file(path: Path) -> str:
    """Read the exact text to post.

    The file is decoded as UTF-8. Trailing newline characters are removed,
    because editors add them and X drops them. Nothing else changes.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise VerbatimError(f"cannot read {path}: {exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise VerbatimError(f"{path} is not valid UTF-8: {exc}") from exc
    text = text.rstrip("\r\n")
    if not text.strip():
        raise VerbatimError(f"{path} is empty")
    return text


def content_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def find_urls(text: str) -> list[str]:
    """Return the link-like spans X would count as links."""
    found = []
    for match in URL_RE.finditer(text):
        span = match.group(0).rstrip(_TRAILING_PUNCTUATION)
        if span:
            found.append(span)
    return found


def x_weighted_length(text: str) -> int:
    """Weighted length as X counts it, never shorter than X's count.

    A link written with http:// or https:// counts as 23. A bare domain counts
    as 23 or as its own weighted length, whichever is longer, because X may
    leave it as plain text.
    """
    normalized = unicodedata.normalize("NFC", text)
    total = 0
    position = 0
    for match in URL_RE.finditer(normalized):
        span = match.group(0).rstrip(_TRAILING_PUNCTUATION)
        if not span:
            continue
        start = match.start()
        total += _weigh(normalized[position:start])
        if _EXPLICIT_URL_RE.match(span):
            total += X_URL_LENGTH * _X_SCALE
        else:
            total += max(X_URL_LENGTH * _X_SCALE, _weigh(span))
        position = start + len(span)
    total += _weigh(normalized[position:])
    # Every weight is a multiple of the scale, so this division is exact.
    return total // _X_SCALE


def has_long_bare_domain(text: str) -> bool:
    """True if a link without http(s):// counts at its full length (over 23)."""
    normalized = unicodedata.normalize("NFC", text)
    for match in URL_RE.finditer(normalized):
        span = match.group(0).rstrip(_TRAILING_PUNCTUATION)
        if span and not _EXPLICIT_URL_RE.match(span):
            if _weigh(span) > X_URL_LENGTH * _X_SCALE:
                return True
    return False


def _weigh(segment: str) -> int:
    weight = 0
    for char in segment:
        code = ord(char)
        if any(low <= code <= high for low, high in _X_LIGHT_RANGES):
            weight += _X_SCALE
        else:
            weight += _X_DEFAULT_WEIGHT
    return weight


def normalize_for_match(text: str) -> str:
    """Make posted text and timeline text comparable.

    X returns links as t.co links and escapes some characters, so links are
    replaced by a marker, entities are decoded, and whitespace is collapsed.
    """
    value = html.unescape(text or "")
    value = unicodedata.normalize("NFC", value)
    value = URL_RE.sub("<link>", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


# --------------------------------------------------------------------------
# Ledger
# --------------------------------------------------------------------------


class Ledger:
    """Append-only JSON Lines record of every attempt, keyed by text hash."""

    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise VerbatimError(f"cannot read ledger {self.path}: {exc}") from exc
        for number, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise VerbatimError(
                    f"ledger {self.path} line {number} is not JSON; refusing to guess: {exc}"
                ) from exc
            if not isinstance(record, dict):
                raise VerbatimError(f"ledger {self.path} line {number} is not an object")
            records.append(record)
        return records

    def history(self, sha256: str, platform: str) -> list[dict[str, Any]]:
        return [
            r
            for r in self._read()
            if r.get("content_sha256") == sha256 and r.get("platform") == platform
        ]

    def current(self, sha256: str, platform: str) -> dict[str, Any] | None:
        history = self.history(sha256, platform)
        return history[-1] if history else None

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"schema": LEDGER_SCHEMA, **record}, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())


# --------------------------------------------------------------------------
# X account access
# --------------------------------------------------------------------------


class XAccount(Protocol):
    def create(self, text: str) -> str:
        """Create a post and return its id. Raise on any failure."""

    def recent_posts(self, limit: int) -> list[dict[str, Any]]:
        """Return the account's own recent posts as dicts with id, text, created_at."""


class TweepyXAccount:
    """The account behind the four OAuth 1.0a user credentials."""

    def __init__(
        self,
        consumer_key: str,
        consumer_secret: str,
        access_token: str,
        access_token_secret: str,
        timeout_seconds: float = 30.0,
    ):
        if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
            raise VerbatimError(
                "X credentials are missing. Set HERALD_TWITTER_CONSUMER_KEY, "
                "HERALD_TWITTER_CONSUMER_SECRET, HERALD_TWITTER_ACCESS_TOKEN and "
                "HERALD_TWITTER_ACCESS_TOKEN_SECRET."
            )
        import requests
        import tweepy

        class _TimeoutSession(requests.Session):
            def request(self, *args, **kwargs):  # type: ignore[override]
                kwargs.setdefault("timeout", timeout_seconds)
                return super().request(*args, **kwargs)

        self._client = tweepy.Client(
            consumer_key=consumer_key,
            consumer_secret=consumer_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
            wait_on_rate_limit=False,
        )
        # tweepy sends requests without a timeout; a hung request would hang
        # the publish job forever.
        self._client.session = _TimeoutSession()

    def create(self, text: str) -> str:
        response = self._client.create_tweet(text=text, user_auth=True)
        data = getattr(response, "data", None) or {}
        post_id = str(data.get("id", "")) if isinstance(data, dict) else ""
        if not post_id:
            raise MissingPostId("X accepted the request but returned no post id")
        return post_id

    def recent_posts(self, limit: int) -> list[dict[str, Any]]:
        me = self._client.get_me(user_auth=True)
        user = getattr(me, "data", None)
        user_id = getattr(user, "id", None)
        if user_id is None and isinstance(user, dict):
            user_id = user.get("id")
        if not user_id:
            raise VerbatimError("could not read the authenticated X account id")
        response = self._client.get_users_tweets(
            user_id,
            user_auth=True,
            max_results=max(5, min(limit, 100)),
            tweet_fields=["created_at"],
            exclude=["replies", "retweets"],
        )
        posts = []
        for tweet in getattr(response, "data", None) or []:
            created = getattr(tweet, "created_at", None)
            posts.append(
                {
                    "id": str(getattr(tweet, "id", "")),
                    "text": getattr(tweet, "text", "") or "",
                    "created_at": created.isoformat() if created else "",
                }
            )
        return posts


class MissingPostId(Exception):
    """X answered 2xx without an id. The post may exist."""


def classify_send_error(exc: BaseException) -> tuple[Outcome, str]:
    """Decide what a failed create call means for whether a post exists."""
    if isinstance(exc, MissingPostId):
        return Outcome.UNCERTAIN, str(exc)

    try:
        import requests
        from urllib3.exceptions import NewConnectionError
    except ImportError:  # pragma: no cover - dependencies are required
        requests = None  # type: ignore[assignment]
        NewConnectionError = ()  # type: ignore[assignment,misc]

    if requests is not None:
        if isinstance(exc, requests.exceptions.ConnectTimeout):
            return Outcome.NOT_SENT, f"could not connect to X (timeout): {exc}"
        if isinstance(exc, requests.exceptions.ConnectionError) and not isinstance(
            exc, requests.exceptions.SSLError
        ):
            reason = exc.args[0] if exc.args else None
            inner = getattr(reason, "reason", reason)
            if isinstance(inner, NewConnectionError):
                return Outcome.NOT_SENT, f"could not connect to X: {exc}"
            return Outcome.UNCERTAIN, f"connection failed after sending may have started: {exc}"
        if isinstance(exc, requests.exceptions.Timeout):
            return Outcome.UNCERTAIN, f"X did not answer in time: {exc}"

    try:
        import tweepy
    except ImportError:  # pragma: no cover
        tweepy = None  # type: ignore[assignment]

    if tweepy is not None and isinstance(exc, tweepy.errors.HTTPException):
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None) or getattr(response, "status", None)
        messages = " ".join(str(m) for m in getattr(exc, "api_messages", []) or [])
        if status is not None and int(status) >= 500:
            return Outcome.UNCERTAIN, f"X answered {status}; the post may exist: {exc}"
        if "duplicate" in messages.lower() or "duplicate" in str(exc).lower():
            return (
                Outcome.UNCERTAIN,
                "X says this text is a duplicate, so a matching post probably exists: "
                f"{exc}",
            )
        if status is not None and 400 <= int(status) < 500:
            return Outcome.NOT_SENT, f"X refused the post ({status}): {exc}"
        return Outcome.UNCERTAIN, f"X answered {status}: {exc}"

    return Outcome.UNCERTAIN, f"{type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------
# Poster
# --------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class VerbatimXPoster:
    """Post one approved text to X with idempotency and reconciliation."""

    platform = "x"

    def __init__(
        self,
        account_factory: Callable[[], XAccount],
        ledger: Ledger | None,
        *,
        settle_seconds: int = 120,
        timeline_limit: int = 20,
        clock: Callable[[], datetime] = _utc_now,
    ):
        self._account_factory = account_factory
        self._account: XAccount | None = None
        self.ledger = ledger
        self.settle_seconds = settle_seconds
        self.timeline_limit = timeline_limit
        self.clock = clock

    # -- helpers -----------------------------------------------------------

    def _account_or_raise(self) -> XAccount:
        if self._account is None:
            self._account = self._account_factory()
        return self._account

    def _result(self, outcome: Outcome, sha: str, message: str, **extra: Any) -> PostResult:
        return PostResult(outcome=outcome, platform=self.platform, content_sha256=sha,
                          message=message, **extra)

    def _record(self, sha: str, state: Outcome, detail: str, **extra: Any) -> None:
        assert self.ledger is not None
        self.ledger.append(
            {
                "content_sha256": sha,
                "platform": self.platform,
                "state": state.value,
                "at": self.clock().isoformat(),
                "detail": detail,
                **extra,
            }
        )

    def _find_on_timeline(self, text: str) -> dict[str, Any] | None:
        """Return a recent post with the same text, whenever it was posted.

        Posting is idempotent by text, so any matching post counts. This also
        covers X's duplicate-content refusal, where the match is an older post.
        """
        wanted = normalize_for_match(text)
        posts = self._account_or_raise().recent_posts(self.timeline_limit)
        for post in posts:
            if normalize_for_match(post.get("text", "")) == wanted:
                return post
        return None

    # -- main entry --------------------------------------------------------

    def post(
        self,
        text: str,
        *,
        expect_sha256: str = "",
        dry_run: bool = False,
        retry: bool = False,
        precheck_timeline: bool = False,
    ) -> PostResult:
        sha = content_sha256(text)
        length = x_weighted_length(text)
        expected = expect_sha256.strip().lower()

        if expected and expected != sha:
            return self._result(
                Outcome.NOT_SENT, sha,
                f"text hash {sha} does not match the approved hash {expected}. Either "
                "the text changed after approval, or the approved hash was taken over "
                "different bytes (Herald hashes the text without trailing newlines; "
                "--dry-run --json prints the hash it uses).",
                weighted_length=length,
            )
        if length > X_MAX_WEIGHTED_LENGTH:
            message = (
                f"text is {length} weighted characters; X allows {X_MAX_WEIGHTED_LENGTH}. "
                "Shorten the approved text. Herald never truncates."
            )
            if has_long_bare_domain(text):
                message += (" A link without https:// counts at its full length when "
                            "that is over 23; add https:// so it counts as 23.")
            return self._result(Outcome.NOT_SENT, sha, message, weighted_length=length)

        try:
            current = self.ledger.current(sha, self.platform) if self.ledger else None
        except VerbatimError as exc:
            return self._result(Outcome.NOT_SENT, sha, str(exc), weighted_length=length)

        state = (current or {}).get("state")
        needs_retry_flag = (
            state == Outcome.NOT_SENT.value and bool((current or {}).get("reconciled"))
        )

        if state == Outcome.PUBLISHED.value:
            return self._result(
                Outcome.PUBLISHED, sha,
                "already published; not posting again",
                post_id=current.get("post_id", ""), url=current.get("url", ""),
                weighted_length=length,
            )

        if dry_run:
            if state == Outcome.UNCERTAIN.value:
                # The result describes whether a post exists, not what this run
                # did. An earlier attempt may have posted, so this stays uncertain.
                return self._result(
                    Outcome.UNCERTAIN, sha,
                    "dry run: the last attempt is uncertain, so a post may already exist. "
                    "A live run reads the account's recent posts before it sends anything.",
                    weighted_length=length,
                )
            if needs_retry_flag and not retry:
                message = ("dry run: an earlier attempt was uncertain and a check found no "
                           "matching post. A live run needs --retry to post it.")
            else:
                message = f"dry run: would post {length} weighted characters"
            return self._result(Outcome.NOT_SENT, sha, message, weighted_length=length,
                                reconciled=needs_retry_flag)

        if self.ledger is None:
            return self._result(
                Outcome.NOT_SENT, sha,
                "a ledger path is required for a live post (--ledger or HERALD_POST_LEDGER)",
                weighted_length=length,
            )

        if needs_retry_flag and not retry:
            return self._result(
                Outcome.NOT_SENT, sha,
                "an earlier attempt was uncertain and a check found no matching post. "
                "Run again with --retry to post it.",
                weighted_length=length, reconciled=True,
            )

        try:
            self._account_or_raise()
        except Exception as exc:  # noqa: BLE001 - nothing was sent
            return self._result(Outcome.NOT_SENT, sha, f"cannot open X account: {exc}",
                                weighted_length=length)

        if state == Outcome.UNCERTAIN.value:
            reconciled = self._reconcile(text, sha, current, retry, length)
            if reconciled is not None:
                return reconciled
        elif precheck_timeline or needs_retry_flag:
            # A --retry after an uncertain attempt always reads the timeline
            # again first: the earlier post may have appeared since the check.
            try:
                found = self._find_on_timeline(text)
            except Exception as exc:  # noqa: BLE001
                return self._result(
                    Outcome.NOT_SENT, sha,
                    f"could not read recent posts before posting, so this run sent "
                    f"nothing: {exc}",
                    weighted_length=length, reconciled=needs_retry_flag,
                )
            if found:
                return self._found(sha, found, "found on timeline before posting",
                                   "a matching post already exists; not posting again",
                                   length)

        return self._send(text, sha, length)

    def _reconcile(
        self, text: str, sha: str, current: dict[str, Any], retry: bool, length: int
    ) -> PostResult | None:
        """Handle a previous uncertain attempt. Return a result, or None to send."""
        attempted_at = _parse_time(current.get("at", "")) or self.clock()
        age = (self.clock() - attempted_at).total_seconds()
        try:
            found = self._find_on_timeline(text)
        except Exception as exc:  # noqa: BLE001
            return self._result(
                Outcome.UNCERTAIN, sha,
                f"the last attempt is uncertain and recent posts could not be read: {exc}. "
                "This run sent nothing; the earlier attempt may still have posted.",
                weighted_length=length,
            )
        if found:
            return self._found(sha, found, "reconciled: found on timeline",
                               "found a matching post on the account after an uncertain "
                               "attempt; recorded it as published and sent nothing",
                               length)
        if age < self.settle_seconds:
            return self._result(
                Outcome.UNCERTAIN, sha,
                f"the last attempt was {int(age)} seconds ago and no matching post is "
                f"visible yet. Wait at least {self.settle_seconds} seconds after the "
                "attempt, then run again. This run sent nothing; the earlier attempt may "
                "still have posted.",
                weighted_length=length,
            )
        try:
            self._record(
                sha, Outcome.NOT_SENT,
                f"reconciled: no matching post in the last {self.timeline_limit} posts",
                reconciled=True,
            )
        except OSError as exc:
            # The ledger still says uncertain, so the next run checks again.
            return self._result(
                Outcome.UNCERTAIN, sha,
                f"found no matching post, but could not record that check ({exc}). "
                "This run sent nothing; fix the ledger and run again.",
                weighted_length=length,
            )
        if not retry:
            return self._result(
                Outcome.NOT_SENT, sha,
                "checked recent posts and found no matching post. "
                "Run again with --retry to post it.",
                weighted_length=length, reconciled=True,
            )
        return None

    def _found(
        self, sha: str, found: dict[str, Any], detail: str, message: str, length: int
    ) -> PostResult:
        """Record and report a matching post found on the account's timeline."""
        url = f"https://x.com/i/status/{found['id']}"
        try:
            self._record(sha, Outcome.PUBLISHED, detail, post_id=found["id"], url=url,
                         reconciled=True)
        except OSError as exc:
            message += (f"; the ledger write failed ({exc}), so the ledger doesn't "
                        "show this post yet")
        return self._result(Outcome.PUBLISHED, sha, message, post_id=found["id"],
                            url=url, weighted_length=length, reconciled=True)

    def _send(self, text: str, sha: str, length: int) -> PostResult:
        # Write-ahead: if this process dies mid-request, the ledger already
        # says "uncertain" and the next run reconciles before sending.
        try:
            self._record(sha, Outcome.UNCERTAIN, "attempt started")
        except OSError as exc:
            return self._result(Outcome.NOT_SENT, sha,
                                f"cannot write the ledger, so nothing was sent: {exc}",
                                weighted_length=length)
        try:
            post_id = self._account_or_raise().create(text)
        except Exception as exc:  # noqa: BLE001 - classified below
            outcome, message = classify_send_error(exc)
            try:
                self._record(sha, outcome, message)
            except OSError as ledger_exc:
                # The write-ahead record still says "uncertain", which is the
                # safe reading: the next run reconciles before sending.
                message += f" (ledger write failed: {ledger_exc})"
            return self._result(outcome, sha, message, weighted_length=length)
        url = f"https://x.com/i/status/{post_id}"
        message = "posted to X"
        try:
            self._record(sha, Outcome.PUBLISHED, "created", post_id=post_id, url=url)
        except OSError as ledger_exc:
            message += (f"; the ledger write failed ({ledger_exc}), so the next run will "
                        "find this post on the timeline before it sends anything")
        return self._result(Outcome.PUBLISHED, sha, message, post_id=post_id,
                            url=url, weighted_length=length)


LINKEDIN_MANUAL_MESSAGE = (
    "LinkedIn posts stay manual. LinkedIn's API terms do not allow automated posting, "
    "so Herald does not post to LinkedIn from an approved file. Copy the text and post "
    "it from the LinkedIn page yourself."
)
