# Live Board UI

A calibrated multi-sport (MLB / Soccer / Tennis) live decision-support board. This is a
React 18 + TypeScript + Vite single-page app that consumes the FastAPI `/api/board` contract and
renders one virtualized table of games with win probabilities, scores, live clocks, and a
provenance badge per row. It is decision support, NOT a money machine: a row's win probability
comes from a calibrated model where the matchup is in-corpus, and falls back to a devigged
market-implied number otherwise (score/clock only when neither is available). No dollar edge,
ROI, value, or "beat the market" claim is made anywhere in the UI or this document.

## Features

- Three sport tabs (MLB / Soccer / Tennis) with a soccer league selector; the active sport is
  deep-linkable via `?sport=` so a view can be shared or bookmarked.
- Honest source badges per row -- MODEL, MODEL-LIVE, MARKET, MARKET-LIVE, or SCORE ONLY --
  reflecting the exact origin of the shown numbers, with a legend dialog that explains each.
- Light / dark / system theming: follows `prefers-color-scheme`, persists a manual choice to
  `localStorage`, and live-updates when the OS preference changes while set to "system".
- Virtualized board (`@tanstack/react-virtual`) that stays smooth on a full tennis slate of
  300+ rows -- only visible rows mount while scroll and sort order are preserved.
- Sectioned ordering: Live -> Upcoming -> Finished, with the Finished section collapsed behind
  a toggle when it exceeds 12 rows.
- Per-row cells: status (with a live pulse), matchup (winner check on finished rows), score
  (including tennis set-strings like "6 4 7"), home/away/draw win-probability bars, and the
  source badge.
- Search plus a "Live only" filter, with a "showing N of M" count.
- Dynamic columns: the Odds and Total columns are hidden entirely when no row carries that data.
- Freshness: a relative "updated Xm ago" stamp and an honest "delayed" flag once the payload is
  more than 90s old.
- Polling every 25s that PAUSES while the browser tab is hidden and refreshes immediately on
  return; in-flight requests are cancelled on a sport/league switch (no flicker, no stale swap).
- "How to read this board" legend dialog and a tap-any-game detail dialog showing the full note,
  all available markets, exact start time, and provenance.
- Favicon (SVG) and a PWA web manifest; ~87KB gzip bundle.
- Accessible (semantic list roles, aria labels, keyboard-focusable scroll region) and ASCII-only.
- 149 tests (Vitest + React Testing Library), plus a clean `tsc` typecheck and production build.

## Quickstart

Prerequisites: Node 18+ (and npm).

Run the FastAPI board on port 8090 (owned by the backend; see `apps/live_board/server.py`),
then install and start the SPA:

```sh
npm install
npm run dev
```

Vite serves the SPA and proxies `/api` -> `http://127.0.0.1:8090`, so the app talks to the
`/api/board` contract with no CORS handling. Point it at a different backend with the `BOARD_API`
env var:

```sh
BOARD_API=http://127.0.0.1:9000 npm run dev
```

Other scripts:

```sh
npm run build       # tsc -b && vite build -> dist/
npm run test        # vitest run
npm run typecheck   # tsc -b --noEmit
```

## Architecture

```
src/
  types/board.ts          # CONTRACT source of truth: BoardRow, BoardResponse,
                          #   Sport, GameState, RowSource, SOCCER_LEAGUES, SPORTS.
                          #   Mirrors the FastAPI response; the backend owns it.
  lib/
    api.ts                #   fetchBoard(sport, leagues?, signal) -> BoardResponse
    format.ts             #   pct, fmtTotal, winnerSide, setsWon, sortRows, ...
    filter.ts             #   filterRows(rows, query, liveOnly) -- pure, no sort
    gameKey.ts            #   stable per-game key across polls and re-sorts
    utils.ts              #   cn() class-merge
  hooks/
    useBoard.ts           #   25s polling, visibility-pause, stale flag, abort-on-switch
    useTheme.ts           #   light / dark / system, persisted, OS-change aware
    useScoreFlash.ts      #   flags rows whose score changed since last poll
    useRelativeTime.ts    #   "updated Xm ago" relative stamp
  components/ui/          # primitives: badge, tabs, tooltip, skeleton, dialog
  components/board/       # cells (status, matchup, score, win-prob, odds, source
                          #   badge) + the virtualized BoardTable + LegendDialog +
                          #   GameDetailDialog + StampBar / FilterBar / states
  App.tsx                 # composition: tabs, league picker, filters, board shell
```

The contract lives in `src/types/board.ts` and is the single source of truth for the row shape;
field names match the FastAPI server and this app never mutates the contract.

Provenance (the source badge): every row carries a `source` of `model`, `live-model`, `market`,
`live-market`, or `unavailable`, plus a `market_implied` flag and an optional `provider`. The
badge makes the origin of each number explicit -- calibrated model (in-corpus) vs devigged
market-implied vs score/clock only -- so a probability is never presented as more than it is.

## Honesty (binding)

- Every row is badged by its real source; the badge always reflects where the number came from.
- The honesty disclaimer stays visible (banner plus footer), and the legend explains each badge.
- Model where the matchup is in-corpus, market-implied otherwise, `unavailable` when neither.
- No `$` edge, ROI, value, +EV, profit, or "beat the market" language anywhere in the UI or copy.
- This is decision support, not a betting recommendation engine.
- Source and copy are ASCII-only; use `->` and `"` rather than typographic glyphs.
```
