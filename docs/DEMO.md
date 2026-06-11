# Demo Guide — CourtVision

A deterministic walkthrough for evaluating the system. Covers environment
setup, the FastAPI app, the prediction CLIs, and the CV pipeline.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.9 |
| Environment manager | conda (recommended) |
| GPU | RTX 4060 or equivalent recommended for CV; CPU fallback exists |
| OS | Linux or Windows (Windows tested, macOS untested) |

---

## Setup

```bash
git clone https://github.com/neeljshah/nba-ai-system.git
cd nba-ai-system
conda create -n basketball_ai python=3.9 -y
conda activate basketball_ai
pip install -r requirements.txt
cp .env.example .env
```

Large data files are gitignored. To regenerate the statistical data layer:

```bash
python scripts/ingest_fetch.py --count 80
python -m src.features.feature_engineering
```

To retrain models (optional — pre-trained weights are in `data/models/`):

```bash
python -m src.prediction.player_props --retrain
python -m src.prediction.win_probability --retrain
```

---

## Validating the Environment

Run the test suite against the core betting-math and in-play subset:

```bash
python -m pytest tests/ -q
```

Note: the full ~7,400-test suite has a documented tail (~2–3%) of
DB/GPU/optional-dependency failures on a fresh clone. The betting-math
core (devig/CLV/calibration) and in-play subset pass clean. See
`docs/KNOWN_LIMITATIONS.md` for the tracked failures.

Verify the production model matches the honest baseline:

```bash
python scripts/verify_production_mae.py    # prop MAE vs claim
python scripts/verify_winprob.py           # walk-forward acc/Brier vs claim
```

Both scripts exit 0 within tolerance, 1 with a drift report.

> **Fresh-clone caveat:** `verify_winprob.py` reads a cached walk-forward
> results file (`data/models/winprob_walk_forward_results.json`) that is
> gitignored. Run `scripts/winprob_walk_forward.py` first to generate it.

---

## The FastAPI App

Start the server:

```bash
uvicorn api.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for the Swagger UI (~99 endpoints, 12 routers).

### Key routes to explore

| Endpoint | What it shows |
|---|---|
| `GET /tonight` | Tonight's slate: predicted props per player |
| `GET /results` | Historical prediction vs actual results |
| `POST /api/predict/player` | Single-player prediction (JSON) |
| `POST /api/devig` | Strip vig from any two-sided market (Shin default) |
| `GET /api/props/edges` | Model vs live book lines — **estimated edge, not realized ROI** |
| `GET /api/risk/status` | Drawdown kill-switch state + bankroll health |
| `GET /health/ops` | Scraper lag, CLV hit-rate, drift flags |
| `WebSocket /ws/live` | Real-time in-game projection stream |
| `GET /sse/live_edges` | Server-sent events: cross-book line discrepancies |

### Honest framing for the betting views

Any "edge %" or "EV" displayed in the `/api/props/edges` view is an
**estimate** from a model that has been shown to be approximately
break-even-minus-vig against real closing lines overall. The one durable
signal is AST (~+4–5% ROI, regular season only). Do not interpret any
displayed edge value as a guaranteed positive-expectation bet.

The dashboard is useful for observing the decision-layer mechanics
(de-vig → edge → Kelly → CLV tracking) as an engineering demonstration.

---

## Prediction CLI Demo

### Single player

```bash
python scripts/predict_player.py --name "Nikola Jokic" --opp LAL --home --rest 2
```

Output: 7 stat predictions (PTS / REB / AST / FG3M / STL / BLK / TOV) with
80% quantile intervals (q10–q90), L5/L10 baselines, and a Kelly-sized estimate
if `|edge| > 0.5` vs a supplied line.

### Full slate

```bash
python scripts/predict_slate.py
python scripts/predict_slate.py --save    # writes data/predictions/<date>.csv
```

Runtime: ~3 min for a 15-game slate.

### Compare to sportsbook lines

```bash
# Edit example_lines.csv with tonight's lines, then:
python scripts/compare_to_lines.py example_lines.csv --kelly --bankroll 1000
```

Output: predictions ranked by estimated EV with Kelly-sized stake suggestions.
These are estimates from a model that has not demonstrated a net edge vs real
closing lines (except AST). Use as an engineering demonstration.

### Daily orchestrator (full ingest → predict → compare chain)

```bash
# Morning
python scripts/daily_run.py --auto-lineups --auto-lines --kelly --bankroll 1000

# Evening (settle against actuals)
python scripts/daily_run.py --settle --date 2026-05-24
```

---

## CV Pipeline Demo

The computer-vision pipeline converts broadcast video into player court
coordinates and behavioral features. Cost: ~$0.10–$0.13 per game on a
consumer RTX 4060.

```bash
# Requires a local NBA broadcast video file
python scripts/run_clip.py --video data/videos/game.mp4 --no-show
```

**What to look for in the output:**

- `data/tracking_data.csv`: per-frame player (x, y) in court feet
- Console: homography RMSE, tracked-slot counts, re-ID hit rate
- The tracker maintains ~5–6 stable slots per frame on the calibration clip;
  reliable 10-player tracking on full broadcast footage is not yet demonstrated

**Honest CV status:** CV features are wired into the feature pipeline but carry
SHAP importance ≈ 0 in the production prop models. The thesis is a cost moat,
not a demonstrated predictive advantage today. See `docs/KNOWN_LIMITATIONS.md`.

---

## Architecture Reference

```
broadcast video
      ↓
YOLOv8n ball/player detector
      ↓
SIFT homography (with EMA smoothing + replay suspension)
      ↓
6D Kalman + Hungarian tracker (AdvancedFeetDetector)
      ↓
OSNet re-ID + HSV histogram (player identity)
      ↓
EasyOCR scoreboard + jersey
      ↓
EventDetector (shots, fouls, rebounds, turnovers)
      ↓
data/tracking_data.csv
      ↓ (joins with NBA API data)
src/features/feature_engineering.py
      ↓
prop models (XGB/LGB/MLP stack, ~51K player-games OOF)
win-prob model (XGBoost, expanding walk-forward)
Monte Carlo possession sim (src/sim/basketball_sim.py)
      ↓
FastAPI serving layer (~99 endpoints)
Jinja dashboard (18 templates)
Next.js frontend (webapp/)
```

---

## After the Demo

- `README.md` — end-to-end funnel narrative with honest numbers
- `docs/JOB_EVIDENCE_PACKET.md` — every claim's proof artifact and the do-not-claim list
- `docs/KNOWN_LIMITATIONS.md` — current gaps, unvalidated claims, and tracked failures
- `docs/BETTING.md` — decision-layer engineering (de-vig, Kelly, CLV)
- `docs/DATA.md` — data sources and ingest pipeline

---

See also: [docs/BETTING.md](BETTING.md) · [docs/DATA.md](DATA.md) ·
[PREDICTIONS_QUICKSTART.md](../PREDICTIONS_QUICKSTART.md)
