"""The scripted traffic that recordings show: real calls, fixed inputs, nothing a later lesson must not reveal."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "app/data/recording_script.jsonl"
PLANTED = ["use your judgment", "telling the truth", "read it back", "colleague", "without asking for tracking"]
SLICE_PAGES = [ROOT / "docs/academy/trace.md", ROOT / "modules/tracing/README.md"]


def rows():
    return [json.loads(line) for line in SCRIPT.read_text().splitlines() if line.strip()]


def test_script_orders_exist():
    known = {o["id"] for o in json.loads((ROOT / "app/data/orders.json").read_text())["orders"]}
    for row in rows():
        for turn in row["turns"]:
            for order in re.findall(r"ord_[a-z0-9]+", turn["text"]):
                assert order in known, order


def test_script_threads_carry_the_prefix():
    for row in rows():
        assert row["thread"].startswith("ws-"), row["thread"]
        for turn in row["turns"]:
            assert turn["instructions"] in {"fixed", "skip-lookup"}, turn


def test_script_does_not_name_planted_behaviors():
    text = SCRIPT.read_text().lower() + (ROOT / "app/recording_traffic.py").read_text().lower()
    for term in PLANTED:
        assert term not in text, term


def test_traffic_sends_top_level_body_fields():
    code = (ROOT / "app/recording_traffic.py").read_text()
    assert "extra_body" in code
    for field in ('"name"', '"identity"', '"thread"'):
        assert field in code, field


def test_slice_storyboards_have_a_status_and_recorded_ones_embed_their_video():
    found = 0
    for page in SLICE_PAGES:
        text = page.read_text()
        for block in re.findall(r'<section class="storyboard".*?</section>', text, re.S):
            found += 1
            status = re.search(r'data-status="([a-z]+)"', block).group(1)
            assert status in {"awaiting", "approved", "recorded"}, (page, status)
            if status == "recorded":
                videos = re.findall(r'<video[^>]*src="([^"]+\.mp4)"', block)
                assert videos, (page, "recorded storyboard without a <video>")
                for src in videos:
                    assert (page.parent / src).exists() or (ROOT / "docs" / src.lstrip("./")).exists(), src
    assert found >= 2


def test_recording_identity_is_its_own():
    """Clip 3 filters on the customer; sharing the tracing module's identity would show every run."""
    for row in rows():
        assert row["identity"] != "customer-user_001", row["identity"]


def test_recording_traffic_traces_its_own_steps():
    code = (ROOT / "app/recording_traffic.py").read_text()
    assert "setup_otel(force=True)" in code and '@traced(type="tool"' in code and '@traced(type="agent"' in code
