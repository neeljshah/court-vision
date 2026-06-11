# API Reference — CourtVision

> FastAPI backend serving the full prediction, analytics, and dashboard surface.
> For the model layer backing these endpoints see [`docs/ML_MODELS.md`](ML_MODELS.md).
> For system architecture see [`ARCHITECTURE.md`](../ARCHITECTURE.md).

---

## Quick Start

```bash
conda activate basketball_ai
uvicorn api.main:app --reload --port 8000
# Interactive Swagger UI: http://localhost:8000/docs
# ReDoc:                  http://localhost:8000/redoc
```

**Environment:**
- `NBA_OFFLINE=1` (default) — serves stale NBA API cache; prevents stats.nba.com hangs
- `NBA_OFFLINE=0` — enables live NBA API fetches
- `LIVE_V2_AUTH_TOKEN=<token>` — enables auth on risk endpoints (open in local-dev when unset)
- `SENTRY_DSN=<dsn>` — enables Sentry error tracking

**App entry:** `api.main:app` (primary), `api.live_v2_app:app` (cloud/Railway entry with
static assets and Jinja dashboard templates)

---

## Router Map

~99 endpoints across 12 routers, counted at runtime from `app.routes`.

| Router module | Mount prefix | Tags | Purpose |
|---|---|---|---|
| `api/main.py` (inline) | `/` | simulation, props, health | Simulation, props, health |
| `api/models_router.py` | `/predictions` | predictions | xFG, win-prob, player EPA |
| `api/predictions_router.py` | `/predictions` | predictions | Full prop stack, injury, breakout, lineup optimizer |
| `api/analytics_router.py` | `/analytics` | analytics | Shot chart, tracking coords, lineup stats |
| `api/dashboard_router.py` | `/` | dashboard | AI chat, CLV summary, today's edges |
| `api/devig_router.py` | `/` | devig | Shin + 4 de-vig methods |
| `api/clv_router.py` | `/` | clv | CLV dashboard page + data |
| `api/live_game_router.py` | `/` | live | Per-game live projection panel |
| `api/lines_router.py` | `/` | lines | Multi-book line scanner |
| `api/courtvision_router.py` | `/` | courtvision | CourtVision UI (home, game, tonight, parlays) |
| `api/_risk_router.py` | `/` | risk | Kill switch, drawdown, bankroll |
| `api/execution_router.py` | `/` | — | Order execution stubs |

---

## Health

### GET `/health`

Fast liveness check. Always returns 200 if the server is up.

```json
{
  "status": "ok",
  "model_status": {
    "possession_simulator": "loaded",
    "player_props": "available",
    "betting_edge": "loaded",
    "win_probability": "available",
    "tracking": "available",
    "re_id": "available"
  }
}
```

### GET `/health/ops`

Operational pipeline metrics. Reads from `data/models/bet_log.json`,
`data/models/clv_log.json`, `data/models/quarantine_state.json`, and the
`scraper_runs` SQLite table.

```json
{
  "status": "ok",
  "scraper_lag_min": 4.2,
  "model_inference_ms_p95": null,
  "daily_bet_count": 12,
  "clv_hit_rate": 0.543,
  "drift_flags": [],
  "last_slate_duration_min": null,
  "uptime_hours": 3.14
}
```

`scraper_lag_min`: minutes since last successful scrape run (`scraper_runs` table,
`status='done'`). `clv_hit_rate`: fraction of logged bets with positive CLV.
`drift_flags`: model names currently in quarantine.

---

## Simulation

All simulation endpoints use `src/prediction/possession_simulator.py` —
`PossessionSimulator`. Responses are TTL-cached 300s in-process (key = params tuple).

### POST `/simulate`

Monte Carlo game simulation.

**Request:**
```json
{ "team_a": "BOS", "team_b": "MIL", "n_sims": 1000, "player_stats": null }
```

**Response:**
```json
{
  "team_a_win_pct": 0.58,
  "mean_score_a": 112.4,
  "mean_score_b": 108.1,
  "player_distributions": {}
}
```

### POST `/simulate_game`

Full game simulation with optional per-team stat overrides.

**Request:**
```json
{
  "team_a": "BOS",
  "team_b": "MIL",
  "n_sims": 1000,
  "team_a_stats": null,
  "team_b_stats": null
}
```

### POST `/over_prob`

Per-player per-stat over probability from Monte Carlo distribution.

**Request:**
```json
{
  "player_id": "Jayson Tatum",
  "stat": "pts",
  "line": 26.5,
  "team_a": "BOS",
  "team_b": "MIL",
  "roster_a": ["Jayson Tatum", "Jaylen Brown"],
  "roster_b": ["Giannis Antetokounmpo"],
  "n_sims": 1000
}
```

**Response:**
```json
{
  "player_id": "Jayson Tatum",
  "stat": "pts",
  "line": 26.5,
  "over_prob": 0.612,
  "mean": 27.4
}
```

---

## Props

### GET `/props/{player_id}`

7-stat pregame prop projections. Accepts player name or name-based ID string.
Calls `stack_predict()` from `src/prediction/prop_model_stack.py`; falls back to
`predict_props()` from `src/prediction/player_props.py` if the stack returns empty.

**Query params:** `opp_team=GSW` (default), `season=2025-26` (default)

**Response:**
```json
{
  "pts": 27.4,
  "reb": 8.1,
  "ast": 4.8,
  "fg3m": 2.1,
  "stl": 1.1,
  "blk": 0.6,
  "tov": 2.8
}
```

**Honest note:** STL R²=0.18 — do not size aggressively. BLK R²=0.16. The
v2 models (`props_{stat}_v2.json`) are active; v1 files retained as fallback.

### GET `/edge/{game_id}`

Betting edge vs current market line. Uses `BettingEdge` from
`src/prediction/betting_edge.py` (wraps win probability).

**Query params:** `home=BOS`, `away=MIL`, `home_odds=-110`, `away_odds=-110`

**Response:**
```json
{
  "game_id": "0022400512",
  "edges": [
    { "team": "BOS", "edge": 0.043, "ev": 0.031, "kelly_fraction": 0.028 }
  ]
}
```

### GET `/win-prob/{game_id}`

Pregame win probability from `src/prediction/win_probability.py`.

**Query params:** `home=BOS`, `away=MIL`, `season=2025-26`

**Response:**
```json
{
  "game_id": "0022400512",
  "home_win_prob": 0.61,
  "confidence_interval": [0.56, 0.66],
  "model": "xgboost_v2"
}
```

Honest metric: 0.709 accuracy / 0.193 Brier (3-fold walk-forward).
Do not cite the endQ3 Brier 0.1191 — that figure is retracted (Q4 feature leak).

### GET `/lineup/{team}`

Injury-filtered DNP list via `InjuryMonitor` (ESPN + NBA official feeds).

```json
{ "team": "BOS", "dnp": ["Kristaps Porzingis"], "active_count": "unknown" }
```

### POST `/backtest/{stat}`

Prop backtest gate. Cached 24h. `stat` ∈ {pts, reb, ast, fg3m, stl, blk, tov}.

**Request:** `{ "seasons": ["2024-25"], "edge_threshold": 0.04 }`

**Response:**
```json
{
  "stat": "pts",
  "n": 1240,
  "mae": 4.58,
  "hit_rate_over": 0.512,
  "roi_at_break_even_odds": -0.020,
  "passed_gate": false,
  "edge_buckets": {}
}
```

---

## Predictions Router (`/predictions`)

**Module:** `api/predictions_router.py`

### GET `/predictions/props/{player_id}`

Full prop stack by numeric NBA player ID. More complete than root `/props` —
includes DNP probability, injury risk, confidence, suppression flag.

**Query params:** `season=2025-26`, `opp_team=""`

**Response:**
```json
{
  "player_id": 2544,
  "player_name": "LeBron James",
  "props": { "pts": 24.1, "reb": 7.4, "ast": 8.1, "fg3m": 1.8, "stl": 1.2, "blk": 0.6, "tov": 3.1 },
  "dnp_prob": 0.03,
  "injury_risk": 0.12,
  "suppressed": false,
  "suppression_reason": null,
  "confidence": 0.82,
  "edges": { "pts": 0.026, "reb": 0.018 }
}
```

### POST `/predictions/injury-risk`

Injury risk + load management from `data/models/injury_risk.pkl`.

**Request:** `{ "player_id": 2544, "season": "2025-26" }`

**Response:**
```json
{
  "player_id": 2544,
  "player_name": "LeBron James",
  "injury_risk_score": 0.18,
  "risk_level": "Low",
  "load_management_prob": 0.08,
  "games_missed_recent": 2,
  "drivers": { "age": 0.12, "b2b": 0.06 }
}
```

### POST `/predictions/breakout`

Breakout potential score from `data/models/breakout_predictor.pkl`.

**Request:** `{ "player_id": 1629029, "opponent_team": "OKC", "season": "2025-26" }`

**Response:**
```json
{
  "player_id": 1629029,
  "player_name": "Ja Morant",
  "breakout_score": 0.74,
  "predicted_pts_above_avg": 3.2,
  "key_factors": ["usage_trend", "matchup_advantage"],
  "signals": { "usage_trend": 0.82, "matchup_advantage": 0.61 }
}
```

### POST `/predictions/lineup-optimizer`

Greedy DFS optimizer. Requires at least one `game_id` from tonight's slate.

**Request:**
```json
{ "game_ids": ["0022400512"], "budget": 50000.0, "platform": "draftkings" }
```

### POST `/predictions/game`

Full game prediction: win prob + game-level models + player props + Kelly edges.

**Request:**
```json
{
  "home_team": "BOS",
  "away_team": "MIL",
  "season": "2025-26",
  "player_ids": null,
  "lines": null,
  "bankroll": 10000.0,
  "game_date": null
}
```

### GET `/predictions/today`

Win probabilities + top props for tonight's games via NBA scoreboard.

---

## Models Router (`/predictions`)

**Module:** `api/models_router.py`

### GET `/predictions/shot`

xFG probability from spatial features (xFG v1, Brier 0.226, 221K shots).

**Query params:** `defender_dist` (required), `shot_angle` (required),
`fatigue_proxy=0.0`, `court_zone=paint`

**Response:** `{ "probability": 0.487, "model": "xfg_v1", "inputs": {...} }`

### GET `/predictions/win`

In-game win probability from spatial momentum features.

**Query params:** `convex_hull_area` (required), `avg_inter_player_dist=0.0`,
`scoring_run=0`, `possession_streak=0`, `swing_point=0`

**Response:** `{ "win_probability": 0.634 }`

### GET `/predictions/player-impact`

Player EPA per 100 possessions. Returns 503 until 20+ CV games are trained
(Phase 6 requirement).

---

## Analytics Router (`/analytics`)

**Module:** `api/analytics_router.py`

### GET `/analytics/shot-chart`

All shot log records for a game from the `shot_logs` SQLite table.

**Query params:** `game_id` (required)

**Response:**
```json
{
  "game_id": "abc123",
  "shots": [
    {
      "player_id": 1,
      "x": 14.2,
      "y": 8.1,
      "made": true,
      "court_zone": "paint",
      "nearest_defender_dist": 3.1,
      "shot_angle": 45.0,
      "fatigue_proxy": 0.12
    }
  ]
}
```

### GET `/analytics/tracking`

Raw tracking coordinates for a frame range.

**Query params:** `game_id` (required), `frame_start=0`, `frame_end=500`,
`object_type=player`

**Response:**
```json
{
  "game_id": "abc123",
  "frame_range": [0, 500],
  "rows": [
    { "frame_number": 0, "track_id": 1, "x": 24.1, "y": 12.3,
      "vx": 0.4, "vy": -0.1, "direction": 45.0, "object_type": "player" }
  ]
}
```

### GET `/analytics/lineup-stats`

Returns **503** until Phase 6 (requires 20+ full games of CV data).

---

## De-Vig Router

**Module:** `api/devig_router.py`

### POST `/api/devig`

Converts vigged sportsbook odds into fair probabilities.

**Request (2-way market):**
```json
{ "over_odds": -115, "under_odds": -105, "method": "shin" }
```

**Request (n-way market):**
```json
{ "odds": [-110, -110, +250], "method": "proportional" }
```

`method` ∈ `{"shin", "additive", "proportional", "multiplicative", "power"}`
Default: `"shin"` (Shin 1992 insider-trading model, numerically-stable bisection).

**Response:**
```json
{
  "method": "shin",
  "vigged": [0.535, 0.488],
  "fair_probs": [0.523, 0.477],
  "fair_odds": [-109, +109],
  "overround": 0.023
}
```

Implementation: `src/prediction/devig.py` — 7 tests verify Shin output against
published theory. `devig()` is also the internal de-vig used by the Kelly sizer.

---

## Live Game Router

**Module:** `api/live_game_router.py`

### GET `/live/{game_id}`

Per-game live projection panel (HTML page). Read-only — does not poll NBA API or
write to disk.

Surfaces for every player in the game:
- Pregame projection (q50) from `data/cache/predictions_cache_<date>.parquet`
- Current actual (if a live box score is cached)
- Pace-projected final (`current / minutes_played × projected_minutes`)
- Best current sportsbook line (from `api._courtvision_odds.consolidate()`)
- Edge vs line for PTS

Optional quarter-shape decay: set `CV_QSHAPE_DECAY=1` to apply league-average
per-quarter rate factors (Q4 is lower for pts/ast/fg3m).

---

## Lines Router

**Module:** `api/lines_router.py`

### GET `/api/lines/scan`

Multi-book line scanner. Reads consolidated per-book CSVs via
`api._courtvision_odds.consolidate(date)`.

**Query params:** `date=YYYY-MM-DD`, `stat=pts`, `min_books=2`, `sort=edge`

**Response:**
```json
{
  "date": "2026-06-11",
  "rows": [
    {
      "player": "Jayson Tatum",
      "stat": "pts",
      "line": 26.5,
      "best_over_book": "fanduel",
      "best_over_price": -108,
      "best_under_book": "draftkings",
      "best_under_price": -112,
      "best_combined_edge": 0.018,
      "books": [...]
    }
  ]
}
```

`best_combined_edge` = max implied-probability spread across books (larger =
more line-shopping value). Computed via `_american_to_implied` from
`api._courtvision_odds`.

### GET `/scan`

HTML line-scanner dashboard page (rendered from `templates/scan.html`).

---

## CLV Router

**Module:** `api/clv_router.py`

### GET `/clv`

CLV dashboard HTML page. Renders dark-theme dashboard with:
- Headline tiles: P&L, ROI, avg CLV bps, win%, Sharpe
- `by_book` table
- `by_stat` table
- Daily ROI sparkline (reads `data/clv/daily_clv.csv`)

### GET `/api/clv/summary`

Rolling CLV summary (7d, 30d) as JSON.

**Query params:** `days=7`

---

## Risk Router

**Module:** `api/_risk_router.py`
**Auth:** `LIVE_V2_AUTH_TOKEN` env var — query param `?token=` or `cv_session` HttpOnly cookie

### GET `/api/risk/status`

Live risk snapshot from `src/prediction/risk_guards.py`.

```json
{
  "kill_switch_engaged": false,
  "current_drawdown_pct": 2.1,
  "daily_bet_count": 8,
  "bankroll": 10000.0,
  "alerts": []
}
```

Drawdown alerts fire to Slack webhook when drawdown crosses 10% (medium) or 15%
(auto-engages kill switch).

### POST `/api/risk/kill-switch`

Engage or disengage the drawdown kill switch.

**Request:** `{ "engage": true }`

### POST `/api/bankroll/set`

Update bankroll value (auth-gated).

**Request:** `{ "bankroll": 12000.0 }`

---

## Dashboard Router

**Module:** `api/dashboard_router.py`

### POST `/chat`

AI chat backed by Claude + live DB + model tools.

**Request:** `{ "message": "What are the top edges tonight?", "game_id": null }`
**Response:** `{ "response": "..." }`

### GET `/analytics/edges/today`

Ranked betting edges for today's slate.

**Query params:** `min_ev=0.03`

**Response:**
```json
{
  "edges": [
    { "game_id": "...", "stat": "pts", "direction": "over", "ev": 0.045, "kelly": 0.028 }
  ],
  "count": 3
}
```

### GET `/analytics/clv-summary`

Rolling CLV for spread and total (7d, 30d).

---

## CourtVision Router

**Module:** `api/courtvision_router.py`

HTML/JSON surface for the live betting dashboard. All cold-path caches are
pre-warmed on startup (background thread).

| Route | Type | Description |
|-------|------|-------------|
| `GET /` | HTML | Home page |
| `GET /tonight` | HTML | Tonight's slate |
| `GET /game/{game_id}` | HTML | Per-game view |
| `GET /plus_ev` | HTML | +EV opportunities page |
| `GET /api/slate` | JSON | Tonight's props + edges |
| `GET /api/parlays` | JSON | Parlay suggestions |
| `GET /api/plus_ev` | JSON | +EV summary |
| `POST /api/bet/{id}` | JSON | Grade/update a bet |

**Rate limiting:** slowapi, 60 requests/minute per IP when `slowapi` is installed.

---

## WebSocket + SSE

### WebSocket `/ws/live-winprob`

Streams real-time win probability updates during live games.

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/live-winprob");
ws.onmessage = (e) => console.log(JSON.parse(e.data));
// {"game_id": "...", "home_win_prob": 0.63, "period": 3, "clock": "5:42"}
```

### SSE `/sse/live_edges`

Server-sent events stream for cross-book arbitrage opportunities.
Source: `scripts/arb_emitter_daemon.py` + `api._courtvision_odds.cross_book_spread`.

```javascript
const es = new EventSource("/sse/live_edges");
es.onmessage = (e) => console.log(JSON.parse(e.data));
// {"event": "arb.detected", "player": "...", "stat": "pts",
//  "over_book": "fanduel", "under_book": "draftkings", "edge_pp": 0.018}
```

Edges are freshness-gated (stale lines filtered), de-vigged via Shin, and tiered
by implied-prob spread magnitude before emission.

---

## Startup WebSocket Subscribers

The following background WebSocket subscribers start on boot when their env var
is set. Each writes to a separate dated CSV to avoid dual-writer races with HTTP
scrapers.

| Env var | Module | Output file |
|---------|--------|-------------|
| `DK_WS_ENABLED=1` | `scripts/draftkings_ws.py` | `data/lines/<date>_dk_ws.csv` |
| `FD_WS_ENABLED=1` | `scripts/fanduel_ws.py` | `data/lines/<date>_fd_ws.csv` |
| `BR_WS_ENABLED=1` | `scripts/betrivers_ws.py` | `data/lines/<date>_br_ws.csv` |
| `DK_INPLAY_WS_ENABLED=1` | `scripts/dk_inplay_ws.py` | `data/lines/<date>_dk_inplay_ws.csv` |

Task supervision: `scripts/task_supervisor.create_supervised_task()` wraps each
subscriber; failures log a warning but never crash the server.

---

## Caching

| Layer | TTL | Key |
|-------|-----|-----|
| In-process TTL cache (`_CACHE` dict) | 300s | endpoint + params tuple |
| Backtest cache (`_BACKTEST_CACHE`) | 24h | stat name |
| CourtVision slate cache | build-triggered | date string |
| NBA API game-log cache | 24h | season + player |
| Player season-average cache | 24h | season |

No Redis dependency for local development. The Railway/Fly deployment uses the
same in-process cache; a Redis layer is not currently wired.

---

## Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Invalid parameter (e.g., unknown stat for backtest) |
| 401 | Missing or invalid auth token (risk endpoints) |
| 404 | Player not found |
| 500 | Internal error (model load failure, DB error) |
| 503 | Feature not available (lineup-stats, player-impact before Phase 6 CV data) |

---

## Deployment

**Docker images (5):** each purpose-built for a deployment target.

```bash
# API server
docker build -f Dockerfile -t courtvision-api .
docker run -p 8000:8000 -e NBA_OFFLINE=1 courtvision-api

# Railway (auto-detects nixpacks.toml or Dockerfile)
# fly.toml for Fly.io; Procfile for Heroku-style

# Environment variables
NBA_OFFLINE=1               # default ON — prevent NBA API hangs
LIVE_V2_AUTH_TOKEN=<token>  # enable auth on risk endpoints
SENTRY_DSN=<dsn>            # optional error tracking
DK_WS_ENABLED=1             # optional DK WebSocket feed
```

**CI:** 3 GitHub Actions workflows — test + coverage gate, scheduled scrape.
Coverage floor enforced at 30%; core betting-math tests always required to pass.

---

## Known Issues

| Issue | Endpoint affected | Status |
|-------|-------------------|--------|
| `verify_production_mae.py` crashes (85 vs 129 feature mismatch) | `POST /backtest/{stat}` | Open |
| `verify_winprob.py` reads uncommitted cache — fails fresh clone | `GET /win-prob/{game_id}` | Open |
| DK/Caesars/MGM scrapers IP-blocked in production | `/api/lines/scan`, `/sse/live_edges` | Live coverage subset |
| PostgreSQL migration pending | All DB-backed endpoints use SQLite | ISSUE-021 |
| `/stitch` prefix doubles (router path + mount prefix) | `api/stitch_router.py` routes | Known |

---

*Related: [`ARCHITECTURE.md`](../ARCHITECTURE.md) · [`docs/ML_MODELS.md`](ML_MODELS.md) · [`docs/CV_TRACKING.md`](CV_TRACKING.md) · [`docs/JOB_EVIDENCE_PACKET.md`](JOB_EVIDENCE_PACKET.md)*

*Last verified: 2026-06-11*
