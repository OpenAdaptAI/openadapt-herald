"""Tests for the GitHub Actions workflows.

A ``workflow_dispatch`` input declared ``type: boolean`` reaches expressions as
a real boolean through the ``inputs`` context. Comparing it with a quoted
string such as ``'true'`` is always false: the expression engine converts both
sides to numbers, so ``true`` becomes 1 and ``'true'`` becomes NaN. A check
written that way silently ignores the input.

These tests read the workflow files as text so they need no YAML parser.
"""

import re
from pathlib import Path

import pytest

WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"
WORKFLOW_FILES = sorted(WORKFLOWS_DIR.glob("*.y*ml"))
RELEASE_ANNOUNCE = WORKFLOWS_DIR / "release-announce.yml"

_EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}", re.DOTALL)
_KEY = re.compile(r"([A-Za-z0-9_-]+)\s*:")
_BOOLEAN_TYPE = re.compile(r"""type\s*:\s*["']?boolean["']?\s*(#.*)?$""")


def _boolean_inputs(text: str) -> set[str]:
    """Return the names of the inputs declared ``type: boolean``.

    Walks the file by indentation. The input name is the closest key above the
    ``type: boolean`` line with less indentation, and that key's own parent
    must be ``inputs``.
    """
    names: set[str] = set()
    stack: list[tuple[int, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if _BOOLEAN_TYPE.fullmatch(stripped) and len(stack) >= 2 and stack[-2][1] == "inputs":
            names.add(stack[-1][1])
        key = _KEY.match(stripped)
        if key:
            stack.append((indent, key.group(1)))
    return names


def _string_comparisons(text: str, name: str) -> list[str]:
    """Return the expressions that compare ``inputs.<name>`` with a quoted string."""
    ref = rf"(?<![\w.])inputs\.{re.escape(name)}\b"
    compare = re.compile(
        rf"{ref}\s*[!=]=\s*['\"]|['\"]\s*[!=]=\s*{ref}",
        re.IGNORECASE,
    )
    return [m.group(0).strip() for m in _EXPRESSION.finditer(text) if compare.search(m.group(1))]


def _publish_step(text: str) -> str:
    """Return the text of the "Publish announcements" step."""
    match = re.search(r"- name: Publish announcements\n(.*?)(?=\n\s*- name:|\Z)", text, re.DOTALL)
    assert match, "release-announce.yml has no 'Publish announcements' step"
    return match.group(1)


def test_release_announce_declares_dry_run_as_boolean():
    # Guards the text walker below: if it stops finding this input, the
    # comparison test would pass without checking anything.
    assert "dry_run" in _boolean_inputs(RELEASE_ANNOUNCE.read_text())


@pytest.mark.parametrize("workflow", WORKFLOW_FILES, ids=lambda p: p.name)
def test_boolean_inputs_are_not_compared_with_strings(workflow):
    text = workflow.read_text()
    offending = [
        expr for name in sorted(_boolean_inputs(text)) for expr in _string_comparisons(text, name)
    ]
    assert offending == [], (
        f"{workflow.name} compares a boolean input with a string, which is always false. "
        f"Use the input directly, for example `inputs.dry_run && '--dry-run' || ''`: {offending}"
    )


def test_publish_step_passes_dry_run_to_herald():
    step = _publish_step(RELEASE_ANNOUNCE.read_text())
    # The command-line flag.
    assert re.search(r"\$\{\{\s*inputs\.dry_run\s*&&\s*'--dry-run'\s*\|\|\s*''\s*\}\}", step)
    # The HERALD_DRY_RUN setting, so a dry run stays a dry run even if the flag is lost.
    assert re.search(
        r"HERALD_DRY_RUN:\s*\$\{\{\s*inputs\.dry_run\s*&&\s*'true'\s*\|\|\s*'false'\s*\}\}", step
    )
