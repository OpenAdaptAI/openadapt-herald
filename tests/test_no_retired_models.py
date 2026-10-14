"""Fail when shipped code or docs name a Claude model that the API no longer serves.

The weekly digest stopped on 2026-07-13 with a 404 for
`claude-sonnet-4-20250514`, which was hardcoded as the default. Add an id here
when Anthropic retires it. Tests are not scanned: they may use a retired id as
an example of a model that returns 404.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

RETIRED_MODEL_IDS = [
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
    "claude-3-7-sonnet-20250219",
    "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-20240620",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
]

SCANNED = sorted(
    [
        *(ROOT / "herald").rglob("*.py"),
        *(ROOT / "herald").rglob("*.md"),
        *(ROOT / "docs").rglob("*.md"),
        *(ROOT / ".github" / "workflows").glob("*.y*ml"),
        *ROOT.glob("*.md"),
        ROOT / ".env.example",
        ROOT / "pyproject.toml",
    ]
)


def test_scan_covers_the_default_model_setting():
    assert ROOT / "herald" / "config.py" in SCANNED
    assert ROOT / ".env.example" in SCANNED


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: str(p.relative_to(ROOT)))
def test_no_retired_model_ids(path):
    text = path.read_text(encoding="utf-8")
    found = [model for model in RETIRED_MODEL_IDS if model in text]
    assert found == [], f"{path.relative_to(ROOT)} names retired model ids: {found}"
