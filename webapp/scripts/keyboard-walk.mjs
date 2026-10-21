// keyboard-walk.mjs -- a keyboard-only walk over the exported shell: Tab from the top
// of each page and check that the skip link is the first stop and lands on
// #main-content, that every element reached by Tab shows a focus indicator (computed
// outline or box-shadow), that the theme toggle and the narrow-screen menu work from
// the keyboard, that the command palette opens on "/" and Ctrl/Cmd+K, keeps focus
// inside, closes on Escape and hands focus back to the trigger, and that the desk
// tabs are reached in order. Prints a Markdown table of PASS/FAIL rows plus a
// ```json blob; exits non-zero on any FAIL. ASCII only.
//
//   A11Y_CHROME=/path/to/chrome node scripts/keyboard-walk.mjs [outDir=out] [pagesFile=perf/keyboard-pages.json]
import { readFileSync } from "node:fs";
import { createServer } from "./serve-export.mjs";
import { resolvePage, readManifest } from "./perf-pages.mjs";
import { launchChrome } from "./browser.mjs";

const MAX_TABS = 700;
const DESK_TABS = ["Record", "How in-game works", "Execution", "Models", "Health"];

/** Where keyboard focus is, with the computed indicator. Runs in the page. */
const FOCUS_INFO = () => {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return { body: true };
  const cs = getComputedStyle(el);
  const r = el.getBoundingClientRect();
  const name = (el.getAttribute("aria-label") || el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 50);
  const outline = cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0;
  const shadow = !!cs.boxShadow && cs.boxShadow !== "none";
  return {
    tag: el.tagName.toLowerCase(), name, href: el.getAttribute("href"), id: el.id || null,
    outline: `${cs.outlineStyle} ${cs.outlineWidth}`, boxShadow: cs.boxShadow === "none" ? "none" : "set",
    indicator: outline || shadow, focusVisible: el.matches(":focus-visible"),
    onScreen: r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth,
    inDialog: !!el.closest("[role=dialog]"), inDeskTabs: !!el.closest('nav[aria-label="Desk pages"]'),
  };
};
const focusInfo = (pg) => pg.evaluate(FOCUS_INFO);
const describe = (f) => `${f.tag}${f.id ? "#" + f.id : ""} "${f.name}"${f.href ? ` (${f.href})` : ""}`;

/** Decide a check; exported for the test. */
export function verdict(ok, detail) { return { result: ok ? "PASS" : "FAIL", detail }; }

export function formatRows(rows) {
  const L = ["| page | check | result | detail |", "|---|---|---|---|"];
  for (const r of rows) L.push(`| ${r.page} | ${r.check} | ${r.result} | ${String(r.detail).replace(/\|/g, "\\|")} |`);
  return L.join("\n");
}

async function openPage(browser, url, width) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 } });
  await ctx.addInitScript(() => { try { localStorage.setItem("cv-theme", "light"); } catch {} });
  const pg = await ctx.newPage();
  await pg.goto(url, { waitUntil: "networkidle" });
  await pg.waitForTimeout(300);
  return { ctx, pg };
}

async function walkPage(browser, base, page, rows) {
  const add = (check, v) => rows.push({ page, check, ...v });
  const { ctx, pg } = await openPage(browser, base + page, 1280);
  try {
    // 1. Skip link first, and it lands on #main-content.
    await pg.keyboard.press("Tab");
    const first = await focusInfo(pg);
    add("skip link is the first Tab stop", verdict(first.href === "#main-content" && first.onScreen && first.indicator,
      `${first.body ? "body" : describe(first)}; on screen ${first.onScreen}; outline ${first.outline}; box-shadow ${first.boxShadow}`));
    await pg.keyboard.press("Enter");
    await pg.waitForTimeout(100);
    const landed = await pg.evaluate(() => ({ hash: location.hash, active: document.activeElement && document.activeElement.id }));
    add("skip link moves focus to #main-content", verdict(landed.hash === "#main-content" && landed.active === "main-content",
      `hash ${landed.hash || "(none)"}; focus on #${landed.active || "(body)"}`));

    // 2. Every Tab stop shows an indicator; desk tabs come in order.
    await pg.evaluate(() => { location.hash = ""; (document.activeElement).blur(); window.scrollTo(0, 0); });
    const stops = [], missing = [], offScreen = [], deskOrder = [];
    for (let i = 0; i < MAX_TABS; i++) {
      await pg.keyboard.press("Tab");
      const f = await focusInfo(pg);
      if (f.body) break;
      stops.push(f);
      if (!f.indicator) missing.push(describe(f) + ` [outline ${f.outline}; box-shadow ${f.boxShadow}]`);
      if (!f.onScreen) offScreen.push(describe(f));
      if (f.inDeskTabs) deskOrder.push(f.name);
    }
    add("every Tab stop has a visible focus indicator", verdict(stops.length > 0 && missing.length === 0,
      `${stops.length} stops; ${missing.length} without: ${missing.slice(0, 8).join(" | ") || "none"}${stops.length >= MAX_TABS ? " (cap hit)" : ""}`));
    add("every Tab stop is on screen when focused", verdict(offScreen.length === 0, offScreen.slice(0, 6).join(" | ") || `${stops.length} stops all on screen`));
    if (page === "/desk/") add("desk tabs reached in order", verdict(JSON.stringify(deskOrder) === JSON.stringify(DESK_TABS), deskOrder.join(" > ") || "none reached"));

    // 3. Theme toggle by keyboard (Space, then Enter).
    await pg.focus('button[aria-label="Dark theme"]');
    const t0 = await pg.evaluate(() => document.documentElement.getAttribute("data-theme"));
    await pg.keyboard.press("Space");
    const t1 = await pg.evaluate(() => document.documentElement.getAttribute("data-theme"));
    await pg.keyboard.press("Enter");
    const t2 = await pg.evaluate(() => ({ theme: document.documentElement.getAttribute("data-theme"), pressed: document.activeElement.getAttribute("aria-pressed") }));
    add("theme toggle works from the keyboard", verdict(t0 !== t1 && t1 !== t2.theme && t2.pressed === String(t2.theme === "dark"), `${t0} -> Space -> ${t1} -> Enter -> ${t2.theme}; aria-pressed ${t2.pressed}`));

    // 4. Command palette: "/" from a focused link, focus trap, Escape returns focus.
    await pg.focus('a[href$="/analytics/ask/"]');
    await pg.keyboard.press("/");
    const dialog = pg.locator("[cmdk-root]").first();
    let opened = true;
    try { await dialog.waitFor({ state: "visible", timeout: 8000 }); } catch { opened = false; }
    const inInput = opened && await pg.evaluate(() => !!document.activeElement && document.activeElement.hasAttribute("cmdk-input"));
    const inputFocus = opened ? await focusInfo(pg) : null;
    add("palette opens on / with focus in the search input", verdict(opened && inInput, opened ? `${describe(inputFocus)}; outline ${inputFocus.outline}; box-shadow ${inputFocus.boxShadow}` : "dialog did not open"));
    add("palette search input shows a focus indicator", verdict(!!inputFocus && inputFocus.indicator, inputFocus ? `outline ${inputFocus.outline}; box-shadow ${inputFocus.boxShadow}` : "n/a"));
    let trapped = opened, leaks = [], noRing = [];
    for (let i = 0; opened && i < 14; i++) {
      await pg.keyboard.press("Tab");
      const f = await focusInfo(pg);
      if (f.body || !f.inDialog) { trapped = false; leaks.push(f.body ? "body" : describe(f)); }
      else if (!f.indicator) noRing.push(describe(f));
    }
    add("palette keeps Tab focus inside while open", verdict(trapped, leaks.length ? `escaped to ${leaks.slice(0, 3).join(" | ")}` : "14 Tabs stayed inside the dialog"));
    add("palette controls show a focus indicator", verdict(opened && noRing.length === 0, noRing.slice(0, 5).join(" | ") || "every control reached inside the dialog has one"));
    await pg.keyboard.press("Escape");
    await pg.waitForTimeout(200);
    const closed = await dialog.isVisible().then((v) => !v).catch(() => true);
    const back = await focusInfo(pg);
    add("Escape closes the palette and returns focus to the trigger", verdict(closed && back.href && back.href.endsWith("/analytics/ask/"), `closed ${closed}; focus on ${back.body ? "body" : describe(back)}`));

    // 5. Ctrl+K and Meta+K open it; the Search button opens it and gets focus back.
    for (const combo of ["Control+k", "Meta+k"]) {
      await pg.keyboard.press(combo);
      let ok = true;
      try { await dialog.waitFor({ state: "visible", timeout: 4000 }); } catch { ok = false; }
      await pg.keyboard.press("Escape");
      await pg.waitForTimeout(150);
      add(`palette opens on ${combo} and closes on Escape`, verdict(ok && !(await dialog.isVisible()), ok ? "opened and closed" : "did not open"));
    }
    await pg.focus('button[aria-label^="Search the site"]');
    await pg.keyboard.press("Enter");
    let viaButton = true;
    try { await dialog.waitFor({ state: "visible", timeout: 4000 }); } catch { viaButton = false; }
    await pg.keyboard.press("Escape");
    await pg.waitForTimeout(200);
    const afterButton = await focusInfo(pg);
    add("Search button opens the palette and gets focus back on Escape", verdict(viaButton && /^Search the site/.test(afterButton.name || ""), `opened ${viaButton}; focus on ${afterButton.body ? "body" : describe(afterButton)}`));
    // 6. The Help guide (site pages only): opens from its button, Escape hands focus back.
    const help = pg.locator('button[aria-label^="Open the how-to-read-this guide"]');
    if (await help.count()) {
      await help.focus();
      await pg.keyboard.press("Enter");
      const guide = pg.locator("[role=dialog]").last();
      let shown = true;
      try { await guide.waitFor({ state: "visible", timeout: 6000 }); } catch { shown = false; }
      const inGuide = shown && await pg.evaluate(() => !!document.activeElement.closest("[role=dialog]"));
      await pg.keyboard.press("Escape");
      await pg.waitForTimeout(250);
      const afterGuide = await focusInfo(pg);
      add("Help guide opens on Enter, holds focus, Escape returns focus to the Help button", verdict(shown && inGuide && /^Open the how-to-read-this guide/.test(afterGuide.name || ""),
        `opened ${shown}; focus inside ${inGuide}; after Escape focus on ${afterGuide.body ? "body" : describe(afterGuide)}`));
    }
  } finally {
    await ctx.close();
  }

  // 7. Narrow screen: the disclosure menu from the keyboard.
  const narrow = await openPage(browser, base + page, 375);
  try {
    const p = narrow.pg;
    await p.focus('button[aria-controls="site-menu"]');
    await p.keyboard.press("Enter");
    const expanded = await p.evaluate(() => document.activeElement.getAttribute("aria-expanded"));
    const menuShown = await p.locator("#site-menu").isVisible();
    await p.keyboard.press("Tab");
    const inside = await focusInfo(p);
    await p.keyboard.press("Escape");
    await p.waitForTimeout(100);
    const after = await p.evaluate(() => ({ expanded: document.activeElement.getAttribute("aria-expanded"), menu: !!document.getElementById("site-menu"), name: document.activeElement.textContent }));
    add("mobile menu opens on Enter, Tab enters it, Escape closes and returns focus", verdict(expanded === "true" && menuShown && inside.indicator && !inside.body && after.expanded === "false" && !after.menu && after.name === "Menu",
      `aria-expanded ${expanded}; menu visible ${menuShown}; first item ${inside.body ? "body" : describe(inside)} (indicator ${inside.indicator}); after Escape: menu ${after.menu}, focus "${after.name}"`));
  } finally {
    await narrow.ctx.close();
  }
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop());
if (isMain) {
  const outDir = process.argv[2] || "out";
  const config = JSON.parse(readFileSync(process.argv[3] || "perf/keyboard-pages.json", "utf8"));
  const manifest = readManifest();
  const pages = config.pages.map((entry) => resolvePage(entry, manifest)).filter(Boolean);
  const server = createServer(outDir, config.basePath);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}${config.basePath}`;
  const rows = [];
  const browser = await launchChrome("keyboard-walk");
  try {
    for (const page of pages) await walkPage(browser, base, page, rows);
  } finally {
    await browser.close();
    server.close();
  }
  console.log(formatRows(rows));
  const fails = rows.filter((r) => r.result === "FAIL");
  console.log("\n```json\n" + JSON.stringify({ pages, rows }) + "\n```");
  if (fails.length) { console.error(`\nkeyboard-walk: ${fails.length} FAIL row(s) on ${pages.length} pages`); process.exit(1); }
  console.log(`\nkeyboard-walk GREEN: ${rows.length} checks passed on ${pages.length} pages.`);
}
