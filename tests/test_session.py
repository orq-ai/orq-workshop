import yaml

from scripts.build_session import ROOT, run_of_show


def test_every_session_manifest_builds_and_fills_the_clock():
    for folder in (ROOT / "sessions").iterdir():
        if (folder / "session.yml").exists():
            days = yaml.safe_load((folder / "session.yml").read_text()).get("days", [None])
            for i, _ in enumerate(days):
                assert "Ends " in run_of_show(folder, day=None if days == [None] else i), folder


def test_public_page_counts_minutes_not_clock_time():
    table = run_of_show(ROOT / "sessions" / "techdays-2026", docs=True)
    assert "Clock" not in table and "Ends " not in table and "Total: 120 min" in table


def test_run_of_show_commands_use_module_slugs():
    import re
    for folder in (ROOT / "sessions").iterdir():
        if (folder / "session.yml").exists():
            days = yaml.safe_load((folder / "session.yml").read_text()).get("days", [None])
            for i, _ in enumerate(days):
                text = run_of_show(folder, day=None if days == [None] else i)
                assert not re.search(r"make m\d\d", text), folder
                assert "modules/0" not in text and "modules/1" not in text, folder
