"""Export SVG diagram sources (styled by scripts/diagram.css) to committed PNGs (`make diagrams`).

    uv run --with playwright python scripts/export_diagrams.py [file.svg ...]

No arguments exports every modules/*/assets/*.svg and docs/assets/diagrams/*.svg; the PNG lands
next to its source with the same stem. The PNGs are committed: GitHub renders the READMEs from
them, and scripts/mkdocs_hooks.py registers them for the docs site. Each PNG is about 2400px
wide (2x for a 1000 unit viewBox, less for wider ones) with the sand background baked in.
Needs a Playwright Chromium once: `uv run --with playwright playwright install chromium`.
"""

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TARGET_WIDTH = 2400
files = [Path(arg).resolve() for arg in sys.argv[1:]] or sorted(
    [*ROOT.glob("modules/*/assets/*.svg"), *ROOT.glob("docs/assets/diagrams/*.svg")]
)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    for source in files:
        width = int(re.search(r'viewBox="0 0 (\d+)', source.read_text()).group(1))
        page = browser.new_page(device_scale_factor=min(2, TARGET_WIDTH / width))
        page.goto(source.as_uri())
        page.wait_for_load_state("networkidle")
        # The web fonts load after the page is "loaded"; screenshot before they arrive and the
        # labels render in the fallback face.
        page.evaluate("document.fonts.ready")
        output = source.with_suffix(".png")
        page.locator("svg").first.screenshot(path=str(output), omit_background=True)
        page.close()
        print(f"{output.relative_to(ROOT)}")
    browser.close()
