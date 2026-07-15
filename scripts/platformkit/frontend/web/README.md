# CourtVision Board -- premium React front end

A premium React + Vite + TypeScript + Tailwind + shadcn/ui front end for the
multi-sport betting decision-support board. It consumes the EXISTING FastAPI JSON
API served by `scripts.platformkit.frontend.serve` (port 8098). It does NOT modify
that service or the legacy `static/index.html` fallback.

HONEST: decision-support only. No auto-execution, no sportsbook connection, no
claimed money edge. Line-shopping / arbitrage are labelled execution edges. You
place every bet yourself.

## Develop

1. Start the API (separate terminal, from the repo root):

   ```
   python -m scripts.platformkit.frontend.serve
   ```

   It listens on `http://127.0.0.1:8098`.

2. Install + run the dev server:

   ```
   cd scripts/platformkit/frontend/web
   npm install
   npm run dev
   ```

   Open the printed URL (default `http://localhost:5174`). The Vite dev server
   proxies `/api` and `/health` to the FastAPI port (8098), so the SPA talks to
   the real predictor with no CORS setup. Override the target with
   `VITE_API_TARGET` if you run serve.py on a different port.

## Build for production

```
cd scripts/platformkit/frontend/web
npm install
npm run build      # type-checks, then emits dist/
npm run preview    # optional: preview the built bundle locally
```

The static bundle lands in `scripts/platformkit/frontend/web/dist/`.

## Serving the built bundle from FastAPI (NOT wired by this scaffold)

`serve.py` is intentionally left untouched as the working fallback. To later serve
the production SPA from the same FastAPI process, mount `dist/` as static files --
for example, adding this to a NEW serve variant (do not edit the existing one
unless you intend to replace the fallback):

```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path

dist = Path(__file__).parent / "web" / "dist"
if dist.exists():
    # API routes (/api, /health) are registered first; mount the SPA at root last
    # with html=True so client-side routing falls back to index.html.
    app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")
```

Build first (`npm run build`) so `dist/` exists, then start FastAPI. The API
routes must be registered BEFORE the catch-all static mount.

## Layout

```
web/
  index.html              # Vite entry
  package.json            # deps + scripts (dev/build/preview/lint)
  vite.config.ts          # @ alias + /api+/health proxy to :8098
  tailwind.config.js      # dark theme tokens
  components.json         # shadcn config (new-york, slate)
  src/
    main.tsx              # React root
    App.tsx               # shell: header + honest banner + controls + tabs
    index.css             # Tailwind + theme CSS variables
    lib/
      api.ts              # typed client + SlateRow/SlatePayload types + SPORTS
      format.ts           # null-safe % / price formatting
      useSlate.ts         # fetch + 30s auto-poll hook
      utils.ts            # cn() helper
    components/
      ui/                 # shadcn primitives: button, card, table, select,
                          #   badge, tabs, input, collapsible, dialog
      board/              # HonestBanner, BoardControls, BoardTable, useSort,
                          #   VerdictBadge, RowActions
      game/               # BestBetCard, BetRowsTable, GameDetail, betFormat
      screens/            # BoardScreen + PlaceholderScreen (arb / +EV / tracker)
```
