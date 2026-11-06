// Records a captioned Studio clip from an approved storyboard, in the recording browser that
// scripts/studio_browser.cjs started (attached over the DevTools port; your own browser is never used).
// Frames come from Chrome's screencast; captions, cards and highlight rings are drawn into the page,
// so they are part of the picture. ffmpeg assembles the frames into an MP4 at their real timing.
// Run: NODE_PATH=.context/node_modules node scripts/studio_record.cjs <clip.json> [--preview]
//   --preview saves one PNG per scene next to the output instead of recording.
//   clip.json: {"out": "docs/assets/videos/clip-3.mp4", "start": {"goto": url, "wait": text},
//     "scenes": [{"ms": 8000, "caption": "...", "actions": [{"card": "<html>"} | {"click": text, "nth": 0}
//       | {"scrollTo": text} | {"ring": text, "nth": 0} | {"ring": {"selector": css}} | {"wait": text}]}]}
const { chromium } = require("playwright");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const PORT = process.env.STUDIO_DEBUG_PORT || "9333";
const clip = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const preview = process.argv.includes("--preview");

function locate(page, spec) {
  if (typeof spec === "object" && spec.selector) return page.locator(spec.selector).first();
  const text = typeof spec === "object" ? spec.text : spec;
  return page.getByText(text, { exact: !!(spec && spec.exact) }).nth((spec && spec.nth) || 0);
}

async function overlay(page, kind, payload) {
  await page.evaluate(({ kind, payload }) => {
    const id = `rec-${kind}`;
    document.getElementById(id)?.remove();
    if (payload === null) return;
    const el = document.createElement("div");
    el.id = id;
    el.style.pointerEvents = "none";
    el.style.zIndex = 99999;
    el.style.position = "fixed";
    if (kind === "caption") {
      el.style.zIndex = 100001;  // above the card
      Object.assign(el.style, { left: "50%", bottom: "36px", transform: "translateX(-50%)", maxWidth: "1100px", padding: "14px 26px",
        borderRadius: "14px", background: "rgba(10,14,13,.9)", color: "#fff", font: "500 24px/1.35 Inter, -apple-system, sans-serif", textAlign: "center" });
      el.textContent = payload;
    } else if (kind === "card") {
      Object.assign(el.style, { inset: "0", display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(247,246,245,.92)", backdropFilter: "blur(3px)" });
      el.innerHTML = payload;
    } else if (kind === "ring") {
      const { x, y, width, height } = payload;
      Object.assign(el.style, { left: `${x - 6}px`, top: `${y - 6}px`, width: `${width + 12}px`, height: `${height + 12}px`, borderRadius: "10px",
        border: "3px solid #027f6b", boxShadow: "0 0 0 6px rgba(2,127,107,.18)" });
    }
    document.body.appendChild(el);
  }, { kind, payload });
}

async function act(page, a) {
  if (a.card !== undefined) return overlay(page, "card", a.card);
  if (a.wait) return locate(page, a.wait).waitFor({ timeout: 30000 });
  if (a.click) { await locate(page, a.click).click(); return page.waitForTimeout(a.settle || 2500); }
  if (a.scrollTo) { await locate(page, a.scrollTo).scrollIntoViewIfNeeded(); return page.waitForTimeout(600); }
  if (a.ring !== undefined) {
    if (a.ring === null) return overlay(page, "ring", null);
    const box = await locate(page, a.ring).boundingBox();
    if (!box) throw new Error(`ring target not on screen: ${JSON.stringify(a.ring)}`);
    return overlay(page, "ring", box);
  }
  throw new Error(`unknown action ${JSON.stringify(a)}`);
}

(async () => {
  const browser = await chromium.connectOverCDP(`http://127.0.0.1:${PORT}`);
  const page = await browser.contexts()[0].newPage();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(clip.start.goto, { waitUntil: "domcontentloaded" });
  await locate(page, clip.start.wait).waitFor({ timeout: 40000 });
  await page.waitForTimeout(clip.start.settle || 5000);
  await page.keyboard.press("Escape");

  const frames = fs.mkdtempSync(path.join(os.tmpdir(), "studio-rec-"));
  const shots = [];
  let cdp;
  if (!preview) {
    cdp = await page.context().newCDPSession(page);
    cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
      const file = path.join(frames, `${String(shots.length).padStart(5, "0")}.jpg`);
      fs.writeFileSync(file, Buffer.from(data, "base64"));
      shots.push({ file, t: metadata.timestamp });
      await cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
    });
    await cdp.send("Page.startScreencast", { format: "jpeg", quality: 90, maxWidth: 1440, maxHeight: 900 });
  }

  const t0 = Date.now() / 1000;
  for (const [i, scene] of clip.scenes.entries()) {
    const began = Date.now();
    await overlay(page, "ring", null);
    await overlay(page, "caption", scene.caption ?? null);
    for (const a of scene.actions || []) await act(page, a);
    if (preview) {
      const out = clip.out.replace(/\.mp4$/, `-scene-${i + 1}.png`);
      await page.screenshot({ path: out });
      console.log(`preview ${out}`);
    } else {
      await page.waitForTimeout(Math.max(0, scene.ms - (Date.now() - began)));
    }
  }
  if (preview) { await page.close(); process.exit(0); }

  await cdp.send("Page.stopScreencast");
  const end = Date.now() / 1000;
  const list = shots.map((s, i) => `file '${s.file}'\nduration ${(((shots[i + 1] || { t: end }).t) - s.t).toFixed(3)}`);
  list.push(`file '${shots[shots.length - 1].file}'`);
  fs.writeFileSync(path.join(frames, "list.txt"), list.join("\n"));
  fs.mkdirSync(path.dirname(clip.out), { recursive: true });
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", path.join(frames, "list.txt"),
    "-vf", "fps=25,scale=1440:-2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23", "-movflags", "+faststart", clip.out]);
  console.log(`saved ${clip.out} (${shots.length} frames, ${(end - t0).toFixed(1)} s)`);
  await page.close();
  process.exit(0);
})().catch((err) => { console.error(err.message); process.exit(1); });
