# API Reference — CourtVision

FastAPI backend. Phase 13.5 complete — 5 routers, 9+ endpoints live.

**Base URL:** `http://localhost:8000`  
**Docs:** `http://localhost:8000/docs` (auto-generated Swagger UI)

```bash
conda activate basketball_ai
uvicorn api.main:app --reload
```

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
    "win_probability": "available"
  }
}
```

---

### POST `/simulate`

Run Monte Carlo game simulation.

```json
// Request
{ "team_a": "BOS", "team_b": "MIL", "n_sims": 1000 }

// Response
{ "team_a_win_pct": 0.58, "mean_score_a": 112.4, "mean_score_b": 108.1 }
```

---

### GET `/props/{player_id}`

7-stat prop projections for a player.

```
GET /props/LeBron%20James?opp_team=MIL&season=2024-25
```

```json
{
  "player": "LeBron James",
  "projections": {
    "pts":  { "projection": 24.1, "line": 23.5, "edge": "over",  "edge_pct": 0.026 },
    "reb":  { "projection": 7.4,  "line": 7.0,  "edge": "over",  "edge_pct": 0.018 },
    "ast":  { "projection": 8.1,  "line": 7.5,  "edge": "over",  "edge_pct": 0.031 },
    "fg3m": { "projection": 1.8,  "line": 2.0,  "edge": "under", "edge_pct": 0.011 },
    "stl":  { "projection": 1.2,  "line": 1.0,  "edge": "push",  "edge_pct": 0.002 },
    "blk":  { "projection": 0.6,  "line": 0.5,  "edge": "over",  "edge_pct": 0.008 },
    "tov":  { "projection": 3.1,  "line": 3.5,  "edge": "under", "edge_pct": 0.019 }
  }
}
```

**Note:** STL R²=0.07 (weak) — do not size aggressively until `opp_to_rate`/`opp_pace` features land.

---

### GET `/edge/{game_id}`

Betting edge vs current market line.

```
GET /edge/0022400512?market_line=-4.5&market_total=221.5
```

```json
{
  "game_id": "0022400512",
  "home_edge": 0.043,
  "spread_edge": 0.031,
  "total_edge": -0.012,
  "kelly_fraction": 0.028
}
```

---

### GET `/win-prob/{game_id}`

XGBoost win probability.

```json
{ "game_id": "0022400512", "home_win_prob": 0.61, "model": "xgboost_v2" }
```

---

### GET `/lineup/{team}`

Lineup optimizer — optimal 5-man unit.

```
GET /lineup/BOS?vs_team=MIL&minutes_budget=36
```

```json
{
  "team": "BOS",
  "optimal_lineup": ["T. Brown", "J. Tatum", "K. Porzingis", "J. Holiday", "D. White"],
  "projected_net_rtg": 8.4
}
```

---

### POST `/backtest/{stat}`

Backtest gate — fails closed on empty data (do NOT bypass in production).

```json
// Request
{ "player_id": "LeBron James", "season": "2024-25", "n_games": 20 }

// Response
{ "stat": "pts", "mae": 3.1, "r2": 0.44, "n": 20, "pass": true }
```

---

### POST `/simulate_game` and POST `/over_prob`

Extended simulation endpoints — full game simulation and per-stat over probability. See `/docs` for full schemas.

---

## Routers

| Router | Prefix | Key Endpoints |
|--------|--------|---------------|
| `predictions_router.py` | `/predictions` | `/props/{player_id}`, `/game`, `/today`, `/injury-risk`, `/breakout`, `/lineup-optimizer` |
| `analytics_router.py` | `/analytics` | `/shot-chart`, `/lineup-stats`, `/tracking` |
| `models_router.py` | `/predictions` | model management |
| `stitch_router.py` | `/stitch` | AI interface |
| `dashboard_router.py` | (root) | dashboard data |

---

## TTL Cache

Responses cached in-process for 300s. Cache key = endpoint + params. No Redis dependency for local dev.

---

## Known Issues (pre-production blockers)

- `/props` calls raw `predict_props` instead of `stack_predict` (CLAUDE.md issue #3)
- Isotonic calibration layer missing — Kelly sizing unsafe without it (issue #2)
- Correlation matrix not populated in `kelly_corr` — assumes zero correlation (issue #6)
