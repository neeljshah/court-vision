# Deploy to Railway — make the dashboard truly always-on

End state: a permanent URL like `https://courtvision-live.railway.app`
that updates 24/7 without your laptop being on. About **10 minutes** of
clicks the first time, then `git push` for every update.

Railway gives you ~$5/mo of free execution credit, plenty for one
always-on Python process.

---

## Prerequisites (one-time, on your laptop)

1. The nba-ai-system repo lives on GitHub (any visibility, private is fine).
   If it isn't there yet:
   ```bash
   cd C:\Users\neelj\nba-ai-system
   git init && git add . && git commit -m "init"
   gh repo create courtvision-live --private --source=. --push
   ```

2. A free Railway account: <https://railway.app/login> → sign up with GitHub.

---

## One-click deploy

1. Open <https://railway.app/new>.
2. **Deploy from GitHub repo** → pick `courtvision-live` (or whatever you
   named it).
3. Railway autodetects Python via `nixpacks.toml` and runs the install
   command (`pip install -r requirements-web.txt`). First build takes
   ~3 minutes. Watch the **Deployments** tab — when it goes green, the
   service is live.

4. **Settings → Networking → Generate Domain** to get a public URL
   (e.g. `https://courtvision-live-production.up.railway.app`).

5. **Settings → Variables** — paste these in:

   ```
   LIVE_V2_GAME_IDS=0042500315
   LIVE_V2_PBP_INTERVAL=15
   LIVE_V2_SNAPSHOT_INTERVAL=30
   LIVE_V2_ALLOWED_ORIGINS=*
   LIVE_V2_AUTH_TOKEN=<paste a random 32-char string here>
   ```

   For the token, run this locally and paste the output:
   ```powershell
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

   Without `LIVE_V2_AUTH_TOKEN` the dashboard is open to anyone with
   the URL. With it, you append `?token=<your-token>` and only you
   can load the page.

6. **Save** — Railway redeploys with the new env vars (~30 sec).

7. Open the URL. You should see the pregame card + EV+ bets within a
   few seconds.

---

## Updating tonight's game ID

Every game day you want to point at a different `LIVE_V2_GAME_IDS`:

- Open Railway → your service → **Variables** → edit `LIVE_V2_GAME_IDS`
  to today's game ID → Save → Railway redeploys.
- Find today's game ID from `scripts/discover_game_ids.py` or
  cdn.nba.com's `todaysScoreboard_00.json`.

You can put **multiple game IDs comma-separated**:
```
LIVE_V2_GAME_IDS=0042500315,0042500316
```

---

## Pushing code updates

Standard git flow:
```bash
git add . && git commit -m "tweak" && git push
```

Railway auto-redeploys on every push to the default branch.

---

## What's running in the cloud

One Python process (`uvicorn api.live_v2_app:app`) doing:

| Subtask | Cadence | What it does |
|---|---|---|
| `pregame_probe` | 30s | hits cdn.nba.com scoreboard for matchup + tipoff |
| `box_snapshot_poller` | 30s | hits cdn.nba.com boxscore (silent 403 until tipoff) |
| `pbp_poller` | 15s | hits nba_api PlayByPlayV3 for events |
| `lineup_tracker` | 30s | hits nba_api BoxScoreMatchupsV3 for defenders |
| `parallel_scraper` | 30s | scrapes Pin/Bov/FD/PP for current lines |
| `pregame_ev_loop` | 60s | recomputes Pinnacle-devig EV+ across books |
| `reactive_projector` | event-driven | reprojects player on each PBP foul/sub |
| `decision_engine` | event-driven | re-ranks bets on every projection/line change |
| WebSocket server | always on | broadcasts every event to connected browsers |

Everything happens in one process so the event bus has zero IPC overhead.

---

## Monitoring

- Railway dashboard → **Metrics** → CPU, memory, network. You should see
  ~50-150 MB RAM, ~1-5% CPU at idle.
- Visit `https://<your-url>/api/health` for a JSON snapshot — counts WS
  clients + recent bets + whether the orchestrator is running.
- All logs are in Railway → **Deployments** → click your deployment →
  **Logs**.

---

## Cost expectations

- **Light usage** (≤3 people viewing, polling 1 game): ~$2-4/mo, fits in
  free credit.
- **Heavy usage** (10+ viewers, 3 games at once, dense line scraping):
  Railway hobby plan is $5/mo and gives you 8 GB RAM + always-on.
- Idle in offseason (no game IDs configured): ~$1/mo just for the
  always-on container.

---

## Fly.io alternative

If you prefer Fly.io (also free with a credit card on file):

```bash
fly launch --no-deploy --name courtvision-live
fly secrets set LIVE_V2_GAME_IDS=0042500315 \
                LIVE_V2_AUTH_TOKEN=<random> \
                LIVE_V2_ALLOWED_ORIGINS='*'
fly deploy
```

The `fly.toml` in the repo is preconfigured to keep one machine warm so
WebSockets don't drop on cold start.

---

## Troubleshooting

**Deploy fails on `pip install`**
The default Railway Python is 3.10. If a wheel is missing, try
pinning the version in `requirements-web.txt`. The leanest set that
should always build:

```
fastapi uvicorn[standard] websockets aiohttp requests numpy pandas scipy nba_api rich
```
(Skip lightgbm/xgboost — they're only used by the in-play projection
model, not the pregame line shop.)

**Dashboard shows "reconnecting..."**
Browser devtools → Network → check the `/ws/live` request. Common causes:
- token mismatch (close code 4401) — make sure `?token=` matches
  `LIVE_V2_AUTH_TOKEN`
- Railway free tier sleeping the container — set
  `RAILWAY_HEALTHCHECK_TIMEOUT_SEC=300` and add `min_instances=1` in
  Settings → Scaling.

**No pregame bets appear**
The pregame EV scanner needs at least Pinnacle data on disk. If the
parallel scraper hasn't run yet (first 60s after deploy) the panel will
be empty. Check `https://<your-url>/api/state` — `recent_bets` should be
non-empty within a minute or two.

**Game tips and dashboard still shows PREGAME**
The dashboard auto-flips when `snapshot.updated` arrives with
`game_status="LIVE"`. If it doesn't:
- Verify `LIVE_V2_GAME_IDS` is the correct ID for tonight (the daemon
  registry's IDs go stale across nights).
- Hit `https://<your-url>/api/health` — `active_games` should list the
  game ID once the first live snapshot lands.

---

## File map (everything Railway needs)

| Path | Purpose |
|---|---|
| `api/live_v2_app.py` | FastAPI app — entry point |
| `api/static/dashboard.html` | self-contained dashboard UI |
| `src/live/*.py` | event bus, pregame probe, EV engine, explainer |
| `scripts/live_orchestrator.py` | spawns all the pollers |
| `scripts/pbp_poller.py`, `lineup_tracker.py`, `box_snapshot_poller.py`, `parallel_scraper.py` | pollers |
| `scripts/nba_api_v3_patch.py` | v3 endpoint wrappers with retry+rate-limit |
| `scripts/live_game_poll.py`, `save_live_predictions.py` | legacy live-game helpers reused by the box snapshot poller |
| `src/data/nba_api_headers_patch.py` | browser-style headers for stats.nba.com |
| `src/data/live*.py`, `live_matchup_seeder.py` | live snapshot loaders |
| `src/prediction/live_engine.py` + residual models | in-play projection pipeline |
| `data/models/*.lgb`, `*.pkl` | required at runtime by live_engine residual heads |
| `requirements-web.txt` | lean Python deps |
| `nixpacks.toml`, `railway.json` | Railway build + run config |
| `Procfile`, `fly.toml`, `Dockerfile.live_v2` | alternatives |

---

## What's NOT in the deployed image

To keep build time + image size down, the cloud deploy intentionally
skips:

- `data/tracking/*` (multi-GB CV outputs)
- `vault/` (your local Obsidian vault — local only)
- `_archive/`, `legacy/` (historical code)
- `tests/`, `webapp/` (only needed for dev)
- `torch`, `cv2`, `easyocr` (CV pipeline; not needed for in-play projection)

If you want to slim further, add a `.dockerignore`:

```
data/tracking
data/cache/news
data/cache/synergy
vault
_archive
legacy
tests
webapp
*.pyc
__pycache__
```
