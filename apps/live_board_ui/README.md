# Live Board UI

A calibrated multi-sport (MLB / Soccer / Tennis) live decision-support board. This is a
React + TypeScript + Vite single-page app that consumes the FastAPI `/api/board` contract and
renders one sortable, virtualized table of games with win probabilities, scores, live clocks,
and a provenance badge per row. It is decision support, NOT a money machine: probabilities come
from a calibrated model where the matchup is in-corpus, and fall back to devigged
market-implied numbers otherwise. No dollar edge, ROI, or value is claimed anywhere in the UI.

## Quickstart

Prerequisites: Node 18+ (and npm).

```sh
npm install
```

Run the FastAPI board on port 8090 (owned by another session; see `apps/live_board/server.py`),
then start the SPA:

```sh
npm run dev
```

Vite serves on `http://127.0.0.1:5174` and proxies `/api` -> `http://127.0.0.1:8090`, so the SPA
talks to the same `/api/board` contract with no CORS juggling. Point it at a different backend
with the `BOARD_API` env var:

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
                          #   Sport, RowSource, SOCCER_LEAGUES, SPORTS.
                          #   Mirrors the FastAPI response; the backend owns it.
  lib/                    # pure helpers: format (winnerSide, sortRows, pct),
                          #   utils (cn class-merge), etc. -- no React, unit-tested.
  hooks/useBoard.ts       # polls /api/board for the selected sport/leagues,
                          #   exposes rows + loading/error + generated_at.
  components/ui/          # primitives (button, tabs, tooltip, badge, ...).
  components/board/        # cells (win prob, score, clock, source badge) +
                          #   the virtualized BoardTable.
  App.tsx                 # sport tabs, soccer league picker, board shell.
```

The contract lives in `src/types/board.ts` and is the single source of truth for the row shape;
field names match the FastAPI server and this app never mutates the contract.

Virtualization: `BoardTable` uses `@tanstack/react-virtual` so a full tennis slate (300+ rows)
stays smooth -- only visible rows are mounted while scroll position and sort order are preserved.

Provenance (the source badge): every row carries a `source` of `model`, `live-model`, `market`,
`live-market`, or `unavailable`, plus a `market_implied` flag and an optional `provider`. The
badge makes the origin of each probability explicit -- calibrated model (in-corpus) vs devigged
market-implied vs score/clock only -- so the number is never presented as more than it is.

## Honesty (binding)

- No `$` edge, ROI, value, +EV, profit, or "beat the market" language anywhere in the UI or copy.
- Provenance stays truthful: model where in-corpus, market-implied otherwise, `unavailable`
  when there is neither. The source badge always reflects the real origin.
- This is decision support, not a betting recommendation engine.
- Source and copy are ASCII-only; use `->` and `"` rather than typographic glyphs.
