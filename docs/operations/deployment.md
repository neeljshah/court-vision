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

All endpoints are in [`api/main.py`](../../api/main.py).

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/predict/player-props` | POST | Batch prop predictions for a slate |
| `/predict/win-probability` | GET | Win probability for a game |
| `/predict/game-total` | GET | Over/under prediction for game total |
| `/portfolio/kelly-size` | POST | Kelly-fractional bet sizing |
| `/portfolio/positions` | GET | Current active positions |
| `/lines/current` | GET | Live lines from Odds API |
| `/health` | GET | System health status |
| `/models/registry` | GET | List all registered models |
| `/calibration/metrics` | GET | Current ECE and calibration stats |

### Example: Player Props Prediction

```bash
curl -X POST http://localhost:8000/predict/player-props \
  -H "Content-Type: application/json" \
  -d '{
    "game_id": "0022401234",
    "players": ["203076", "2544", "1629029"],
    "prop_types": ["pts", "reb", "ast"]
  }'
```

Response:
```json
{
  "predictions": {
    "203076": {
      "pts": {
        "distribution_mean": 26.4,
        "distribution_std": 5.2,
        "lines": {
          "24.5": {"p_over": 0.68, "p_under": 0.32},
          "27.5": {"p_over": 0.44, "p_under": 0.56},
          "30.5": {"p_over": 0.24, "p_under": 0.76}
        }
      }
    }
  },
  "metadata": {
    "model_version": "cv_17g_v2",
    "cv_features_used": true,
    "prediction_timestamp": "2026-05-10T09:31:00Z"
  }
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
The dashboard connects to `ws://localhost:8000/ws/odds` for real-time odds updates. FastAPI handles WebSocket via `python-socketio` + Redis Pub/Sub for fan-out to multiple connected clients.

---

## Environment Variables

Copy `.env.example` → `.env` and fill in:

```bash
# NBA API
NBA_API_DELAY=0.6          # seconds between requests (cloud IP safety)

# Odds API
ODDS_API_KEY=...           # theOddsApi.com key
ODDS_API_TIER=paid         # free|paid

# B2 Storage (optional, for remote sync)
B2_KEY_ID=...
B2_APPLICATION_KEY=...
B2_BUCKET=...

# Betting config
LIVE_BETTING=0             # 0 = paper mode; 1 = live (requires Phase 19 gate)
KELLY_FRACTION=0.5         # fractional Kelly multiplier
BANKROLL=10000             # current bankroll in dollars
MIN_EDGE=0.03              # minimum edge to bet (3%)

# Model config
CV_FEATURES_ENABLED=1      # 0 = API-only mode
MODEL_REGISTRY_PATH=data/models/model_registry.json
```

---

## Monitoring

**System health endpoint:**
```bash
curl http://localhost:8000/health
```

Returns:
```json
{
  "status": "healthy",
  "components": {
    "odds_api": {"status": "ok", "last_fetch": "2026-05-10T09:30:00Z"},
    "model_serving": {"status": "ok", "models_loaded": 19},
    "calibration": {"status": "ok", "last_update": "2026-05-09T23:45:00Z"},
    "database": {"status": "ok", "queue_depth": 4}
  },
  "alerts": []
}
```

**Grafana** (Phase 21): System metrics dashboard for model latency, API response times, data freshness. See [dashboard-spec.md](../architecture/dashboard-spec.md) System Health panel.

---

## Reproducibility

To reproduce the current model predictions exactly:

```bash
bash scripts/setup_dev.sh
cp .env.example .env  # fill API keys
python scripts/reproduce.py --seed 42 --games data/release/v0.14/game_list.json
sha256sum -c data/release/v0.14/output_hashes.txt
```

Release v0.14.0-80g ships the game list, seeds, pod config, and SHA256 of every tracking JSON. A reviewer with the videos can reproduce bit-exactly.

---

*See [data-pipeline.md](data-pipeline.md) for the ingest system. See [system-overview.md](../architecture/system-overview.md) for the full system architecture that the API serves.*
