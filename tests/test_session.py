import yaml

from scripts.build_session import ROOT, run_of_show


def test_every_session_manifest_builds_and_fills_the_clock():
    for folder in (ROOT / "sessions").iterdir():
        if (folder / "session.yml").exists():
            days = yaml.safe_load((folder / "session.yml").read_text()).get("days", [None])
            for i, _ in enumerate(days):
                assert "Ends " in run_of_show(folder, day=None if days == [None] else i), folder
