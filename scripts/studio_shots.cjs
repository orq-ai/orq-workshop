// Takes annotated Studio screenshots for a module's Studio tabs, in the recording browser that
// scripts/studio_browser.cjs started (attached over the DevTools port; your own browser is never used).
// Each shot: open a Studio URL, wait for a piece of text, draw numbered callouts next to the
// elements the tab's numbered steps name, save a PNG.
// Run: NODE_PATH=.context/node_modules node scripts/studio_shots.cjs <shots.json>
//   shots.json: [{"out": "modules/tracing/assets/studio-step-1.png", "url": "https://my.orq.ai/...",
//                 "wait": "refund-turn", "scrollTo": {"text": "Rating", "exact": true},
//                 "callouts": [{"n": 1, "text": "Traces", "exact": true}, {"n": 2, "selector": "input"}]}]
const { chromium } = require("playwright");
const fs = require("fs");

const PORT = process.env.STUDIO_DEBUG_PORT || "9333";

function target(page, spec) {
  if (spec.selector) return page.locator(spec.selector).first();
  return page.getByText(spec.text, { exact: !!spec.exact }).nth(spec.nth || 0);
}

async function callout(page, spec) {
  const n = spec.n;
  const box = await target(page, spec).boundingBox();
  if (!box) throw new Error(`callout ${n}: ${spec.selector || spec.text} not on screen`);
  await page.evaluate(({ n, x, y }) => {
    const dot = document.createElement("div");
    dot.textContent = String(n);
    Object.assign(dot.style, {
      position: "fixed", left: `${x}px`, top: `${y}px`, width: "26px", height: "26px", borderRadius: "50%",
      background: "#027f6b", color: "#fff", font: "600 14px/26px Inter, sans-serif", textAlign: "center",
      boxShadow: "0 0 0 3px #fff", zIndex: 99999, pointerEvents: "none",
    });
    document.body.appendChild(dot);
  }, { n, x: Math.max(4, box.x - 32), y: box.y + box.height / 2 - 13 });
}

(async () => {
  const shots = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  const browser = await chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
  const page = await browser.contexts()[0].newPage();
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const shot of shots) {
    await page.goto(shot.url, { waitUntil: "domcontentloaded" });
    await page.getByText(shot.wait, { exact: false }).first().waitFor({ timeout: 30000 });
    await page.waitForTimeout(shot.settle || 2500);
    for (const step of shot.click || []) {
      await page.getByText(step, { exact: false }).first().click();
      await page.waitForTimeout(2000);
    }
    await page.keyboard.press("Escape");
    if (shot.scrollTo) {
      await target(page, shot.scrollTo).scrollIntoViewIfNeeded();
      await page.waitForTimeout(800);
    }
    for (const c of shot.callouts || []) await callout(page, c);
    await page.screenshot({ path: shot.out });
    console.log(`saved ${shot.out}`);
  }
  await page.close();
  process.exit(0);
})().catch((err) => { console.error(err.message); process.exit(1); });
