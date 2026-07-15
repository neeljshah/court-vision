# Deployment — API and Dashboard

*API serving, execution router, and deployment architecture.*

---

## Current Serving Architecture

The system currently serves model predictions via a FastAPI backend running locally. There is no public deployment; all API calls are local.

```
Local development:
  uvicorn api.main:app --reload
  → http://localhost:8000

API documentation:
  http://localhost:8000/docs (Swagger UI)
  http://localhost:8000/redoc (ReDoc)
```

---

## FastAPI Endpoints

~100 endpoints across `api/main.py` and its routers (confirmed via `grep -r '@router\.\|@app\.' api/*.py`), not a small fixed set. Representative sample:

| Endpoint | Method | Router | Description |
|----------|--------|--------|-------------|
| `/predictions/props/{player_id}` | GET | predictions_router.py | Prop prediction for one player |
| `/predictions/game` | POST | predictions_router.py | Game-level prediction |
| `/predictions/injury-risk` | POST | predictions_router.py | Injury-risk prediction |
| `/predictions/breakout` | POST | predictions_router.py | Breakout prediction |
| `/predictions/lineup-optimizer` | POST | predictions_router.py | Lineup optimizer |
| `/predictions/today` | GET | predictions_router.py | Today's slate predictions |
| `/api/lines/scan` | GET | lines_router.py | Scan current lines across books for edge |
| `/health` | GET | main.py | System health status |
| `/models/win` | GET | models_router.py | Win-probability model endpoint |
| `/models/player-impact` | GET | models_router.py | Player-impact model endpoint |

### Example: Player Props Prediction

```bash
curl http://localhost:8000/predictions/props/203076
```

Response (see `api/predictions_router.py` `props_by_id`):
```json
{
  "player_id": 203076,
  "player_name": "...",
  "props": {"pts": 26.4, "reb": 5.2, "ast": 4.1},
  "dnp_prob": 0.02,
  "injury_risk": 0.05,
  "suppressed": false,
  "suppression_reason": null,
  "confidence": "...",
  "edges": {}
}
```

---

## Execution Router

[`api/execution_router.py`](../../api/execution_router.py) — handles bet routing logic. Currently generates manual bet slip queue; Playwright automation is Phase 17.

```python
from api.execution_router import ExecutionRouter

router = ExecutionRouter(config=betting_config)
result = router.route_bet(
    player_id="203076",
    prop_type="pts",
    threshold=27.5,
    side="over",
    kelly_fraction=0.5,
    bankroll=10000
)
# result contains: recommended_book, bet_amount, current_price, heat_score
```

---

## VPS Deployment Plan (Phase 21)

Target: always-on VPS for continuous odds monitoring, 6am prop sweep automation, and injury report polling.

**Recommended stack:**
- VPS: Hetzner CX21 (~€5/mo) or DigitalOcean Basic ($6/mo) for CPU-only serving
- GPU inference: kept on RunPod (pay-per-use for heavy inference; CPU-only for serving)
- Process manager: systemd or Supervisor for service management
- Reverse proxy: Nginx for HTTPS termination

**Services to run on VPS:**
1. FastAPI server (model serving)
2. Odds API polling cron (every 60 seconds during game days)
3. Referee assignment scraper (9am ET daily)
4. Injury report scraper (1pm and 5pm ET on game days)
5. Late scratch monitor (continuous, game day evenings)
6. Nightly learning loop (post-game, ~midnight ET)

**Services remaining on local GPU machine:**
1. CV pipeline processing (requires NVIDIA GPU)
2. Model retraining (heavy compute)

---

## Dashboard Deployment (Phase 7)

The dashboard is a Next.js frontend on the existing FastAPI backend.

**Development:**
```bash
cd apps/quant-dashboard
npm install
npm run dev    # http://localhost:3000
```

**Production build:**
```bash
npm run build
npm start
# Or: pm2 start npm --name "dashboard" -- start
```

**WebSocket connection:**
The dashboard connects to `ws://localhost:8000/ws/live` for the live board (see `api/live_v2_app.py`). Other live sockets: `/ws/win-prob/{game_id}` and `/ws/cv/{game_id}` (both in `api/main.py`).

---

## Environment Variables

Copy `.env.example` → `.env` and fill in:

```bash
# Database
DATABASE_URL=postgresql://nba_user:PASSWORD@localhost:5432/nba_ai
REDIS_URL=redis://localhost:6379

# API Keys
NBA_API_KEY=
THE_ODDS_API_KEY=

# Backblaze B2 (optional, for remote sync)
B2_BUCKET=
B2_KEY_ID=
B2_APP_KEY=

# Exchange APIs (paper/live gate)
LIVE_BETTING=0             # 0 = paper/dry-run (default), 1 = real orders -- global kill switch
KALSHI_ACCESS_KEY=
KALSHI_PRIVATE_KEY_PATH=
POLY_PRIVATE_KEY=
POLY_FUNDER_ADDRESS=
```

Full, current list: [`.env.example`](../../.env.example).

---

## Monitoring

**System health endpoint:**
```bash
curl http://localhost:8000/health
```

Returns (see `health()` in `api/main.py`):
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

A separate `/health/ops` endpoint reports operational pipeline metrics (scraper lag, CLV hit rate, drift flags).

**Grafana** (Phase 21): System metrics dashboard for model latency, API response times, data freshness. See [dashboard-spec.md](../architecture/dashboard-spec.md) System Health panel.

---

## Reproducibility

There is no dedicated `scripts/reproduce.py` or `data/release/` bundle yet -- that
release-artifact pipeline (seeded game list + SHA256 manifest + tagged release)
is not built. Current setup path:

```bash
bash scripts/setup_dev.sh
cp .env.example .env  # fill API keys
```

See [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md) for what reproduction
evidence currently exists.

---

*See [data-pipeline.md](data-pipeline.md) for the ingest system. See [system-overview.md](../architecture/system-overview.md) for the full system architecture that the API serves.*


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
