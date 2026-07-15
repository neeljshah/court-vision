# webapp -- the P5/P6 dashboard UI (:3000)

Next.js app served by the supervised stack (`go.ps1` -> supervisor `m1_ui`).
Read-only over the predict-service Auto-API (:8099) and boards API (:8098).
Paper/units only -- no $ fields, no edge claims anywhere in the UI.

## Production build only (the .next gotcha)

`go.ps1` sets `NBA_AI_UI_CMD=npm run start`, so the stack serves the
**production build** in `webapp/.next/`, NOT the dev server. The dev server's
incremental compile was corrupting under load (unstyled pages), which is why
prod-serve is the default.

Consequences:

- A production build must exist. First clone or missing `.next/`:

      cd webapp
      npm install     # first time only
      npm run build   # compiles to webapp/.next/

- **Every front-end change requires `npm run build`** before it appears on
  :3000. Editing a component and restarting the stack is NOT enough -- the old
  compiled assets in `.next/` keep serving.
- If :3000 serves stale or unstyled pages after a build, delete `.next/` and
  rebuild (`rm -rf .next && npm run build`) -- a partially-written `.next/cache`
  can poison subsequent incremental builds.
- Backend changes (predict_service/, scripts/platformkit/) do NOT need a
  front-end rebuild.

Dev server (hot reload) when you want it:

    $env:NBA_AI_UI_CMD = "npm run dev"
    .\go.ps1

## Layout

- `app/p6/` -- the main dashboard route (slate, CLV, ratchet, live lines,
  props panel, in-game, ops, self-improve panels).
- `app/system/`, `app/records/`, `app/paper-trading/`, `app/bets/`, `app/paper/`,
  `app/live/`, `app/games/`, `app/progress/`, `app/risk/`, `app/today/`,
  `app/models/`, `app/how-it-works/` -- dedicated views (13 top-level routes
  total including `app/p6/`).
- `components/p6/PropsPanel.tsx` -- player props (mlb + soccer_intl), reads
  `GET :8099/api/predict/props/{sport}` (route-collision fix + scraped-book
  bridge shipped 2026-07-02, commits 460fd0cb + 9bc820d4).
- `lib/p5api.ts`, `lib/types_w12.ts` -- API client + response shapes.

Tests: `cd webapp && npx vitest run <file>` (per-file only, same rule as pytest).
