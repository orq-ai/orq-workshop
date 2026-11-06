"""Alternate credential files stay out of git, and the day-framing rule names where it is lifted."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("name", [".env.academy", ".env.admin"])
def test_alternate_env_files_are_ignored(name):
    assert subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT).returncode == 0


def test_agents_md_scopes_the_day_rule():
    text = (ROOT / "AGENTS.md").read_text()
    assert "Onboarding pages" in text
    assert "may use days and clock times" in text
