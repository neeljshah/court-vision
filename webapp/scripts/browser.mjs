// browser.mjs -- the ONE Chrome launcher the browser-driven QA scripts share
// (a11y-gate, keyboard-walk, third-party-requests). playwright-core only: no browser
// download. In CI the runner's Google Chrome (channel "chrome"); locally set
// A11Y_CHROME=/path/to/chrome (or chromium). ASCII only.
import { chromium } from "playwright-core";

export async function launchChrome(tool = "browser") {
  const executablePath = process.env.A11Y_CHROME;
  if (executablePath) return chromium.launch({ executablePath, args: ["--no-sandbox"] });
  try {
    return await chromium.launch({ channel: "chrome", args: ["--no-sandbox"] });
  } catch (err) {
    throw new Error(`${tool}: no Chrome found (${err.message.split("\n")[0]}); set A11Y_CHROME=/path/to/chrome`);
  }
}
