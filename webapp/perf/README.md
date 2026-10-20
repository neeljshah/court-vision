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

## How the ceilings were chosen

Each JS/CSS/HTML ceiling is the after-measurement for that page rounded up by roughly 10%:
large enough that a routine copy or data change never trips it, small enough that
re-importing a chart library on a page that lost it (the recharts chunk alone is 106 KB gzip),
passing a full data set to a client component again (the papers index was 192 KB of HTML
before), or adding a second font family (each face is 10-66 KB) fails immediately.

The image caps are the largest optimised file in each directory plus headroom: the showcase
charts quantise to a 256-colour palette at 20-45 KB each (visually lossless for matplotlib
output; measured mean error under 2/255), and the brand icons sit at 2-60 KB.

To raise a ceiling, change `budget.json` in the same pull request as the code that needs it and
say in this file what the extra bytes buy.

## Re-measuring locally

```
cd webapp && npm ci
NEXT_PUBLIC_DATA_MODE=snapshot NEXT_PUBLIC_BASE_PATH=/court-vision npm run build
node scripts/perf-budget.mjs out perf/budget.json
A11Y_CHROME=/path/to/chrome node scripts/a11y-gate.mjs out perf/a11y-pages.json
node scripts/serve-export.mjs out 4173   # then point Lighthouse at http://127.0.0.1:4173/court-vision/
```
