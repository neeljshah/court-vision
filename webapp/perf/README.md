# webapp/perf -- performance and accessibility floor

This directory holds the measured baseline, the after-table for the same method, and the
two configuration files the `webapp QA` workflow enforces on every push and pull request
that touches `webapp/**`.

| File | What it is |
|---|---|
| `BASELINE_2026-10-20.md` | Lighthouse (mobile + desktop), axe-core (both themes) and static byte accounting for ten representative pages, measured before any change. |
| `AFTER_2026-10-20.md` | The same measurement after the fixes on the `perf/webapp-baseline-2026-10-20` branch, with the before/after deltas. |
| `budget.json` | Per-page gzip ceilings for JS, CSS and HTML plus image size caps. Read by `scripts/perf-budget.mjs`. |
| `a11y-pages.json` | The pages `scripts/a11y-gate.mjs` runs axe-core on (both themes). |
| `keyboard-pages.json` | The shell pages `scripts/keyboard-walk.mjs` and `scripts/third-party-requests.mjs` drive (home, desk, paper record, calibration, one finding, one paper fill). |

## The gate (what fails the workflow)

Both steps run after the static export in `.github/workflows/webapp-qa.yml` and are hard
gates like the typecheck and the honesty grep:

1. **`node scripts/perf-budget.mjs out perf/budget.json`** -- no browser. For each page in
   `budget.json` it parses the exported `index.html`, sums the gzip bytes of the module
   `<script src>` chunks (the `noModule` polyfill is never fetched by a modern browser) and the
   stylesheet `<link>`s, gzips the HTML, and fails when any of the three exceeds the page's
   ceiling. It also walks `public/img/showcase` and `public/brand` and fails on any image over
   its cap, so a re-staged chart or icon cannot ship unoptimised again.
2. **`node scripts/a11y-gate.mjs out perf/a11y-pages.json`** -- serves the export the way GitHub
   Pages does (`scripts/serve-export.mjs`), loads every listed page in the dark and the light
   theme with the runner's Chrome (via `playwright-core`, no browser download), runs axe-core
   with the WCAG 2.0/2.1/2.2 A+AA and best-practice rule sets, and fails on any **serious or
   critical** violation. Moderate and minor findings print as workflow warnings.

Unit tests for both scripts: `node --test scripts/perf-budget.test.mjs scripts/a11y-gate.test.mjs`.

## The reports (what the workflow uploads but never fails on)

Three more scripts run after the export as non-blocking report steps, each with an artifact
and a copy in the run summary:

1. **`node scripts/crawl-export.mjs out /court-vision`** (artifact `crawl-report`) -- no browser.
   Walks every exported HTML file, pulls every `href` / `src` (and a redirect stub's meta refresh
   url), resolves each one the way GitHub Pages serves the project site (basePath, one
   percent-decode, a directory's `index.html`) and reports, per page family and as the top
   offending (page, href) pairs: internal targets missing from `out/` (a 404 on Pages), links that
   land on a retired-route stub (with the final target from `lib/redirects.ts`), internal links
   without the trailing slash (a redirect hop), anchors whose id is absent on the target page, and
   the external hosts referenced. It exits non-zero only for missing internal targets. Unit test:
   `node --test scripts/crawl-export.test.mjs`.
2. **`node scripts/keyboard-walk.mjs out perf/keyboard-pages.json`** (artifact `browser-qa-report`)
   -- Chrome via `playwright-core`. Tabs from the top of each page: the skip link must be the first
   stop and land on `#main-content`; every Tab stop must show a computed outline or box-shadow and
   be on screen; the theme toggle and the narrow-screen menu must work from the keyboard; the
   command palette must open on `/` and Ctrl/Cmd+K, keep focus inside, close on Escape and hand
   focus back to its trigger; the desk tabs must be reached in order. PASS/FAIL rows per page.
3. **`node scripts/third-party-requests.mjs out perf/keyboard-pages.json`** (same artifact) --
   loads the same pages, opens the palette and flips the theme, and records every request host
   other than the site's own origin plus any cookie set. This is the receipt behind the footer line
   "No analytics, no cookies, no third-party requests": fonts are self-hosted by `next/font` at
   build time, so the expected inventory is empty. It exits non-zero when a third-party host or a
   cookie appears, which is the signal to change the footer line rather than the script.

Locally all three take `A11Y_CHROME=/path/to/chrome` like the a11y gate.

## How the ceilings were chosen

Each JS/CSS/HTML ceiling is the after-measurement for that page rounded up by roughly 10%:
large enough that a routine copy or data change never trips it, small enough that
re-importing a chart library on a page that lost it (the recharts chunk alone is 106 KB gzip),
passing a full data set to a client component again (the papers index was 192 KB of HTML
before), or adding a second font family (each face is 10-66 KB) fails immediately.

The image caps are the largest optimised file in each directory plus headroom: the showcase
charts quantise to a 256-colour palette at 20-45 KB each (visually lossless for matplotlib
output; measured mean error under 2/255), and the brand icons and social cards sit at 2-70 KB
(cap 77,824 B = `courtvision-emblem-hero.webp` + 10%, no exemptions).

### Brand image cleanup (2026-10-21)

None of the eight oversized `public/brand` files was rendered by any page, manifest or document,
so they were removed from the served tree instead of re-encoded, and the brand cap dropped from
81,920 B with eight exemptions to 77,824 B with none.

| file (`public/brand/`) | before (B) | after (B) | action |
|---|---:|---:|---|
| `courtvision-logo.png` | 1,923,171 | 0 | moved to `scripts/platformkit/analytics_showcase/assets/` (generator source; bytes unchanged, no longer served) |
| `courtvision-research-fields.webp` | 1,628,150 | 0 | deleted (unreferenced) |
| `courtvision-logo-transparent.png` | 1,350,688 | 0 | deleted (unreferenced) |
| `logo-on-light.png` | 961,034 | 0 | deleted (unreferenced generator press composite; now a local export under `out/brand/`) |
| `logo-on-dark.png` | 960,630 | 0 | deleted (same) |
| `courtvision-emblem.webp` | 924,822 | 0 | deleted (unreferenced; the export verifier's 1254x1254 pin was removed with it) |
| `logo-square-dark.png` | 706,092 | 0 | deleted (same as logo-on-*) |
| `logo-square-light.png` | 701,291 | 0 | deleted (same as logo-on-*) |
| **total** | **9,155,878** | **0** | **9,155,878 B (8.73 MiB) removed from the served tree** |

Not changed: the `og-*.png` cards (1200x630, 50-62 KB each, all under 150 KB) and
`courtvision-emblem-hero.webp` (640x640, 70,062 B), which is now the largest brand file.

To raise a ceiling, change `budget.json` in the same pull request as the code that needs it and
say in this file what the extra bytes buy.

Raised ceilings:

- 2026-10-21, `/paper-trading/` HTML 10 KB -> 17 KB (measured 15354 gzip bytes + 2 KB headroom). The page
  now server-renders the five baked paper feeds (`public/demo-data/api_paper_*.json`) instead of fetching
  them after hydration, so the exported HTML carries the ledger as-of date, the 29 fills and the settled
  count on first paint rather than "loading" and "not stated". The extra bytes are the 29-fill trail,
  present once as the rendered rows and once as the client page's props; JS and CSS are unchanged.

## Re-measuring locally

```
cd webapp && npm ci
NEXT_PUBLIC_DATA_MODE=snapshot NEXT_PUBLIC_BASE_PATH=/court-vision npm run build
node scripts/perf-budget.mjs out perf/budget.json
A11Y_CHROME=/path/to/chrome node scripts/a11y-gate.mjs out perf/a11y-pages.json
node scripts/serve-export.mjs out 4173   # then point Lighthouse at http://127.0.0.1:4173/court-vision/
```

## Re-measuring (after a shell restructure)

`budget.json` and `a11y-pages.json` go stale when the shell changes. The `webapp QA` workflow
runs two non-blocking report steps after the build, so no local build is needed:

1. Push (or run **workflow_dispatch** on) the branch; open the run in the Actions tab.
2. The run summary already shows both Markdown tables. For the raw numbers, download the
   `perf-report` artifact (`perf-report.md` + `perf-report.json`: gzip bytes of HTML / JS / CSS
   per page, plus the largest images) and the `a11y-report` artifact (`a11y-report.md` +
   `a11y-report.json`: critical / serious / moderate / minor counts per page per theme and the
   violation list). Artifacts expire after 7 days. If the a11y report says "skipped", the runner
   had no Chrome; set `A11Y_CHROME` and re-run.
3. Set `budget.json`: for every page, `jsGz` / `cssGz` / `htmlGz` = measured gzip bytes + 10%,
   with at least 2 KB (2048 bytes) of headroom, rounded up to the KB. Image caps = the largest
   optimised image in each directory plus headroom. Drop pages that report "not exported" or fix
   their entry.
4. Set `a11y-pages.json` to the pages you want gated. Fix or consciously accept every serious or
   critical row first; the gate fails on any of those.
5. Uncomment the two gate steps in `.github/workflows/webapp-qa.yml` in the same pull request,
   and note here what the final numbers were.

Locally: `node scripts/perf-budget.mjs out perf/budget.json --report` and
`node scripts/a11y-gate.mjs out perf/a11y-pages.json --report` print the same output.
