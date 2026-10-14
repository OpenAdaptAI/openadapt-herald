"""Tests for the drafting model setting."""

from herald.config import HeraldSettings

# Read the default from the field rather than importing a constant, so these
# tests fail on the behavior they check, not on a missing name.
_DEFAULT = HeraldSettings.model_fields["default_model"].default


def _settings() -> HeraldSettings:
    # Ignore any .env in the directory the tests run from.
    return HeraldSettings(_env_file=None)


def test_default_model_without_env(monkeypatch):
    monkeypatch.delenv("HERALD_DEFAULT_MODEL", raising=False)
    assert _settings().default_model == _DEFAULT
    assert _DEFAULT.strip()


def test_env_sets_default_model(monkeypatch):
    monkeypatch.setenv("HERALD_DEFAULT_MODEL", "claude-test-model")
    assert _settings().default_model == "claude-test-model"


def test_empty_env_keeps_default_model(monkeypatch):
    # The workflow passes `${{ vars.HERALD_DEFAULT_MODEL }}`, which is an empty
    # string when the repository variable isn't set.
    for blank in ("", "  "):
        monkeypatch.setenv("HERALD_DEFAULT_MODEL", blank)
        assert _settings().default_model == _DEFAULT, repr(blank)


def test_config_names_the_default_once():
    from herald import config

    assert config.DEFAULT_MODEL == _DEFAULT
