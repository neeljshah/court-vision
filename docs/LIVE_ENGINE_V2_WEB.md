# Live Engine v2 — web deployment runbook

Companion to `LIVE_ENGINE_V2.md`. Adds a **real-time browser dashboard**
(OddsTrader-style) backed by a WebSocket bridge over the existing event bus.

```
   ┌─────────────────────────┐         ┌──────────────────────────────┐
   │  webapp/  (Next.js 14)  │  WS+ws  │  api/live_v2_app.py (FastAPI)│
   │  Vercel-hosted          │ ──────▶ │  Railway/Fly-hosted          │
   │  Tailwind + Zustand     │  REST   │  in-proc EventBus +          │
   └─────────────────────────┘         │  ExplanationEngine + pollers │
                                       └──────────────────────────────┘
```

Everything runs in one Python process on the backend (orchestrator
+ pollers + decision engine + explanation engine + WS server), and
one Next.js process on the frontend. Vercel hosts the frontend for
free; the backend needs a persistent process so it goes on Railway
(free tier) or Fly.io.

## Quickstart — fully local

Backend (terminal 1):
```
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pip install websockets
$env:LIVE_V2_GAME_IDS = "0042500315"
$env:LIVE_V2_ALLOWED_ORIGINS = "http://localhost:3000"
C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m uvicorn api.live_v2_app:app --host 0.0.0.0 --port 8000 --ws websockets
```

Frontend (terminal 2):
```
cd webapp
npm install
cp .env.local.example .env.local
npm run dev
```

Open http://localhost:3000 — dashboard hydrates from `/api/state`,
then upgrades to a WebSocket and re-renders incrementally as events
fire. Click any bet row to open the "Why this bet" drawer.

## Backend env vars

| Var | Purpose |
|-----|---------|
| `LIVE_V2_GAME_IDS`        | comma-separated game IDs (omit for passive mode — backend stays a pure relay for another process publishing to the bus) |
| `LIVE_V2_AUTH_TOKEN`      | bearer token required for REST + WS. Omit for open local dev. |
| `LIVE_V2_ALLOWED_ORIGINS` | CORS allow list. Set to your Vercel URL in prod. |
| `LIVE_V2_PBP_INTERVAL`    | override PBP poll cadence (default 10s) |
| `LIVE_V2_SNAPSHOT_INTERVAL` | override box-score poll cadence (default 30s) |
| `LIVE_V2_LINEUP_INTERVAL` | override matchup poll cadence (default 30s) |
| `LIVE_V2_LINE_INTERVAL`   | override line scrape cadence (default 30s) |
| `SLACK_ALERT_WEBHOOK` / `DISCORD_ALERT_WEBHOOK` | optional alert sinks |

## API surface

| Path | Method | Purpose |
|------|--------|---------|
| `/api/health` | GET | liveness; reports WS client count + active games |
| `/api/state`  | GET | one-shot snapshot for fresh page loads |
| `/api/bets?limit=20` | GET | recent ranked bets |
| `/api/explain` | POST | builds the "why" payload for one bet |
| `/ws/live`     | WebSocket | all events broadcast in real time |

Every endpoint accepts `?token=...` for auth when `LIVE_V2_AUTH_TOKEN`
is set. The WS handshake reads the same query arg and closes with
code 4401 if it doesn't match.

## WebSocket message envelope

```json
{ "topic": "bet.recommended",
  "event": { ... event payload, same shape as the bus event ... },
  "ts": 1717000000.123 }
```

Topics: `hello` (sent once on connect with full hydration payload),
`pong` (response to client `ping`), `snapshot.updated`,
`projection.updated`, `bet.recommended`, `lines.refreshed`,
`pbp.made_shot`, `pbp.foul`, `pbp.sub`, `pbp.turnover`,
`pbp.timeout`, `pbp.period_end`.

## "Why" engine — what each section shows

The `/api/explain` endpoint returns up to 4 sections per bet:

| `kind` | Source | Example |
|--------|--------|---------|
| `projection_path`  | row.projection_source + foul/blow/heat_check factors + matchup_reason | "endQ2 head → endQ2 residual head → defender matchup — heat_check=0.85x, matchup_applied:Jokic vs AGordon" |
| `pbp_context`      | last 3 PBP events relevant to the player | "Q4 PT05M30 — foul (Jokic); Q4 PT05M10 — made_shot (Jokic)" |
| `line_movement`    | per-book drift in this session + cross-book spread | "pin: 26.5 ↓ 24.5 (-2.0 in 180s); fd: 26.5; spread across books: +2.0 — possible middle window" |
| `foul_pressure`    | snapshot.players[bet.player_id] + projection_source | "Jokic on 4 PF — one away from foul-out; through 30 min, period=4" |

Sections are emitted only when there is real signal — if no PBP
buffer or no line ticks have been ingested yet, those sections are
omitted (rather than empty).

## Deployment — Vercel + Railway

### Backend → Railway (free tier, ~$0-5/mo)

1. Push the repo to GitHub.
2. Sign up at railway.app, "New project" → "Deploy from GitHub".
3. Pick the repo. Railway detects `railway.json` and runs:
   `uvicorn api.live_v2_app:app --host 0.0.0.0 --port $PORT --ws websockets`.
4. Variables tab:
   ```
   LIVE_V2_GAME_IDS=0042500315
   LIVE_V2_AUTH_TOKEN=<openssl rand -hex 32>
   LIVE_V2_ALLOWED_ORIGINS=https://<your-vercel-app>.vercel.app
   ```
5. Note the public URL (e.g. `https://courtvision-live-api.railway.app`).
6. Hit `https://<url>/api/health?token=<token>` to confirm.

### Backend → Fly.io alternative

```
fly launch --no-deploy --name courtvision-live-api
fly secrets set LIVE_V2_AUTH_TOKEN=<token> \
                LIVE_V2_GAME_IDS=0042500315 \
                LIVE_V2_ALLOWED_ORIGINS=https://<your>.vercel.app
fly deploy
```
`fly.toml` is already configured to keep one machine warm (`auto_stop_machines = false`) so WS clients don't drop on cold-start.

### Frontend → Vercel (free)

1. `cd webapp && npx vercel`
2. Add env vars in the Vercel dashboard:
   ```
   NEXT_PUBLIC_API_BASE=https://<your-railway>.railway.app
   NEXT_PUBLIC_WS_BASE=wss://<your-railway>.railway.app
   NEXT_PUBLIC_AUTH_TOKEN=<same-token-as-backend>
   ```
3. `vercel --prod`.

### Local Docker (alternative to cloud)

```
docker build -f Dockerfile.live_v2 -t courtvision-live-v2 .
docker run -p 8000:8000 \
  -e LIVE_V2_GAME_IDS=0042500315 \
  -e LIVE_V2_AUTH_TOKEN=changeme \
  -e LIVE_V2_ALLOWED_ORIGINS=http://localhost:3000 \
  courtvision-live-v2
```

## Auth model

Single shared token via `LIVE_V2_AUTH_TOKEN`. Both the REST endpoints
and the WS handshake check `?token=...` against the env var.

- Local dev: leave the env var unset and the API is fully open.
- Production: generate `openssl rand -hex 32` and paste the same
  value into Vercel (`NEXT_PUBLIC_AUTH_TOKEN`) and Railway/Fly
  (`LIVE_V2_AUTH_TOKEN`). Anyone with the URL but not the token
  gets a 401 / WS close code 4401.

This is intentionally bare-bones — for personal use it's enough.
If you ever share access with others, upgrade to JWT (Clerk, Auth.js,
or NextAuth) and have the API verify the JWT signature.

## Mobile

`/app/page.tsx` uses a 12-column grid that collapses to a single
column below the `lg:` breakpoint. The dashboard is functional on
phone-portrait — bets stack, PBP feed below, alerts in a single
strip. The "Why" drawer fills the whole screen on mobile.

## Cost & limits

- **Vercel free**: 100 GB bandwidth/mo, instant rollback, free SSL.
- **Railway free**: 500 hours/mo execution time (enough to keep one
  process up 24/7) + $5/mo of usage credit.
- **NBA API rate limit**: each backend pod respects the 0.6s rate
  limit via `scripts/nba_api_v3_patch.py`. Don't run two backend
  pods polling the same game IDs — you'll hit 429s.

## Troubleshooting

**Browser says "reconnecting…" forever**
Check the browser devtools network tab for the `/ws/live` connection.
Common causes:
- token mismatch (close code 4401)
- backend CORS rejects the origin (set `LIVE_V2_ALLOWED_ORIGINS`)
- Railway free tier sleeping (set `auto_stop_machines = false` for Fly; for Railway add a non-trivial cron ping)

**"Why" drawer shows "Couldn't load explanation"**
The `/api/explain` POST is failing. Check the Vercel function logs
or `curl -X POST https://<api>/api/explain?token=... -d '{...}'`.
The most common cause is missing CORS — make sure `OPTIONS` requests
return 200 from your backend.

**Top bets pane never populates**
- No game IDs configured on the backend → orchestrator didn't start
- No book lines on disk yet → wait ~30s for the first scrape
- Decision engine `emit_floor_ev` higher than any current edge —
  expected at tip-off when projections are still pregame-anchored

## File map

| Path | Purpose |
|------|---------|
| `api/live_v2_app.py`           | FastAPI WS + REST bridge |
| `src/live/explanation_engine.py` | builds the "why" payload |
| `tests/test_live_v2_app.py`    | backend regression (6 tests) |
| `tests/test_explanation_engine.py` | explanation regression (7 tests) |
| `webapp/`                      | Next.js 14 frontend |
| `webapp/app/page.tsx`          | dashboard root |
| `webapp/lib/ws.ts`             | WS client + reconnect loop |
| `webapp/lib/store.ts`          | Zustand store |
| `webapp/lib/types.ts`          | shared TS types |
| `webapp/components/*.tsx`      | per-pane UI |
| `Procfile`                     | Railway start cmd |
| `fly.toml`                     | Fly.io config |
| `railway.json`                 | Railway config |
| `Dockerfile.live_v2`           | container image |
