# API Reference — NBA AI System

FastAPI backend for serving model predictions, analytics, and live data.

**Current state:** 2 routers live (predictions + analytics). Full 12-endpoint spec planned for Phase 13.

**Base URL:** `http://localhost:8000`

---

## Starting the Server

```bash
conda activate basketball_ai
cd C:/Users/neelj/nba-ai-system
uvicorn api.main:app --reload
# → http://localhost:8000
# → http://localhost:8000/docs  (auto-generated Swagger UI)
```

---

## Current Endpoints (Live)

### GET `/predictions/props/{player_name}`

Returns all 7 prop projections for a player vs their next opponent.

**Request:**
```
GET /predictions/props/Jayson%20Tatum?opp_team=MIL&season=2024-25
```

**Response:**
```json
{
  "player": "Jayson Tatum",
  "opp_team": "MIL",
  "dnp_risk": 0.03,
  "projections": {
    "pts": {
      "projection": 27.4,
      "line": 26.5,
      "edge": "over",
      "edge_pct": 0.043,
      "confidence": 0.81
    },
    "reb": {
      "projection": 8.2,
      "line": 8.0,
      "edge": "over",
      "edge_pct": 0.021
    },
    "ast": { "projection": 4.9, "line": 4.5, "edge": "over" },
    "fg3m": { "projection": 2.8, "line": 2.5, "edge": "over" },
    "stl": { "projection": 1.1, "line": 1.0, "edge": "push" },
    "blk": { "projection": 0.8, "line": 1.0, "edge": "under" },
    "tov": { "projection": 2.1, "line": 2.5, "edge": "under" }
  },
  "features_used": 57,
  "sharp_adjustment_applied": false
}
```

---

### GET `/predictions/win-probability`

Pre-game win probability for a matchup.

**Request:**
```
GET /predictions/win-probability?home_team=BOS&away_team=MIL&season=2024-25
```

**Response:**
```json
{
  "home_team": "BOS",
  "away_team": "MIL",
  "home_win_prob": 0.624,
  "away_win_prob": 0.376,
  "projected_spread": -7.2,
  "projected_total": 226.4,
  "confidence": 0.78,
  "key_factors": [
    "BOS +4.1 net rating advantage",
    "MIL back-to-back (rest disadvantage)",
    "BOS 8-2 last 10 at home"
  ]
}
```

---

### GET `/analytics/shot-chart/{player_id}`

Shot chart data for a player — coordinates, made/missed, xFG by zone.

**Request:**
```
GET /analytics/shot-chart/1629029?season=2024-25&min_games=10
```

**Response:**
```json
{
  "player_id": 1629029,
  "player_name": "Jayson Tatum",
  "season": "2024-25",
  "shots": [
    {
      "court_x": 14.2,
      "court_y": 4.8,
      "zone": "left_corner_3",
      "made": true,
      "xfg": 0.38,
      "shot_type": "catch_and_shoot",
      "quarter": 2,
      "game_clock": "4:23"
    }
  ],
  "zone_summary": {
    "paint_rate": 0.32,
    "corner_3_rate": 0.18,
    "above_break_3_rate": 0.29,
    "mid_range_rate": 0.21,
    "paint_fg_pct": 0.64,
    "above_break_3_fg_pct": 0.38,
    "actual_efg": 0.584,
    "xfg_efg": 0.531,
    "luck_factor": +0.053
  }
}
```

---

### GET `/analytics/lineup/{team_id}`

Five-man lineup data and net ratings for a team.

**Request:**
```
GET /analytics/lineup/1610612738?season=2024-25&min_minutes=50
```

**Response:**
```json
{
  "team_id": 1610612738,
  "team": "BOS",
  "lineups": [
    {
      "players": ["Tatum", "Brown", "White", "Holiday", "Porzingis"],
      "minutes": 387,
      "net_rtg": +14.2,
      "off_rtg": 128.4,
      "def_rtg": 114.2,
      "pace": 98.1,
      "spacing_score": 0.82
    }
  ]
}
```

---

## Phase 13 Planned Endpoints

Full REST API with 12 endpoints, Redis caching, and WebSocket.

### Predictions

```
GET  /predictions/game/{game_id}
     Win probability, spread, total, confidence intervals

GET  /predictions/props/{player_id}
     All 7 prop projections with edge vs current lines

GET  /predictions/props/{player_id}/distribution
     Full simulation distribution (P10/P25/mean/P75/P90)

GET  /predictions/edges
     All +EV edges today, sorted by EV, with Kelly sizes

GET  /predictions/dnp
     DNP probability for all players with injury flags
```

### Analytics

```
GET  /analytics/shot-chart/{player_id}
     Shot coordinates + xFG + zone efficiency

GET  /analytics/lineup/{team_id}
     5-man lineup data + net ratings + spacing scores

GET  /analytics/player/{player_id}/profile
     Full 96-metric player profile

GET  /analytics/matchup/{home_team}/{away_team}
     Head-to-head breakdown + predicted lineups + edges
```

### Data

```
GET  /data/injuries
     Current injury report (30min TTL)

GET  /data/odds
     Current lines from all available books

GET  /data/schedule
     Today's games with tip times + venue
```

### Simulation

```
POST /simulate/{game_id}
     Run 10K Monte Carlo simulation
     Returns: full stat distributions for all players

Body: {
  "home_lineup": ["player_id_1", ...],
  "away_lineup": ["player_id_1", ...],
  "n_simulations": 10000
}

Response: {
  "game_id": "...",
  "simulation_count": 10000,
  "home_win_prob": 0.624,
  "distributions": {
    "player_id_1": {
      "pts": {"p10": 18, "p25": 23, "mean": 27.4, "p75": 32, "p90": 37},
      "reb": {"p10": 5, "p25": 7, "mean": 8.2, "p75": 10, "p90": 12},
      ...
    }
  }
}
```

### Live (WebSocket)

```
WS   /ws/live/{game_id}
     Real-time win probability updates after each possession
     Requires Phase 16 (LSTM model)

Message format:
{
  "possession_number": 47,
  "home_score": 54,
  "away_score": 48,
  "home_win_prob": 0.712,
  "momentum": "home_run",
  "live_props": {
    "player_id_1": {
      "pts_current": 14,
      "pts_projected": 27.2,
      "pts_line": 26.5
    }
  }
}
```

---

## AI Chat Tools (Phase 15)

Claude API tool definitions for the AI chat interface:

```python
tools = [
    {
        "name": "get_game_prediction",
        "description": "Get win probability, spread, and total for a game",
        "input_schema": {
            "type": "object",
            "properties": {
                "home_team": {"type": "string"},
                "away_team": {"type": "string"},
                "date": {"type": "string", "format": "date"}
            }
        }
    },
    {
        "name": "get_player_props",
        "description": "Get prop projections and edge vs book line for a player",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {"type": "string"},
                "stats": {"type": "array", "items": {"type": "string"}},
                "date": {"type": "string"}
            }
        }
    },
    {
        "name": "get_analytics",
        "description": "Get any of 96 analytics metrics for a player or team",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string"},
                "metric": {"type": "string"},
                "filters": {"type": "object"}
            }
        }
    },
    {
        "name": "get_shot_chart",
        "description": "Get shot chart data for visualization",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {"type": "string"},
                "season": {"type": "string"},
                "filters": {"type": "object"}
            }
        }
    },
    {
        "name": "simulate_game",
        "description": "Run 10K Monte Carlo simulation for a game",
        "input_schema": {
            "type": "object",
            "properties": {
                "game_id": {"type": "string"},
                "n_simulations": {"type": "integer", "default": 10000}
            }
        }
    },
    {
        "name": "get_betting_edges",
        "description": "Get all +EV betting edges for today, ranked by expected value",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "min_edge_pct": {"type": "number", "default": 0.03},
                "stat_types": {"type": "array", "items": {"type": "string"}}
            }
        }
    },
    {
        "name": "get_injuries",
        "description": "Get current injury report and lineup news",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string"},
                "team": {"type": "string"}
            }
        }
    },
    {
        "name": "get_lineup_data",
        "description": "Get 5-man lineup net ratings for a team",
        "input_schema": {
            "type": "object",
            "properties": {
                "team": {"type": "string"},
                "season": {"type": "string"},
                "min_minutes": {"type": "integer", "default": 50}
            }
        }
    },
    {
        "name": "get_player_similarity",
        "description": "Find historically similar players to a given player",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_name": {"type": "string"},
                "n_comps": {"type": "integer", "default": 5}
            }
        }
    },
    {
        "name": "render_chart",
        "description": "Render a chart inline in the chat conversation",
        "input_schema": {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": [
                        "shot_chart", "bar", "line", "distribution",
                        "radar", "heatmap", "scatter", "win_prob",
                        "box_plot", "lineup_matrix"
                    ]
                },
                "data": {"type": "object"},
                "title": {"type": "string"},
                "config": {"type": "object"}
            }
        }
    }
]
```

---

## Redis Caching (Phase 13)

All prediction endpoints will be cached in Redis:

| Endpoint | TTL | Invalidation |
|---|---|---|
| `/predictions/props/{player}` | 15 minutes | On injury update |
| `/predictions/win-probability` | 30 minutes | On lineup news |
| `/analytics/shot-chart` | 24 hours | On new game data |
| `/analytics/lineup` | 1 hour | On rotation change |
| `/predictions/edges` | 15 minutes | On odds update |
| `/data/injuries` | 5 minutes | Push on RotoWire update |

---

## Known Issues (Current State)

**6 failing tests in `tests/test_models_router.py`:**
- `AttributeError` on `/predictions/shot` — wrong attribute access
- Wrong status codes on `/predictions/player-impact`

These are pre-existing API wiring issues. The underlying prediction models work correctly — the failure is in the FastAPI route handlers.

**Fix:** Wire `src/prediction/*.py` outputs into the route handlers for these endpoints (Phase 4.6 Track 2).
