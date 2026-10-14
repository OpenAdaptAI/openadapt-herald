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
# An `if:` condition is an expression even without `${{ }}` around it.
_BARE_IF = re.compile(r"^[ \t]*(?:-[ \t]+)?if[ \t]*:[ \t]*(.+)$", re.MULTILINE)
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
    expressions = [m.group(0) for m in _EXPRESSION.finditer(text)]
    expressions += [m.group(1) for m in _BARE_IF.finditer(text) if "${{" not in m.group(1)]
    return [expr.strip() for expr in expressions if compare.search(expr)]


def _publish_step(text: str) -> str:
    """Return the text of the "Publish announcements" step."""
    match = re.search(r"- name: Publish announcements\n(.*?)(?=\n\s*- name:|\Z)", text, re.DOTALL)
    assert match, "release-announce.yml has no 'Publish announcements' step"
    return match.group(1)


def test_release_announce_declares_dry_run_as_boolean():
    # Guards the text walker below: if it stops finding this input, the
    # comparison test would pass without checking anything.
    assert "dry_run" in _boolean_inputs(RELEASE_ANNOUNCE.read_text())


def test_string_comparison_check_covers_every_expression_form():
    # Guards the comparison finder: each of these forms ignores a boolean input.
    workflow = """\
on:
  workflow_dispatch:
    inputs:
      dry_run:
        type: boolean
jobs:
  a:
    steps:
      - if: inputs.dry_run == 'true'
      - if: ${{ 'true' != inputs.dry_run }}
      - run: echo ${{ inputs.dry_run == "true" && 'x' || '' }}
      - if: github.event.inputs.dry_run == 'true'
      - if: inputs.dry_run
"""
    assert _boolean_inputs(workflow) == {"dry_run"}
    assert _string_comparisons(workflow, "dry_run") == [
        "${{ 'true' != inputs.dry_run }}",
        "${{ inputs.dry_run == \"true\" && 'x' || '' }}",
        "inputs.dry_run == 'true'",
    ]


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
    # The flag reaches the shell through env, and the script passes it on.
    assert re.search(r"DRY_RUN_FLAG:\s*\$\{\{\s*inputs\.dry_run\s*&&\s*'--dry-run'", step)
    (script,) = _run_blocks(step)
    assert '${DRY_RUN_FLAG:+"$DRY_RUN_FLAG"}' in script


def test_publish_step_lets_a_repository_variable_set_the_model():
    # The digest died on a retired model id. A repository variable lets the
    # operator change the model without a code change.
    step = _publish_step(RELEASE_ANNOUNCE.read_text())
    assert re.search(
        r"HERALD_DEFAULT_MODEL:\s*\$\{\{\s*vars\.HERALD_DEFAULT_MODEL\s*\}\}", step
    ), "pass HERALD_DEFAULT_MODEL from the repository variables to `herald publish`"


# Script injection. GitHub replaces each `${{ ... }}` in a `run:` script with
# its value before the shell starts, so a workflow_dispatch input such as
# days = `7"; curl ... ; echo "` becomes shell code. Inputs and step outputs
# must reach the shell through `env:` and be quoted there.

_RUN_KEY = re.compile(r"^(?P<indent>[ \t]*(?:-[ \t]+)?)run[ \t]*:[ \t]*(?P<value>.*)$")


def _run_blocks(text: str) -> list[str]:
    """Return the script of every `run:` key, inline or as a `|`/`>` block."""
    lines = text.splitlines()
    blocks = []
    for i, line in enumerate(lines):
        match = _RUN_KEY.match(line)
        if not match:
            continue
        value = match.group("value").strip()
        if value and value[0] not in "|>":
            blocks.append(value)
            continue
        key_column = len(match.group("indent"))
        body = []
        for following in lines[i + 1:]:
            if following.strip() and len(following) - len(following.lstrip()) <= key_column:
                break
            body.append(following)
        blocks.append("\n".join(body))
    return blocks


def _step(text: str, name: str) -> str:
    match = re.search(rf"- name: {re.escape(name)}\n(.*?)(?=\n\s*- name:|\Z)", text, re.DOTALL)
    assert match, f"no step named {name!r}"
    return match.group(1)


def test_run_block_finder_sees_inline_and_block_scripts():
    workflow = """\
jobs:
  a:
    steps:
      - run: echo ${{ inputs.one }}
      - name: Two
        run: |
          echo first
          echo ${{ inputs.two }}
        env:
          X: ${{ inputs.safe_here }}
"""
    assert _run_blocks(workflow) == [
        "echo ${{ inputs.one }}",
        "          echo first\n          echo ${{ inputs.two }}",
    ]
    assert len(_run_blocks(RELEASE_ANNOUNCE.read_text())) >= 3


@pytest.mark.parametrize("workflow", WORKFLOW_FILES, ids=lambda p: p.name)
def test_run_scripts_contain_no_expressions(workflow):
    offending = [
        expr.group(0)
        for block in _run_blocks(workflow.read_text())
        for expr in _EXPRESSION.finditer(block)
    ]
    assert offending == [], (
        f"{workflow.name} expands expressions inside run: scripts, where a dispatch "
        f"input becomes shell code. Pass them through env: and quote them: {offending}"
    )


def _run_params_step(tmp_path, **env):
    import shutil
    import subprocess

    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not installed")
    (script,) = _run_blocks(_step(RELEASE_ANNOUNCE.read_text(), "Determine content type"))
    # Do what the runner does first: replace each expression with its value.
    context = {
        "github.event_name": env.get("GITHUB_EVENT_NAME", ""),
        "inputs.content_type": env.get("INPUT_CONTENT_TYPE", ""),
        "inputs.days": env.get("INPUT_DAYS", ""),
    }
    script = _EXPRESSION.sub(lambda m: context[m.group(1).strip()], script)
    output = tmp_path / "github_output"
    output.write_text("")
    result = subprocess.run(
        [bash, "-e", "-c", script],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "GITHUB_OUTPUT": str(output), **env},
    )
    return result, output.read_text()


# The payloads print INJECTED-42 only if the shell evaluates them, so the
# marker never appears just because the raw input was echoed back.
_RAN = "INJECTED-42"


@pytest.mark.parametrize(
    "days",
    [
        '7"; echo INJECTED-$((6*7)); echo "',
        "7 ; echo INJECTED-$((6*7))",
        "$(echo INJECTED-$((6*7)))",
        "7\ntype=release",
        "",
        "-1",
    ],
)
def test_params_step_rejects_days_that_are_not_a_number(tmp_path, days):
    result, outputs = _run_params_step(
        tmp_path,
        GITHUB_EVENT_NAME="workflow_dispatch",
        INPUT_CONTENT_TYPE="digest",
        INPUT_DAYS=days,
    )
    assert _RAN not in result.stdout + result.stderr + outputs, "the shell ran the input"
    assert result.returncode != 0
    assert "days=" not in outputs


def test_params_step_rejects_an_unknown_content_type(tmp_path):
    result, outputs = _run_params_step(
        tmp_path,
        GITHUB_EVENT_NAME="workflow_dispatch",
        INPUT_CONTENT_TYPE="digest; echo INJECTED-$((6*7))",
        INPUT_DAYS="7",
    )
    assert _RAN not in result.stdout + result.stderr + outputs, "the shell ran the input"
    assert result.returncode != 0
    assert "type=" not in outputs


def test_params_step_passes_valid_dispatch_inputs(tmp_path):
    result, outputs = _run_params_step(
        tmp_path,
        GITHUB_EVENT_NAME="workflow_dispatch",
        INPUT_CONTENT_TYPE="release",
        INPUT_DAYS="30",
    )
    assert result.returncode == 0, result.stderr
    assert outputs.splitlines() == ["type=release", "days=30", "embed_title=New release"]


def test_params_step_uses_digest_defaults_on_schedule(tmp_path):
    result, outputs = _run_params_step(tmp_path, GITHUB_EVENT_NAME="schedule")
    assert result.returncode == 0, result.stderr
    assert outputs.splitlines() == ["type=digest", "days=7", "embed_title=Weekly digest"]


def test_params_step_titles_a_spotlight(tmp_path):
    result, outputs = _run_params_step(
        tmp_path,
        GITHUB_EVENT_NAME="workflow_dispatch",
        INPUT_CONTENT_TYPE="spotlight",
        INPUT_DAYS="7",
    )
    assert result.returncode == 0, result.stderr
    assert "embed_title=Feature spotlight" in outputs.splitlines()


def test_publish_step_titles_the_embed_from_the_content_type():
    step = _publish_step(RELEASE_ANNOUNCE.read_text())
    assert re.search(r"EMBED_TITLE:\s*\$\{\{\s*steps\.params\.outputs\.embed_title\s*\}\}", step)
    assert '--embed-title "$EMBED_TITLE"' in step
