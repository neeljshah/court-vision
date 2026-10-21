# Visual QA, 2026-10-20 (unified shell)

Screenshots of the static export (`NEXT_PUBLIC_DATA_MODE=snapshot npm run build`, served by
`node scripts/serve-export.mjs out 4173`) taken with playwright-core and the bundled Chromium
at 375, 768 and 1280 px in both themes (`localStorage.cv-theme`), 17 pages: `/`, `/about/`,
`/desk/`, `/desk/health/`, `/paper-trading/`, `/games/`, `/how-it-works/`, `/methodology/`,
`/evidence/retractions/`, `/analytics/calibration/`, `/analytics/findings/`,
`/analytics/findings/shrinkage/`, `/analytics/papers/`, `/analytics/players/`,
`/analytics/players/nba_players/alperen_sengun/`, `/analytics/lab/` and the first `/paper/<fill>/`
linked from `/paper-trading/`. Every capture also ran a DOM audit: page scrollWidth vs viewport,
tables outside an `overflow-x: auto` ancestor, tap targets under 24 px, text under 11 px,
`overflow: hidden` clipping, stretched images, header row height, overlapping text rects.

`before/` is the export at master `4347505`, `after/` the same regions after the fixes below.
Each file is `<region>--<width>-<theme>.jpg`, under 150 KB.

## Findings

| page | width | theme | issue | element | after |
|---|---|---|---|---|---|
| / | 375 | both | In-game scoreboard table squeezed to one character per line (every header and number) | `HomeScoreboard` table | fixed: `whitespace-nowrap` on the table; it scrolls inside its wrapper |
| / | 768 | both | Scoreboard headers break mid-word ("SPO RT", "CHECKP OINT") | same | fixed |
| / | 1280 | both | "1593" and "+0.0040" split across two lines in the n and delta columns | same | fixed |
| / | all | both | Byline links (email, GitHub, Portfolio) 16 px tall; "night receipts" 14 px; "retraction record" 17 px | `HomeByline`, `HomeForwardStatus`, `HomeNotClaimed` links | fixed: 24 px hit boxes |
| /desk/, /desk/health/ | all | both | Desk sub-nav chips 22 px tall | `DeskShell` nav links | fixed: `min-h-6` |
| /desk/, /desk/health/ | 375 | both | Table headers wrap mid-word in the narrow columns | `DeskShell` `T`, `ScoreboardCompact` thead | fixed: `whitespace-nowrap` on header rows |
| /paper-trading/ | 375, 768 | both | Settled book and open positions tables clipped at the right; the Radix ScrollArea had only a vertical bar, so its viewport was `overflow-x: hidden` | `ScrollArea` > `table.min-w-full` | fixed: horizontal `ScrollBar` mounted in `components/ui/scroll-area.tsx` |
| /how-it-works/ | 375 | both | Page scrolls horizontally (407 > 375 px): the panel head's right group (as-of stamp + receipt) never wraps | `PanelHead` in `components/ui/terminal.tsx` | fixed: `flex-wrap` + `min-w-0` |
| /how-it-works/ | 375 | both | Market surface / verdict table headers wrap mid-word | `MarketSurfaceTable`, `HonestFindings` thead | fixed: `whitespace-nowrap` on header rows |
| /analytics/calibration/ | 375, 768 | both | "Show as table" histogram table (760 px) sits in the clipped `main` with no scroll container; columns past the second are unreachable | `figure.cal-hist details table` | fixed: wrapped in `.calibration-table-wrap` (scroll region, focusable) |
| /analytics/calibration/ | all | both | Receipt "R" glyph renders unstyled (14 x 19 px, pressed against the date): its Tailwind classes never load in the analytics group | `components/showcase/ReceiptChip.tsx` Glyph (29 per view) | fixed: `.cv-receipt-glyph` rule in `analytics.css` |
| /paper-trading/, /analytics/findings/shrinkage/ | all | both | Receipt chip link 21 px tall | `a.ev-chip` | fixed: 24 px via padding in `evidence.css` |
| /paper/<fill>/ | all | both | "back to PM trail" link 14 px tall | `BetDetailPageClient` link | fixed: `min-h-6` |
| /games/ | all | both | Sport tab strip is `sticky top-0` under the sticky site header, so it disappears behind the header once the page scrolls | `SlateCards` nav | fixed: `top-14` (header height) |
| /analytics/lab/ | all | both | Dataset catalog row counts and rank sub-labels at 8 px | `.lab-nav-group>button small`, `.lab-rank-label small` | fixed: 10 px |

Noted, not changed (by design or outside a layout fix):

- `/games/` 375: the sport tab strip scrolls sideways (last tab cut at the edge); card titles truncate with an ellipsis (`truncate`).
- `/desk/` 375: the per-arm cell table inside the scoreboard scrolls within the outer table scroller.
- `/evidence/retractions/` 375: the 720 px table scrolls inside its wrapper, as intended.
- 10 px microlabels, trust pills and `cv-badge` (9 px) are the design's smallest meta sizes; left alone.
- `/paper/<fill>/`: the breadcrumb shows the percent-encoded fill id (label content, not layout).
- The DOM audit's "overlapping text" hits were the fixed Help button over a full-page capture and multi-line inline spans; none reproduced visually.
- Header, mobile menu, breadcrumbs and footer: no wrapping or contrast problems at any width in either theme.

## CSS and class changes

- `components/ui/scroll-area.tsx`: mount `<ScrollBar orientation="horizontal" />` (Radix enables `overflow-x: scroll` only then).
- `components/ui/terminal.tsx` `PanelHead`: `flex-wrap gap-y-1` on the row, `min-w-0 flex-wrap` on the right group.
- `components/home/HomeScoreboard.tsx`: `whitespace-nowrap` on the table, `whitespace-normal` on the small-sample note.
- `components/home/HomeByline.tsx`: `items-center` on the row, `inline-flex min-h-6 items-center` on the links.
- `components/home/HomeForwardStatus.tsx`: `py-[5px]` on the night receipts link; `components/home/HomeNotClaimed.tsx`: `py-1` on the retraction record link.
- `components/desk/DeskShell.tsx`: `whitespace-nowrap` on the `T` header row; `inline-flex min-h-6 items-center` on the sub-nav links.
- `components/desk/ScoreboardCompact.tsx`, `components/explain/HonestFindings.tsx`, `components/depth/MarketSurfaceTable.tsx`: `whitespace-nowrap` on the header row.
- `components/analytics/calibration/CalibrationDecomposition.tsx`: the details table gets the existing `.calibration-table-wrap` scroll region.
- `components/showcase/ReceiptChip.tsx`: Glyph carries `cv-receipt-glyph`; `app/(analytics)/analytics.css` styles it (24 px box, rule border, mono 10 px).
- `components/evidence/evidence.css`: `.ev-chip` padding 3px (24 px tall).
- `app/(terminal)/paper/[betId]/BetDetailPageClient.tsx`: back link `inline-flex min-h-6 items-center`.
- `app/(terminal)/games/SlateCards.tsx`: sport nav `sticky top-14`.
- `app/(analytics)/analytics/lab/lab.css`: the two 8 px `small` rules become 10 px.

No copy changed. Gates after the change: axe 0 serious/critical on the 10 gate pages x 2 themes,
perf budget green, typecheck clean, lint unchanged (pre-existing warnings only).

## Reproduce

```
cd webapp && npm ci
NEXT_PUBLIC_DATA_MODE=snapshot NEXT_PUBLIC_BASE_PATH=/court-vision npm run build
node scripts/serve-export.mjs out 4173 &
A11Y_CHROME=/opt/pw-browsers/chromium node scripts/a11y-gate.mjs out perf/a11y-pages.json
node scripts/perf-budget.mjs out perf/budget.json
```
