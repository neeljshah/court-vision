# API Reference — CourtVision

FastAPI backend. Phase 13.5 complete — 5 routers, 21+ endpoints live.

**Base URL:** `http://localhost:8000`  
**Docs:** `http://localhost:8000/docs` (auto-generated Swagger UI)

```bash
conda activate basketball_ai
uvicorn api.main:app --reload
```

---

## Endpoint Index

| Method | Path | Router | Description |
|--------|------|--------|-------------|
| GET | `/health` | main.py | System status |
| POST | `/simulate` | main.py | Monte Carlo game simulation |
| POST | `/simulate_game` | main.py | Full game simulation with rosters |
| POST | `/over_prob` | main.py | Per-stat over probability |
| GET | `/props/{player_id}` | main.py | 7-stat prop projections (by name) |
| GET | `/edge/{game_id}` | main.py | Betting edge vs market |
| GET | `/win-prob/{game_id}` | main.py | Win probability |
| GET | `/lineup/{team}` | main.py | Injury-filtered lineup |
| POST | `/backtest/{stat}` | main.py | Prop backtest gate (24h cache) |
| GET | `/predictions/shot` | models_router.py | xFG probability (spatial) |
| GET | `/predictions/win` | models_router.py | In-game win probability |
| GET | `/predictions/player-impact` | models_router.py | Player EPA (Phase 6+ placeholder) |
| GET | `/predictions/props/{player_id}` | predictions_router.py | Props by numeric player ID |
| POST | `/predictions/injury-risk` | predictions_router.py | Injury risk + load management |
| POST | `/predictions/breakout` | predictions_router.py | Breakout potential score |
| POST | `/predictions/lineup-optimizer` | predictions_router.py | DFS lineup optimizer |
| POST | `/predictions/game` | predictions_router.py | Full game prediction orchestration |
| GET | `/predictions/today` | predictions_router.py | Tonight's game predictions |
| GET | `/analytics/shot-chart` | analytics_router.py | Shot log for a game |
| GET | `/analytics/tracking` | analytics_router.py | Tracking coordinates by frame range |
| GET | `/analytics/lineup-stats` | analytics_router.py | 503 until Phase 6 (20+ CV games) |
| POST | `/chat` | dashboard_router.py | AI chat (Claude + DB + models) |
| GET | `/analytics/clv-summary` | dashboard_router.py | Rolling CLV (7d/30d) |
| GET | `/analytics/edges/today` | dashboard_router.py | Today's ranked betting edges |

---

## Core Endpoints (api/main.py)

### GET `/health`

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

---

### POST `/simulate`

Monte Carlo game simulation. TTL-cached 300s.

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

**Example:**
```bash
curl -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{"team_a": "BOS", "team_b": "MIL", "n_sims": 1000}'
```

---

### POST `/simulate_game`

Full game simulation with optional per-team stats override.

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

---

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
{ "player_id": "Jayson Tatum", "stat": "pts", "line": 26.5, "over_prob": 0.612, "mean": 27.4 }
```

---

### GET `/props/{player_id}`

7-stat prop projections. Accepts player name or ID string. Uses `stack_predict`; falls back to `predict_props` if stack returns empty.

**Query params:** `opp_team=GSW` (default), `season=2025-26` (default)

**Example:**
```bash
curl "http://localhost:8000/props/LeBron%20James?opp_team=MIL&season=2024-25"
```

**Response:**
```json
{
  "pts": 24.1,
  "reb": 7.4,
  "ast": 8.1,
  "fg3m": 1.8,
  "stl": 1.2,
  "blk": 0.6,
  "tov": 3.1
}
```

**Known issue:** STL R²=0.18 — do not size aggressively until `opp_to_rate`/`opp_pace` features land.

---

### GET `/edge/{game_id}`

Betting edge vs current market line. Uses XGBoost win probability internally.

**Query params:** `home=BOS`, `away=MIL`, `home_odds=-110`, `away_odds=-110`

**Example:**
```bash
curl "http://localhost:8000/edge/0022400512?home=BOS&away=MIL&home_odds=-110&away_odds=+100"
```

**Response:**
```json
{
  "game_id": "0022400512",
  "edges": [
    { "team": "BOS", "edge": 0.043, "ev": 0.031, "kelly_fraction": 0.028 }
  ]
}
```

---

### GET `/win-prob/{game_id}`

XGBoost win probability with confidence interval.

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

---

### GET `/lineup/{team}`

Returns injury-filtered DNP list (Out/Doubtful) via InjuryMonitor.

**Response:**
```json
{ "team": "BOS", "dnp": ["Kristaps Porzingis"], "active_count": "unknown — filter applied" }
```

---

### POST `/backtest/{stat}`

Prop backtest gate. Cached 24h. `stat` must be one of: pts, reb, ast, fg3m, stl, blk, tov.

**Request:**
```json
{ "seasons": ["2024-25"], "edge_threshold": 0.04 }
```

**Response:**
```json
{
  "stat": "pts",
  "n": 1240,
  "mae": 3.1,
  "hit_rate_over": 0.512,
  "roi_at_break_even_odds": 0.024,
  "passed_gate": true,
  "edge_buckets": {}
}
```

**Error codes:** 400 if stat not in valid list; 500 on internal error.

---

## Predictions Router (`/predictions` prefix)

### GET `/predictions/shot`

xFG probability from spatial features. Backed by xFG v1 (Brier 0.226, 221K shots).

**Query params:** `defender_dist` (required), `shot_angle` (required), `fatigue_proxy=0.0`, `court_zone=paint`

**Response:**
```json
{ "probability": 0.487, "model": "xfg_v1", "inputs": { ... } }
```

---

### GET `/predictions/win`

In-game win probability using spatial momentum features.

**Query params:** `convex_hull_area` (required), `avg_inter_player_dist=0.0`, `scoring_run=0`, `possession_streak=0`, `swing_point=0`

**Response:**
```json
{ "win_probability": 0.634 }
```

---

### GET `/predictions/player-impact`

Player EPA per 100 possessions. Phase 6+ placeholder until 20 CV games trained.

**Query params:** `track_id` (required), `made_rate=0.0`, `shots_taken=0`

---

### GET `/predictions/props/{player_id}`

Props by numeric NBA player ID. More complete than root `/props` — includes DNP prob, injury risk, confidence, suppression.

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

---

### POST `/predictions/injury-risk`

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

---

### POST `/predictions/breakout`

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

---

### POST `/predictions/lineup-optimizer`

Greedy DFS optimizer. Requires at least one game_id from tonight's slate.

**Request:**
```json
{ "game_ids": ["0022400512"], "budget": 50000.0, "platform": "draftkings" }
```

---

### POST `/predictions/game`

Full game prediction: win prob + game models + player props + Kelly edges.

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

---

### GET `/predictions/today`

Win probabilities and top props for tonight's games via NBA scoreboard.

---

## Analytics Router (`/analytics` prefix)

### GET `/analytics/shot-chart`

All shot log records for a game from `shot_logs` table.

**Query params:** `game_id` (required)

**Response:**
```json
{
  "game_id": "abc123",
  "shots": [
    { "player_id": 1, "x": 14.2, "y": 8.1, "made": true, "court_zone": "paint",
      "nearest_defender_dist": 3.1, "shot_angle": 45.0, "fatigue_proxy": 0.12 }
  ]
}
```

---

### GET `/analytics/tracking`

Tracking coordinates for a frame range.

**Query params:** `game_id` (required), `frame_start=0`, `frame_end=500`, `object_type=player`

**Response:**
```json
{
  "game_id": "abc123",
  "frame_range": [0, 500],
  "rows": [{ "frame_number": 0, "track_id": 1, "x": 24.1, "y": 12.3, "vx": 0.4, "vy": -0.1, "direction": 45.0, "object_type": "player" }]
}
```

---

### GET `/analytics/lineup-stats`

Returns **503** until Phase 6 (requires 20+ full games of CV data).

---

## Dashboard Router (root prefix)

### POST `/chat`

AI chat powered by Claude + live DB + model tools.

**Request:** `{ "message": "What are the top edges tonight?", "game_id": null }`

**Response:** `{ "response": "..." }`

---

### GET `/analytics/clv-summary`

Rolling CLV for spread and total (7d, 30d).

---

### GET `/analytics/edges/today`

Ranked betting edges for today's slate.

**Query params:** `min_ev=0.03`

**Response:**
```json
{ "edges": [{ "game_id": "...", "stat": "pts", "direction": "over", "ev": 0.045, "kelly": 0.028 }], "count": 3 }
```

---

## TTL Cache

- Root endpoint responses: 300s in-process cache. Key = endpoint + params. No Redis for local dev.
- `/backtest/{stat}`: 24h cache (`_BACKTEST_CACHE`).

---

## Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Invalid parameter (e.g., bad stat name for backtest) |
| 404 | Player not found (predictions router) |
| 500 | Internal error (model failure, DB failure) |
| 503 | Feature not yet available (lineup-stats, player-impact before Phase 6) |

---

## Known Production Blockers

- `/props` (root) calls `stack_predict` with name-based ID; falls back to `predict_props` if stack empty
- Isotonic calibration layer missing — Kelly sizing unsafe without it (CLAUDE.md issue #2)
- Correlation matrix not populated in `kelly_corr` — assumes zero correlation (issue #6)
- `stitch_router.py` routes include double `/stitch` prefix (router path + mount prefix)
