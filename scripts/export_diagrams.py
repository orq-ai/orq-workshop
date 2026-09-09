"""Export diagram sources (HTML with inline SVG) to PNG, diagram only, 2x.

    uv run --with playwright python scripts/export_diagrams.py [file.html ...]

No arguments exports every modules/*/assets/*.html and docs/assets/diagrams/*.html.
Needs a Playwright Chromium once: `uv run --with playwright playwright install chromium`.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
files = [Path(a) for a in sys.argv[1:]] or sorted(
    [*ROOT.glob("modules/*/assets/*.html"), *ROOT.glob("docs/assets/diagrams/*.html")]
)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(device_scale_factor=2)
    for src in files:
        page.goto(src.resolve().as_uri())
        page.wait_for_load_state("networkidle")
        page.evaluate("document.fonts.ready")
        out = src.with_suffix(".png")
        page.locator("svg").first.screenshot(path=str(out), omit_background=True)
        print(f"{out}  {out.stat().st_size // 1024} KB")
    browser.close()
