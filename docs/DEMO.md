# Demo Guide -- CourtVision

A deterministic walkthrough for evaluating the system. The headline product is
the converged 4-sport (NBA / MLB / Soccer / Tennis) calibrated prediction
platform; start with "The Predictor Platform" below. The FastAPI app, the NBA
prediction CLIs, and the CV pipeline are the NBA computer-vision lineage and are
covered afterward as engineering evidence.

All numbers here are calibration / sharpness (Brier / RMSE / ECE), never a dollar
edge. The single honesty truth-source for every figure is
`docs/JOB_EVIDENCE_PACKET.md`.

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
git clone https://github.com/neeljshah/court-vision.git
cd court-vision
conda create -n basketball_ai python=3.9 -y
conda activate basketball_ai
cp .env.example .env
```

For the predictor platform (the product) a slim install is enough -- it skips the
heavy CV / web / daemon stack:

```bash
pip install -r requirements-predictor.txt    # or: pip install -e .  -> cv-matchup / cv-predict / cv-live
```

For the full NBA computer-vision lineage (CV pipeline + FastAPI app), install the
full requirements instead:

```bash
pip install -r requirements.txt
```

Large data files are gitignored. To regenerate the NBA statistical data layer:

```bash
python scripts/ingest_fetch.py --count 80
python -m src.features.feature_engineering
```

To retrain the NBA models (optional -- pre-trained weights are in `data/models/`):

```bash
python -m src.prediction.player_props --retrain
python -m src.prediction.win_probability --retrain
```

---

## The Predictor Platform (the product)

One converged predictor per sport: a single calibrated win-probability anchors a
coherent pregame surface plus an in-game repricer, behind one unified CLI.

### One matchup -- pregame + in-game

```bash
python -m scripts.platformkit.predict_matchup --sport nba --home BOS --away LAL \
    --elapsed 0 --home-score 0 --away-score 0
```

Returns one JSON object: a calibrated pregame block (`p_home_win`, `total_mean`,
`margin_home`) and an in-game block that reprices off the realized state -- with
`edge_claimed: false` baked into the response. Swap `--sport` for `mlb`,
`soccer`, or `tennis`.

### Reproduce the leak-free scoreboards on committed fixtures (proof in under 60s)

```bash
python -m scripts.platformkit.beat_the_close_scoreboard --corpus tests/fixtures/proof
python -m scripts.platformkit.ingame_scoreboard         --corpus tests/fixtures/proof
```

Both print a per-sport verdict table directly. The `--corpus tests/fixtures/proof`
path runs the SAME code on a small committed slice (print-only; it never
overwrites the canonical reports), so a fresh clone can verify the methodology
end-to-end without the private corpora. The canonical full-corpus numbers live in
`vault/_Edge_Maps/_Beat_The_Close.md` and `vault/_Edge_Maps/_Ingame_Scoreboard.md`.

Full step-by-step is in `docs/PREDICTOR_QUICKSTART.md`; the proof-module map is in
`docs/PROOFS.md`.

---

## Validating the Environment

Tests are run per file (the full-suite collection freezes on a local box -- never
run `pytest tests/` unscoped). Run the predictor proof tests one file at a time,
for example:

```bash
python -m pytest tests/test_ingame_leak_free.py -q
python -m pytest tests/test_devig.py -q
```

Note: the suite has a documented tail of DB / GPU / optional-dependency failures
on a fresh clone; the betting-math core (devig / CLV / calibration) and the
predictor proof modules pass clean. See `docs/KNOWN_LIMITATIONS.md` for the
tracked failures and `docs/JOB_EVIDENCE_PACKET.md` for the honest test-pass
accounting (cite the per-file predictor tests, not an aggregate suite figure).

---

## The FastAPI App (NBA computer-vision lineage)

The NBA serving layer is part of the CV lineage, not the predictor product. It is
a substantial engineering demonstration of the decision-layer mechanics.

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
| `GET /api/props/edges` | Model vs live book lines -- **estimated edge, not realized ROI** |
| `GET /api/risk/status` | Drawdown kill-switch state + bankroll health |
| `GET /health/ops` | Scraper lag, CLV hit-rate, drift flags |
| `WebSocket /ws/live` | Real-time in-game projection stream |
| `GET /sse/live_edges` | Server-sent events: cross-book line discrepancies |

### Honest framing for the betting views

Any "edge %" or "EV" displayed in the `/api/props/edges` view is an
**estimate** from a model that has been shown to be approximately
break-even-minus-vig against real closing lines overall. The one durable
signal is AST (~+4-5% ROI, regular season only). Do not interpret any
displayed edge value as a guaranteed positive-expectation bet.

The dashboard is useful for observing the decision-layer mechanics
(de-vig -> edge -> Kelly -> CLV tracking) as an engineering demonstration.

---

## NBA Prediction CLI Demo (lineage)

These are the original NBA-only prop CLIs from the CV lineage. Any displayed
"edge %" or "EV" is an estimate from a model shown to be approximately
break-even-minus-vig vs real closing lines (AST the one durable regular-season
signal); treat them as an engineering demonstration, not a claimed edge. The
product-level predictor is the `predict_matchup` CLI above.

### Single player

```bash
python scripts/predict_player.py --name "Nikola Jokic" --opp LAL --home --rest 2
```

Output: 7 stat predictions (PTS / REB / AST / FG3M / STL / BLK / TOV) with
80% quantile intervals (q10-q90), L5/L10 baselines, and a Kelly-sized estimate
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

### Daily orchestrator (full ingest -> predict -> compare chain)

```bash
# Morning
python scripts/daily_run.py --auto-lineups --auto-lines --kelly --bankroll 1000

# Evening (settle against actuals)
python scripts/daily_run.py --settle --date 2026-05-24
```

---

## CV Pipeline Demo (NBA computer-vision lineage)

The computer-vision pipeline converts broadcast video into player court
coordinates and behavioral features. Cost: ~$0.10-$0.13 per game on a
consumer RTX 4060.

```bash
# Requires a local NBA broadcast video file
python scripts/run_clip.py --video data/videos/game.mp4 --no-show
```

**What to look for in the output:**

- `data/tracking_data.csv`: per-frame player (x, y) in court feet
- Console: homography RMSE, tracked-slot counts, re-ID hit rate
- The tracker maintains ~5-6 stable slots per frame on the calibration clip;
  reliable 10-player tracking on full broadcast footage is not yet demonstrated

**Honest CV status:** CV features are wired into the feature pipeline but carry
SHAP importance ~ 0 in the production prop models. The thesis is a cost moat,
not a demonstrated predictive advantage today. See `docs/KNOWN_LIMITATIONS.md`.

---

## Architecture Reference

```
broadcast video
      v
YOLOv8n ball/player detector
      v
SIFT homography (with EMA smoothing + replay suspension)
      v
6D Kalman + Hungarian tracker (AdvancedFeetDetector)
      v
OSNet re-ID + HSV histogram (player identity)
      v
EasyOCR scoreboard + jersey
      v
EventDetector (shots, fouls, rebounds, turnovers)
      v
data/tracking_data.csv
      v (joins with NBA API data)
src/features/feature_engineering.py
      v
prop models (XGB/LGB/MLP stack, ~51K player-games OOF)
win-prob model (XGBoost, expanding walk-forward)
Monte Carlo possession sim (src/sim/basketball_sim.py)
      v
FastAPI serving layer (~99 endpoints)
Jinja dashboard (18 templates)
Next.js frontend (webapp/)
```

---

## After the Demo

- `docs/JOB_EVIDENCE_PACKET.md` -- the honesty truth-source: every claim's proof artifact and the do-not-claim list
- `docs/PREDICTOR_PLATFORM.md` -- the product, in full (thesis, scorecards, architecture)
- `docs/PREDICTOR_QUICKSTART.md` -- run a calibrated prediction in minutes
- `docs/PROOFS.md` -- the proof-module index (every number maps to a runnable, leak-free proof)
- `docs/KNOWN_LIMITATIONS.md` -- current gaps, unvalidated claims, and tracked failures
- `docs/PROJECT_INDEX.md` -- the full navigation hub

---

See also: [docs/PREDICTOR_PLATFORM.md](PREDICTOR_PLATFORM.md) |
[docs/PROOFS.md](PROOFS.md) | [docs/PROJECT_INDEX.md](PROJECT_INDEX.md)
