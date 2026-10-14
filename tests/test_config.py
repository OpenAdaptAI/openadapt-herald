"""Tests for the drafting model setting."""

from herald.config import DEFAULT_MODEL, HeraldSettings


def _settings() -> HeraldSettings:
    # Ignore any .env in the directory the tests run from.
    return HeraldSettings(_env_file=None)


def test_default_model_without_env(monkeypatch):
    monkeypatch.delenv("HERALD_DEFAULT_MODEL", raising=False)
    assert _settings().default_model == DEFAULT_MODEL


def test_env_sets_default_model(monkeypatch):
    monkeypatch.setenv("HERALD_DEFAULT_MODEL", "claude-test-model")
    assert _settings().default_model == "claude-test-model"


def test_empty_env_keeps_default_model(monkeypatch):
    # The workflow passes `${{ vars.HERALD_DEFAULT_MODEL }}`, which is an empty
    # string when the repository variable isn't set.
    monkeypatch.setenv("HERALD_DEFAULT_MODEL", "  ")
    assert _settings().default_model == DEFAULT_MODEL
