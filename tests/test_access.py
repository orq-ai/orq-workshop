"""Steps a participant key cannot run are marked as instructor demos and listed in one table."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEEDS = {"smart-routing": "admin key", "guardrails": "admin key", "budgets-and-keys": "Management Key", "mcp-gateway": "workspace-wide key", "knowledge-base": "public tunnel", "alerts-and-webhooks": "public tunnel"}


def test_restricted_steps_are_marked_and_tabled():
    table = (ROOT / "docs/start/for-engineers.md").read_text()
    for slug, need in NEEDS.items():
        assert f"../modules/{slug}.md" in table, slug
        assert need in table, need
        assert '!!! instructor "Instructor demo' in (ROOT / f"modules/{slug}/README.md").read_text(), slug
