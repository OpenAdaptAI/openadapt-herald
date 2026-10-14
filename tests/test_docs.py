"""Keep the README, the docs and .env.example in step with the code."""

import re
import shlex
from pathlib import Path

import pytest
import typer

from herald.cli import app
from herald.config import HeraldSettings

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DOCS = [README, *sorted((ROOT / "docs").glob("*.md"))]

_FENCE = re.compile(r"```(?:bash|sh|console)?\n(.*?)```", re.DOTALL)


def _herald_commands(path: Path) -> list[list[str]]:
    """Return each `herald ...` command in the file's code blocks, as tokens."""
    commands = []
    for block in _FENCE.findall(path.read_text()):
        joined = block.replace("\\\n", " ")
        for line in joined.splitlines():
            line = line.split("#", 1)[0].strip()
            if line.startswith("herald "):
                commands.append(shlex.split(line))
    return commands


def _options(command) -> set[str]:
    names = set()
    for param in command.params:
        names.update(param.opts)
        names.update(getattr(param, "secondary_opts", []))
    return names


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_documented_commands_and_options_exist(path):
    group = typer.main.get_command(app)
    commands = _herald_commands(path)
    for tokens in commands:
        name = tokens[1]
        assert name in group.commands, f"{path.name}: unknown command `herald {name}`"
        known = _options(group.commands[name]) | {"--help"}
        for token in tokens[2:]:
            if token.startswith("--"):
                flag = token.split("=", 1)[0]
                assert flag in known, f"{path.name}: `herald {name}` has no option {flag}"


def test_readme_quick_start_is_documented():
    commands = [" ".join(t[:2]) for t in _herald_commands(README)]
    assert "herald collect" in commands
    assert "herald preview" in commands


def test_env_example_names_real_settings():
    fields = set(HeraldSettings.model_fields)
    names = re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)=", (ROOT / ".env.example").read_text(), re.M)
    assert names, ".env.example lists no settings"
    for name in names:
        assert name.startswith("HERALD_"), (
            f".env.example sets {name}, but herald reads only HERALD_* names from .env"
        )
        assert name.removeprefix("HERALD_").lower() in fields, f"{name} is not a herald setting"


def test_readme_keeps_status_language_in_compliance_doc():
    text = README.read_text()
    for phrase in ("admitted", "admission", "lifecycle", "evidence authority", "product target"):
        assert phrase not in text.lower(), f"README mentions {phrase!r}; it belongs in docs/"
    links = re.findall(r"\]\([^)]*docs/COMPLIANCE\.md\)", text)
    assert len(links) == 1, "link docs/COMPLIANCE.md from the README exactly once"
    assert (ROOT / "docs" / "COMPLIANCE.md").exists()


def test_readme_installs_from_github_until_herald_is_on_pypi():
    # `pip install herald-announce` returned 404: the package isn't on PyPI.
    installs = [
        line.strip()
        for block in _FENCE.findall(README.read_text())
        for line in block.splitlines()
        if "pip install" in line
    ]
    assert installs, "the README shows no install command"
    for line in installs:
        assert "git+https://github.com/OpenAdaptAI/openadapt-herald" in line, line
