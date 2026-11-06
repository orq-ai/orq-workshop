// Opens the isolated recording browser: a plain Chrome process with its own profile under
// .context/studio-profile/ (gitignored), never the browser you use day to day. It is started as a
// normal Chrome, not by Playwright, so the Studio's Cloudflare check treats it like any browser;
// scripts/studio_shots.cjs attaches to it over the DevTools port only to take screenshots.
// Log in to the orq.ai Studio once in this window and switch to the recording project. The
// session stays in the profile for later runs.
// Run: node scripts/studio_browser.cjs
const { spawn } = require("child_process");
const path = require("path");

const CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = process.env.STUDIO_DEBUG_PORT || "9333";
const profile = path.resolve(__dirname, "..", ".context", "studio-profile");

const chrome = spawn(CHROME, [`--user-data-dir=${profile}`, `--remote-debugging-port=${PORT}`, "--no-first-run", "--no-default-browser-check", "https://my.orq.ai/"], { detached: true, stdio: "ignore" });
chrome.unref();
console.log(`recording browser started (pid ${chrome.pid}, DevTools port ${PORT}, profile ${profile})`);
console.log("log in, switch to the recording project, and leave the window open for scripts/studio_shots.cjs");
