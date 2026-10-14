"""Tests for the verbatim post path. No network; the X account is faked."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
import tweepy
from typer.testing import CliRunner
from urllib3.exceptions import NewConnectionError

from herald.cli import app
from herald.verbatim import (
    X_MAX_WEIGHTED_LENGTH,
    Ledger,
    MissingPostId,
    Outcome,
    VerbatimError,
    VerbatimXPoster,
    classify_send_error,
    content_sha256,
    normalize_for_match,
    read_post_file,
    x_weighted_length,
)

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)
TEXT = (
    "New post: how OpenAdapt checks that a save went through.\n\n"
    "https://blog.openadapt.ai/posts/example/?utm_source=x&utm_medium=social&utm_campaign=t"
)


class FakeAccount:
    def __init__(self, *, create_result=None, create_error=None, timeline=None,
                 timeline_error=None):
        self.create_result = create_result if create_result is not None else "1001"
        self.create_error = create_error
        self.timeline = timeline or []
        self.timeline_error = timeline_error
        self.created: list[str] = []
        self.timeline_reads = 0

    def create(self, text: str) -> str:
        self.created.append(text)
        if self.create_error is not None:
            raise self.create_error
        return self.create_result

    def recent_posts(self, limit: int):
        self.timeline_reads += 1
        if self.timeline_error is not None:
            raise self.timeline_error
        return list(self.timeline)


def make_poster(tmp_path: Path, account: FakeAccount, *, now=NOW, settle=120):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    poster = VerbatimXPoster(lambda: account, ledger, settle_seconds=settle,
                             clock=lambda: now)
    return poster, ledger


def http_error(cls, status: int, message: str = "error"):
    response = MagicMock()
    response.status_code = status
    response.reason = message
    response.json.return_value = {"errors": [{"message": message}]}
    return cls(response)


# ----------------------------------------------------------------- length


class TestWeightedLength:
    def test_ascii_counts_one_each(self):
        assert x_weighted_length("hello") == 5

    def test_every_link_counts_23(self):
        long_link = "https://blog.openadapt.ai/posts/" + "a" * 80
        assert x_weighted_length(f"Read {long_link}") == len("Read ") + 23

    def test_bare_domain_counts_as_link(self):
        assert x_weighted_length("see openadapt.ai") == len("see ") + 23

    def test_trailing_period_is_not_part_of_link(self):
        assert x_weighted_length("see https://openadapt.ai.") == len("see ") + 23 + 1

    def test_ellipsis_after_a_link_is_not_part_of_it(self):
        # X ends a link before U+2026 and counts the ellipsis as 2. `herald
        # publish` adds one when it shortens a draft that ends in a link.
        assert x_weighted_length("see https://openadapt.ai/x…") == len("see ") + 23 + 2
        assert x_weighted_length("see openadapt.ai/x…") == len("see ") + 23 + 2

    def test_cjk_counts_two(self):
        assert x_weighted_length("日本") == 4

    def test_long_dotted_word_never_counts_short(self):
        # X may leave this as plain text, so it must not count as only 23.
        word = "openadapt.runtime.verification.settings.timeout"
        assert x_weighted_length(f"key {word}") == len("key ") + len(word)

    def test_long_explicit_link_still_counts_23(self):
        link = "https://openadapt.runtime.verification.settings.example.com/x"
        assert x_weighted_length(link) == 23

    def test_overlength_from_bare_domain_explains_https(self, tmp_path):
        account = FakeAccount()
        poster, _ = make_poster(tmp_path, account)
        text = "a" * 250 + " openadapt.ai/posts/a-long-article-slug"
        result = poster.post(text)
        assert result.outcome is Outcome.NOT_SENT
        assert "https://" in result.message
        assert account.created == []

    def test_exactly_280_is_allowed(self, tmp_path):
        account = FakeAccount()
        poster, _ = make_poster(tmp_path, account)
        result = poster.post("a" * X_MAX_WEIGHTED_LENGTH)
        assert result.outcome is Outcome.PUBLISHED


# ----------------------------------------------------------------- input


class TestReadFile:
    def test_strips_only_trailing_newlines(self, tmp_path):
        path = tmp_path / "post.txt"
        path.write_text("  line one\nline two  \n\n", encoding="utf-8")
        assert read_post_file(path) == "  line one\nline two  "

    def test_empty_file_is_refused(self, tmp_path):
        path = tmp_path / "post.txt"
        path.write_text("\n", encoding="utf-8")
        with pytest.raises(VerbatimError):
            read_post_file(path)


# ----------------------------------------------------------------- refusals


class TestRefusals:
    def test_overlength_is_not_sent_and_never_truncated(self, tmp_path):
        account = FakeAccount()
        poster, ledger = make_poster(tmp_path, account)
        result = poster.post("b" * 281)
        assert result.outcome is Outcome.NOT_SENT
        assert "never truncates" in result.message
        assert account.created == []
        assert not ledger.path.exists()

    def test_hash_mismatch_is_not_sent(self, tmp_path):
        account = FakeAccount()
        poster, _ = make_poster(tmp_path, account)
        result = poster.post(TEXT, expect_sha256="0" * 64)
        assert result.outcome is Outcome.NOT_SENT
        assert "changed after approval" in result.message
        assert account.created == []

    def test_matching_hash_posts(self, tmp_path):
        account = FakeAccount()
        poster, _ = make_poster(tmp_path, account)
        result = poster.post(TEXT, expect_sha256=content_sha256(TEXT))
        assert result.outcome is Outcome.PUBLISHED
        assert account.created == [TEXT]

    def test_matching_hash_tolerates_case_and_whitespace(self, tmp_path):
        account = FakeAccount()
        poster, _ = make_poster(tmp_path, account)
        result = poster.post(TEXT, expect_sha256=f" {content_sha256(TEXT).upper()}\n")
        assert result.outcome is Outcome.PUBLISHED

    def test_dry_run_after_uncertain_attempt_stays_uncertain(self, tmp_path):
        ledger = Ledger(tmp_path / "l.jsonl")
        ledger.append({"content_sha256": content_sha256(TEXT), "platform": "x",
                       "state": "uncertain", "at": NOW.isoformat(),
                       "detail": "attempt started"})
        factory = MagicMock(side_effect=AssertionError("must not build a client"))
        poster = VerbatimXPoster(factory, ledger, clock=lambda: NOW)
        result = poster.post(TEXT, dry_run=True)
        assert result.outcome is Outcome.UNCERTAIN
        assert result.exit_code == 4
        factory.assert_not_called()

    def test_dry_run_after_reconciled_check_mentions_retry(self, tmp_path):
        ledger = Ledger(tmp_path / "l.jsonl")
        ledger.append({"content_sha256": content_sha256(TEXT), "platform": "x",
                       "state": "not_sent", "at": NOW.isoformat(),
                       "detail": "reconciled", "reconciled": True})
        poster = VerbatimXPoster(MagicMock(), ledger, clock=lambda: NOW)
        result = poster.post(TEXT, dry_run=True)
        assert result.outcome is Outcome.NOT_SENT
        assert "--retry" in result.message
        assert result.reconciled

    def test_dry_run_never_opens_the_account(self, tmp_path):
        factory = MagicMock(side_effect=AssertionError("must not build a client"))
        poster = VerbatimXPoster(factory, Ledger(tmp_path / "l.jsonl"), clock=lambda: NOW)
        result = poster.post(TEXT, dry_run=True)
        assert result.outcome is Outcome.NOT_SENT
        assert result.message.startswith("dry run")
        factory.assert_not_called()

    def test_live_post_requires_ledger(self, tmp_path):
        account = FakeAccount()
        poster = VerbatimXPoster(lambda: account, None, clock=lambda: NOW)
        result = poster.post(TEXT)
        assert result.outcome is Outcome.NOT_SENT
        assert "ledger" in result.message
        assert account.created == []

    def test_missing_credentials_is_not_sent(self, tmp_path):
        def factory():
            raise VerbatimError("X credentials are missing")

        poster = VerbatimXPoster(factory, Ledger(tmp_path / "l.jsonl"), clock=lambda: NOW)
        result = poster.post(TEXT)
        assert result.outcome is Outcome.NOT_SENT
        assert "credentials" in result.message

    def test_corrupt_ledger_refuses_and_stays_uncertain(self, tmp_path):
        # Without a readable ledger an earlier post can't be ruled out.
        account = FakeAccount()
        poster, ledger = make_poster(tmp_path, account)
        ledger.path.write_text("{not json\n", encoding="utf-8")
        result = poster.post(TEXT)
        assert result.outcome is Outcome.UNCERTAIN
        assert result.exit_code == 4
        assert "sent nothing" in result.message
        assert account.created == []
        assert account.timeline_reads == 0

    def test_partial_ledger_line_after_a_post_stays_uncertain(self, tmp_path):
        # A full disk can cut the "published" record short right after X
        # accepted the post. The next run must not report not_sent.
        account = FakeAccount(create_result="321")
        poster, ledger = make_poster(tmp_path, account)
        assert poster.post(TEXT).outcome is Outcome.PUBLISHED
        lines = ledger.path.read_text(encoding="utf-8").splitlines()
        ledger.path.write_text(lines[0] + "\n" + lines[1][:20], encoding="utf-8")
        again = poster.post(TEXT)
        assert again.outcome is Outcome.UNCERTAIN
        assert account.created == [TEXT]


# ----------------------------------------------------------------- publish


class TestPublishAndIdempotency:
    def test_publish_records_write_ahead_then_published(self, tmp_path):
        account = FakeAccount(create_result="555")
        poster, ledger = make_poster(tmp_path, account)
        result = poster.post(TEXT)
        assert result.outcome is Outcome.PUBLISHED
        assert result.url == "https://x.com/i/status/555"
        states = [r["state"] for r in ledger.history(content_sha256(TEXT), "x")]
        assert states == ["uncertain", "published"]

    def test_second_run_does_not_post_again(self, tmp_path):
        account = FakeAccount()
        poster, _ = make_poster(tmp_path, account)
        poster.post(TEXT)
        again = poster.post(TEXT)
        assert again.outcome is Outcome.PUBLISHED
        assert "already published" in again.message
        assert account.created == [TEXT]

    def test_precheck_finds_existing_post_and_skips(self, tmp_path):
        posted = TEXT.replace(
            "https://blog.openadapt.ai/posts/example/?utm_source=x&utm_medium=social&utm_campaign=t",
            "https://t.co/abc123",
        )
        account = FakeAccount(timeline=[{"id": "77", "text": posted, "created_at": ""}])
        poster, ledger = make_poster(tmp_path, account)
        result = poster.post(TEXT, precheck_timeline=True)
        assert result.outcome is Outcome.PUBLISHED
        assert result.reconciled
        assert account.created == []

    def test_precheck_read_failure_sends_nothing(self, tmp_path):
        account = FakeAccount(timeline_error=RuntimeError("read failed"))
        poster, _ = make_poster(tmp_path, account)
        result = poster.post(TEXT, precheck_timeline=True)
        assert result.outcome is Outcome.NOT_SENT
        assert account.created == []


# ----------------------------------------------------------------- outcomes


class TestClassification:
    def test_server_error_is_uncertain(self):
        exc = http_error(tweepy.errors.TwitterServerError, 503)
        assert classify_send_error(exc)[0] is Outcome.UNCERTAIN

    def test_bad_request_is_not_sent(self):
        exc = http_error(tweepy.errors.BadRequest, 400)
        assert classify_send_error(exc)[0] is Outcome.NOT_SENT

    def test_rate_limit_is_not_sent(self):
        exc = http_error(tweepy.errors.TooManyRequests, 429)
        assert classify_send_error(exc)[0] is Outcome.NOT_SENT

    def test_duplicate_content_is_uncertain(self):
        exc = http_error(tweepy.errors.Forbidden, 403,
                         "You are not allowed to create a Tweet with duplicate content.")
        assert classify_send_error(exc)[0] is Outcome.UNCERTAIN

    def test_read_timeout_is_uncertain(self):
        assert classify_send_error(requests.exceptions.ReadTimeout("slow"))[0] is (
            Outcome.UNCERTAIN
        )

    def test_connect_timeout_is_not_sent(self):
        assert classify_send_error(requests.exceptions.ConnectTimeout("no"))[0] is (
            Outcome.NOT_SENT
        )

    def test_refused_connection_is_not_sent(self):
        inner = NewConnectionError(None, "refused")
        exc = requests.exceptions.ConnectionError(MagicMock(reason=inner))
        assert classify_send_error(exc)[0] is Outcome.NOT_SENT

    def test_reset_connection_is_uncertain(self):
        exc = requests.exceptions.ConnectionError("Connection aborted")
        assert classify_send_error(exc)[0] is Outcome.UNCERTAIN

    def test_missing_id_is_uncertain(self):
        assert classify_send_error(MissingPostId("no id"))[0] is Outcome.UNCERTAIN

    def test_unknown_error_is_uncertain(self):
        assert classify_send_error(ValueError("odd"))[0] is Outcome.UNCERTAIN


class TestUncertainNeverRetriesBlindly:
    def first_attempt_uncertain(self, tmp_path):
        account = FakeAccount(create_error=http_error(tweepy.errors.TwitterServerError, 502))
        poster, ledger = make_poster(tmp_path, account)
        result = poster.post(TEXT)
        assert result.outcome is Outcome.UNCERTAIN
        return ledger

    def test_reconcile_finds_post_and_records_published(self, tmp_path):
        ledger = self.first_attempt_uncertain(tmp_path)
        later = NOW + timedelta(minutes=5)
        account = FakeAccount(timeline=[
            {"id": "900", "text": TEXT, "created_at": NOW.isoformat()},
        ])
        poster = VerbatimXPoster(lambda: account, ledger, clock=lambda: later)
        result = poster.post(TEXT)
        assert result.outcome is Outcome.PUBLISHED
        assert result.post_id == "900"
        assert account.created == []
        assert account.timeline_reads == 1

    def test_reconcile_accepts_an_older_matching_post(self, tmp_path):
        # X refuses duplicate text, so the match can predate the attempt.
        ledger = self.first_attempt_uncertain(tmp_path)
        later = NOW + timedelta(minutes=5)
        account = FakeAccount(timeline=[
            {"id": "800", "text": TEXT, "created_at": (NOW - timedelta(days=2)).isoformat()},
        ])
        poster = VerbatimXPoster(lambda: account, ledger, clock=lambda: later)
        result = poster.post(TEXT, retry=True)
        assert result.outcome is Outcome.PUBLISHED
        assert result.post_id == "800"
        assert account.created == []

    def test_too_soon_stays_uncertain(self, tmp_path):
        ledger = self.first_attempt_uncertain(tmp_path)
        account = FakeAccount(timeline=[])
        poster = VerbatimXPoster(lambda: account, ledger, settle_seconds=120,
                                 clock=lambda: NOW + timedelta(seconds=30))
        result = poster.post(TEXT, retry=True)
        assert result.outcome is Outcome.UNCERTAIN
        assert account.created == []
        # Never imply that nothing was posted while the state is uncertain.
        assert "Nothing was sent" not in result.message
        assert "may still have posted" in result.message

    def test_absent_after_settle_needs_retry_flag(self, tmp_path):
        ledger = self.first_attempt_uncertain(tmp_path)
        later = NOW + timedelta(minutes=10)
        account = FakeAccount(timeline=[{"id": "1", "text": "something else",
                                         "created_at": later.isoformat()}])
        poster = VerbatimXPoster(lambda: account, ledger, clock=lambda: later)
        result = poster.post(TEXT)
        assert result.outcome is Outcome.NOT_SENT
        assert "--retry" in result.message
        assert account.created == []

        # A plain re-run still refuses; the flag is required.
        again = poster.post(TEXT)
        assert again.outcome is Outcome.NOT_SENT
        assert account.created == []

        retried = poster.post(TEXT, retry=True)
        assert retried.outcome is Outcome.PUBLISHED
        assert account.created == [TEXT]

    def test_retry_reads_timeline_again_before_sending(self, tmp_path):
        ledger = self.first_attempt_uncertain(tmp_path)
        later = NOW + timedelta(minutes=10)
        empty = FakeAccount(timeline=[])
        poster = VerbatimXPoster(lambda: empty, ledger, clock=lambda: later)
        assert poster.post(TEXT).outcome is Outcome.NOT_SENT

        # The slow first attempt shows up before the person runs --retry.
        late = FakeAccount(timeline=[{"id": "901", "text": TEXT,
                                      "created_at": NOW.isoformat()}])
        poster = VerbatimXPoster(lambda: late, ledger,
                                 clock=lambda: later + timedelta(hours=1))
        result = poster.post(TEXT, retry=True)
        assert result.outcome is Outcome.PUBLISHED
        assert result.post_id == "901"
        assert late.timeline_reads == 1
        assert late.created == []

    def test_retry_with_unreadable_timeline_sends_nothing(self, tmp_path):
        ledger = self.first_attempt_uncertain(tmp_path)
        later = NOW + timedelta(minutes=10)
        poster = VerbatimXPoster(lambda: FakeAccount(), ledger, clock=lambda: later)
        assert poster.post(TEXT).outcome is Outcome.NOT_SENT

        broken = FakeAccount(timeline_error=RuntimeError("503"))
        poster = VerbatimXPoster(lambda: broken, ledger, clock=lambda: later)
        result = poster.post(TEXT, retry=True)
        assert result.outcome is Outcome.NOT_SENT
        assert broken.created == []

    def test_unwritable_ledger_during_check_stays_uncertain(self, tmp_path):
        ledger = self.first_attempt_uncertain(tmp_path)
        later = NOW + timedelta(minutes=10)
        account = FakeAccount(timeline=[])
        poster = VerbatimXPoster(lambda: account, ledger, clock=lambda: later)
        with patch.object(Ledger, "append", side_effect=OSError("disk full")):
            result = poster.post(TEXT, retry=True)
        assert result.outcome is Outcome.UNCERTAIN
        assert account.created == []

    def test_account_open_failure_keeps_uncertain(self, tmp_path):
        # Expired or missing credentials on the next run must not turn an
        # uncertain attempt into not_sent.
        ledger = self.first_attempt_uncertain(tmp_path)

        def factory():
            raise VerbatimError("X credentials are missing")

        poster = VerbatimXPoster(factory, ledger, clock=lambda: NOW + timedelta(minutes=10))
        result = poster.post(TEXT, retry=True)
        assert result.outcome is Outcome.UNCERTAIN
        assert result.exit_code == 4
        assert "may still have posted" in result.message
        assert ledger.current(content_sha256(TEXT), "x")["state"] == "uncertain"

    def test_timeline_read_failure_keeps_uncertain(self, tmp_path):
        ledger = self.first_attempt_uncertain(tmp_path)
        account = FakeAccount(timeline_error=RuntimeError("401"))
        poster = VerbatimXPoster(lambda: account, ledger,
                                 clock=lambda: NOW + timedelta(minutes=10))
        result = poster.post(TEXT, retry=True)
        assert result.outcome is Outcome.UNCERTAIN
        assert account.created == []

    def test_crash_mid_request_leaves_uncertain(self, tmp_path):
        class Crash(BaseException):
            pass

        account = FakeAccount(create_error=Crash())
        poster, ledger = make_poster(tmp_path, account)
        with pytest.raises(Crash):
            poster.post(TEXT)
        assert ledger.current(content_sha256(TEXT), "x")["state"] == "uncertain"


def test_normalize_matches_tco_and_entities():
    assert normalize_for_match("a &amp; b https://t.co/x") == normalize_for_match(
        "a & b https://openadapt.ai/long/path"
    )


def test_verbatim_module_does_not_load_the_composer():
    sys.modules.pop("herald.composer", None)
    import importlib

    import herald.verbatim as verbatim

    importlib.reload(verbatim)
    assert "herald.composer" not in sys.modules


# ----------------------------------------------------------------- CLI


runner = CliRunner()


class TestPostCommand:
    def write(self, tmp_path, text=TEXT):
        path = tmp_path / "post.txt"
        path.write_text(text + "\n", encoding="utf-8")
        return path

    def test_linkedin_is_manual(self, tmp_path):
        result = runner.invoke(app, ["post", "--file", str(self.write(tmp_path)),
                                     "--platform", "linkedin"])
        assert result.exit_code == 3
        assert "manual" in result.output

    def test_dry_run_exit_code_not_sent(self, tmp_path):
        result = runner.invoke(app, ["post", "--file", str(self.write(tmp_path)),
                                     "--dry-run", "--json"])
        assert result.exit_code == 3
        payload = json.loads(result.output)
        assert payload["outcome"] == "not_sent"
        assert payload["content_sha256"] == content_sha256(TEXT)

    def test_overlength_exit_code(self, tmp_path):
        result = runner.invoke(app, ["post", "--file", str(self.write(tmp_path, "c" * 300)),
                                     "--dry-run"])
        assert result.exit_code == 3
        assert "never truncates" in result.output

    @patch("herald.verbatim.TweepyXAccount")
    @patch("herald.cli._get_settings")
    def test_live_post_exit_zero(self, mock_settings, mock_account_cls, tmp_path):
        mock_settings.return_value = MagicMock(
            twitter_consumer_key="ck", twitter_consumer_secret="cs",
            twitter_access_token="at", twitter_access_token_secret="ats",
            dry_run=False,
        )
        account = FakeAccount(create_result="42")
        mock_account_cls.return_value = account
        ledger = tmp_path / "ledger.jsonl"
        result = runner.invoke(app, [
            "post", "--file", str(self.write(tmp_path)), "--ledger", str(ledger),
            "--expect-sha256", content_sha256(TEXT),
        ])
        assert result.exit_code == 0, result.output
        assert "https://x.com/i/status/42" in result.output
        assert account.created == [TEXT]

    @patch("herald.verbatim.TweepyXAccount")
    @patch("herald.cli._get_settings")
    def test_live_uncertain_exit_four(self, mock_settings, mock_account_cls, tmp_path):
        mock_settings.return_value = MagicMock(dry_run=False)
        mock_account_cls.return_value = FakeAccount(
            create_error=requests.exceptions.ReadTimeout("slow"))
        result = runner.invoke(app, [
            "post", "--file", str(self.write(tmp_path)),
            "--ledger", str(tmp_path / "ledger.jsonl"),
        ])
        assert result.exit_code == 4
        assert "uncertain" in result.output

    @patch("herald.verbatim.TweepyXAccount")
    @patch("herald.cli._get_settings")
    def test_ledger_path_from_settings(self, mock_settings, mock_account_cls, tmp_path):
        # HERALD_POST_LEDGER in a .env file reaches the command through settings.
        ledger = tmp_path / "from-settings.jsonl"
        mock_settings.return_value = MagicMock(post_ledger=str(ledger), dry_run=False)
        mock_account_cls.return_value = FakeAccount(create_result="43")
        result = runner.invoke(app, ["post", "--file", str(self.write(tmp_path))],
                               env={"HERALD_POST_LEDGER": None})
        assert result.exit_code == 0, result.output
        assert ledger.exists()


    @patch("herald.verbatim.TweepyXAccount")
    def test_herald_dry_run_setting_keeps_post_preview_only(
        self, mock_account_cls, tmp_path, monkeypatch
    ):
        # HERALD_DRY_RUN=true is documented as preview-only for every command.
        monkeypatch.setenv("HERALD_DRY_RUN", "true")
        monkeypatch.setenv("HERALD_TWITTER_CONSUMER_KEY", "ck")
        monkeypatch.setenv("HERALD_TWITTER_CONSUMER_SECRET", "cs")
        monkeypatch.setenv("HERALD_TWITTER_ACCESS_TOKEN", "at")
        monkeypatch.setenv("HERALD_TWITTER_ACCESS_TOKEN_SECRET", "ats")
        monkeypatch.chdir(tmp_path)
        account = FakeAccount()
        mock_account_cls.return_value = account
        ledger = tmp_path / "ledger.jsonl"
        result = runner.invoke(app, ["post", "--file", str(self.write(tmp_path)),
                                     "--ledger", str(ledger), "--json"])
        assert result.exit_code == 3, result.output
        assert json.loads(result.output)["message"].startswith("dry run")
        mock_account_cls.assert_not_called()
        assert account.created == []
        assert not ledger.exists()


def test_settings_read_post_ledger_from_dotenv(tmp_path, monkeypatch):
    from herald.config import HeraldSettings

    monkeypatch.delenv("HERALD_POST_LEDGER", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("HERALD_POST_LEDGER=/data/ledger.jsonl\n",
                                   encoding="utf-8")
    assert HeraldSettings().post_ledger == "/data/ledger.jsonl"
