# Pipeline Flow
*Last updated: 2026-03-24*

← [[03 - Data Sources]] | → [[05 - Ideas and Future Work]]

---

## Overview

There are three distinct operating modes:
1. **Prediction-only** — no video, uses NBA API + trained models (runs now)
2. **Full game pipeline** — video processing + NBA API enrichment (Phase F/G)
3. **Daily production loop** — morning pipeline + nightly retrain (Phase 9+)

---

## Mode 1: Prediction-Only (Available Now)

No video required. Uses pre-trained models + NBA API data.

### Morning Prediction Run

```bash
conda activate basketball_ai
cd C:/Users/neelj/nba-ai-system

# 1. Run full morning pipeline
python scripts/daily_pipeline.py
# Steps: injuries → props → predictions → CLV log → edge report

# 2. Or run individual components:
python src/prediction/game_prediction.py --predict GSW BOS
python -c "
from src.prediction.player_props import predict_props
result = predict_props('Jayson Tatum', 'MIA', '2024-25')
print(result)
"
```

### Post-Game Outcome Recording

```bash
# Record game outcomes for CLV tracking + model retraining
python scripts/record_outcome.py --game-id 0022400710
```

### API Server

```bash
uvicorn api.main:app --reload --port 8000
# Endpoints documented at http://localhost:8000/docs
```

### Streamlit Dashboard

```bash
streamlit run dashboards/app.py
# Opens at http://localhost:8501
```

---

## Mode 2: Full Game Pipeline (Phase F — NEXT)

Downloads full NBA games from YouTube and processes through the CV pipeline.

```bash
# Phase F — process full games (NOT the short calibration clips)
python scripts/full_game_pipeline.py

# What it does:
# 1. yt-dlp search for NBA game broadcast
# 2. Download ~2h video (ytsearch)
# 3. Run advanced_tracker.py with --game-id
# 4. Enrich with NBA API (shot outcomes, lineups)
# 5. Write to data/tracking/{game_id}_{date}.csv
# 6. Write to PostgreSQL (if DATABASE_URL set)
# 7. Append to data/full_game_results.json
```

**IMPORTANT:** Always pass `--game-id` to link CV data to NBA API outcomes.

**NEVER run:** `run.py`, `run_clip.py`, `scripts/loop_processor.py` (fills disk)

---

## Mode 3: Daily Production Loop (Phase 9+)

Not yet active. Will run automatically after Phase 9 is built.

```
6:00 AM  → daily_pipeline.py
           ├── refresh_injury_report()
           ├── refresh_props()
           ├── predict_today_props()
           ├── log_pre_game_predictions()
           └── generate_edge_report()

Game ends → record_outcome.py --game-id {id}
           ├── fetch_box_score()
           ├── compare_vs_predictions()
           ├── record_clv()
           └── trigger_auto_retrain()

Nightly   → auto_retrain.py
           ├── check_drift()
           ├── retrain_stale_models()
           └── update_model_registry()
```

---

## Training Models

### Win Probability

```bash
python src/prediction/win_probability.py --train
# Uses: data/nba/team_stats_*.json + historical results
# Output: data/models/win_probability.pkl
# Time: ~2 min on CPU
```

### Player Props

```bash
python src/prediction/player_props.py --train
# Uses: gamelogs + shot_dashboard + advanced stats + schedule_context
# Output: data/models/props_{stat}.json (7 files)
# Time: ~5 min on CPU
```

### xFG v1

```bash
python src/prediction/xfg_model.py --train
# Uses: data/nba/shot_charts_*.json (221K shots)
# Output: data/models/xfg_v1.pkl
# Time: ~3 min on CPU
```

### All Phase 4.5 Models

```bash
# These are heuristic/rule-based and don't need long training
python src/prediction/load_management.py --train
python src/prediction/injury_risk.py --train
python src/prediction/breakout_predictor.py --train
# etc.
```

---

## Testing

```bash
# Full suite (431 tests — ~30s)
python -m pytest tests/ -q

# By phase
python -m pytest tests/test_phase2.py -v    # CV tracker tests
python -m pytest tests/test_phase3.py -v    # ML model tests
python -m pytest tests/test_new_models.py -v # Phase 4.5 smoke tests

# API tests
python -m pytest tests/test_predictions_router.py tests/test_models_router.py -v

# Single test
python -m pytest tests/test_phase3.py::test_win_prob_train -v
```

---

## Database Setup

```bash
# Ensure PostgreSQL is running and DATABASE_URL is set in .env
# Then run migrations
python src/data/migrations.py

# Verify
python -c "from src.data.db import get_connection; conn = get_connection(); print('DB OK')"
```

---

## Data Refresh

```bash
# Refresh shot dashboard (most important for props accuracy)
python src/data/nba_tracking_stats.py --fetch-shot-dashboard

# Refresh hustle + on/off stats
python src/data/nba_tracking_stats.py --fetch-all

# Refresh injury report (run before daily pipeline)
python -c "from src.data.injury_monitor import refresh_rotowire; refresh_rotowire()"

# Backfill missing PBP
python src/data/pbp_scraper.py --backfill

# Refresh BBRef advanced stats
python src/data/bbref_scraper.py --refresh
```

---

## CV Pipeline — Clip Mode (Safe)

For testing the tracker only (no full game):

```bash
# Process a single short clip (safe — won't fill disk)
python run_clip.py --video data/videos/test_clip.mp4 --game-id 0022400710 --max-frames 500

# Evaluate tracker accuracy on clip
python src/tracking/evaluate.py --clip data/videos/test_clip.mp4
```

---

## Celery Batch Processing

```bash
# Start Redis (required)
redis-server

# Start Celery worker
celery -A src.pipeline.tasks worker --loglevel=info

# Submit batch jobs
python scripts/batch_process.py --games-file data/game_ids.txt
```

---

## Monitoring

```bash
# Check model status (last trained, accuracy)
curl http://localhost:8000/api/models/status

# Check feature drift
python src/pipeline/feature_drift_detector.py --report

# Check CLV performance
python -c "
from src.analytics.clv_tracker import CLVTracker
tracker = CLVTracker()
tracker.print_summary()
"
```

---

## Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| Props returning 0 lines | DK v5 endpoint blocked | Use Odds API primary (already fixed ISSUE-022) |
| `isinstance(list, dict)` error | Props pipeline type check | Fixed ISSUE-023 |
| `int(player_id)` throws on name | Player ID is string name | Fixed ISSUE-024 |
| sklearn version mismatch | Model pickled with older sklearn | Retrain: `python src/prediction/win_probability.py --train` |
| 0 PBP games | Rate limiting | Add 0.8s delay, run during off-peak |
| Court homography drift | Low SIFT inlier count | EMA blend kicks in automatically at <40 inliers |

---

## Related Notes

- [[01 - System Architecture]] — full system design
- [[02 - Model Catalog]] — what each model does
- [[03 - Data Sources]] — where data comes from
