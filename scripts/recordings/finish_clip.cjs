// Finishes a terminal clip recorded with vhs: holds the frame at given cut points a little longer
// (vhs shortens the pauses after hidden waits) and burns in the captions from the approved storyboard.
// This ffmpeg has no text filters, so each caption is rendered to a PNG with headless Chrome and overlaid.
// Run: NODE_PATH=.context/node_modules node scripts/recordings/finish_clip.cjs scripts/recordings/clip-t1.json
//   clip.json: {"in": "...raw.mp4", "out": "...mp4", "holds": [{"at": 4.28, "add": 3.5}],
//               "captions": [{"from": 0, "to": 7.8, "text": "..."}]}   (caption times are after the holds)
const { chromium } = require("playwright");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const clip = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const work = fs.mkdtempSync(path.join(os.tmpdir(), "clip-"));

(async () => {
  const [width, height] = execFileSync("ffprobe", ["-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height", "-of", "csv=p=0", clip.in]).toString().trim().split(",").map(Number);

  // 1 · captions as transparent PNGs, one per line of the storyboard
  const browser = await chromium.launch({ channel: "chrome" });
  const page = await browser.newPage({ viewport: { width, height } });
  const pngs = [];
  for (const [i, c] of clip.captions.entries()) {
    await page.setContent(`<html><body style="margin:0;background:transparent;display:flex;align-items:flex-end;justify-content:center;height:${height}px">
      <div style="margin-bottom:40px;max-width:1100px;padding:14px 26px;border-radius:14px;background:rgba(247,246,245,.95);color:#151817;
      font:500 26px/1.35 Inter,-apple-system,sans-serif;text-align:center">${c.text}</div></body></html>`);
    const file = path.join(work, `cap-${i}.png`);
    await page.screenshot({ path: file, omitBackground: true });
    pngs.push(file);
  }
  await browser.close();

  // 2 · cut at the hold points, freeze each cut's last frame for `add` seconds, join
  const cuts = clip.holds.map((h) => h.at);
  const bounds = [0, ...cuts, null];
  const parts = [];
  let graph = "";
  for (let i = 0; i < bounds.length - 1; i++) {
    const end = bounds[i + 1] === null ? "" : `:end=${bounds[i + 1]}`;
    const add = clip.holds[i] ? clip.holds[i].add : 0;
    graph += `[0:v]trim=start=${bounds[i]}${end},setpts=PTS-STARTPTS${add ? `,tpad=stop_mode=clone:stop_duration=${add}` : ""}[s${i}];`;
    parts.push(`[s${i}]`);
  }
  graph += `${parts.join("")}concat=n=${parts.length}:v=1:a=0[base]`;

  // 3 · overlay every caption in its window
  let last = "base";
  clip.captions.forEach((c, i) => {
    graph += `;[${last}][${i + 1}:v]overlay=0:0:enable='between(t,${c.from},${c.to})'[v${i}]`;
    last = `v${i}`;
  });
  const inputs = ["-i", clip.in, ...pngs.flatMap((p) => ["-i", p])];
  fs.mkdirSync(path.dirname(clip.out), { recursive: true });
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", ...inputs, "-filter_complex", graph, "-map", `[${last}]`,
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", "-movflags", "+faststart", clip.out]);
  console.log(`saved ${clip.out}`);
})().catch((err) => { console.error(err.message); process.exit(1); });
