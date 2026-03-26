<!-- AUTO-GENERATED — DO NOT EDIT BELOW THIS LINE -->

## Resume From Here — Last Updated: 2026-03-24 20:18

### Pick Up Where We Left Off
*(Fill in '## What's Next' in today's session note before closing)*

### This Session — Files Changed
- README.md — full rewrite (professional, investor-ready)
- CONTRIBUTING.md — created
- LICENSE — created (MIT)
- .gitignore — expanded and organized
- requirements.txt — expanded from 17 → 35+ packages with categories
- CLAUDE.md — optimized for token efficiency
- vault/ — new organized Obsidian documentation structure

---

## Open Priority Issues

1. 🔴 Win probability / game prediction models — data pipeline ready, model still TBD
2. 🔴 Analytics + tracking dashboards — not built yet
3. 🟡 HSV re-ID upgrades — jersey confusion on similar-colored uniforms
4. 🔴 Real game clip needed — tracker plateaued on Short4Mosaicing clip; need actual NBA broadcast footage
5. 🟢 Pano validation + fallback — fixed 2026-03-12

---

## What This Project Is

**CourtVision** — a self-improving possession-by-possession NBA game simulator combining CV tracking + NBA API + 90 ML models. Runs 10,000 Monte Carlo simulations per game, produces stat distributions for every player, compares against sportsbook lines, surfaces +EV edges.

**Three products:** Betting Dashboard (Kelly + CLV) | Analytics Dashboard (96 metrics, 10 chart types) | AI Chat (Claude + render_chart inline)

**Moat:** Spatial CV data (defender distance, spacing, fatigue) from broadcast video. Second Spectrum charges $1M+/yr for this. No public API has it.

**Full plan:** `.planning/ROADMAP.md` — 17 phases, 90 models, 96 analytics metrics

---

## Current Phase: Pre-Phase F

**Phases Complete:** 3 ✅ | 4 ✅ | 5 ✅ | 4.6 ✅ | Pre-Phase 6 Enrichment ✅

**Next action:** Phase F — run `scripts/full_game_pipeline.py` to download + process full NBA games

**Model status:**
- Win prob: 69.1% acc, Brier 0.203 (`data/models/win_probability.pkl`)
- Props ×7: R² > 0.93, MAE pts=0.308 (`data/models/props_*.json`)
- xFG v1: Brier 0.226, 221K shots (`data/models/xfg_v1.pkl`)
- DNP: AUC 0.979 (`data/models/dnp_model.pkl`)
- Matchup: R² 0.796 (`data/models/matchup_model.json`)
- Phase 4.5 models: load_management, injury_return, injury_risk, breakout_predictor, public_fade, soft_book_lag — all `.pkl` in `data/models/`

---

## Key Files

| File | Purpose |
|------|---------|
| `src/tracking/advanced_tracker.py` | AdvancedFeetDetector — main tracker |
| `src/tracking/color_reid.py` | TeamColorTracker — similar-color re-ID |
| `src/tracking/jersey_ocr.py` | EasyOCR jersey number reader |
| `src/pipeline/unified_pipeline.py` | Tracking → possession → spatial → CSV |
| `src/prediction/win_probability.py` | XGBoost win prob (WinProbModel) |
| `src/prediction/player_props.py` | predict_props() / train_props() |
| `src/prediction/prop_model_stack.py` | Ridge meta-model over all 7 props |
| `src/prediction/betting_portfolio.py` | Kelly + CLV + arb detection |
| `src/prediction/prop_backtester.py` | Historical backtest + paper trading |
| `src/data/nba_tracking_stats.py` | NBA API tracking data fetcher |
| `src/features/feature_engineering.py` | 60+ ML features |
| `api/main.py` | FastAPI app (10 endpoints) |
| `scripts/daily_pipeline.py` | Morning: injuries → props → predict → CLV |
| `scripts/record_outcome.py` | Post-game: box score → CLV report |
| `database/schema.sql` | PostgreSQL schema (9 tables, 2 views) |

---

## Architecture Summary

```
CV Tracker (broadcast feed) + NBA API (stats, PBP, shots)
    → 90 ML Models → Possession Simulator (10K Monte Carlo)
    → Stat distributions → Compare vs book lines → Flag +EV edges
    → FastAPI → Next.js Dashboard + Claude AI Chat
```

**Tracking tech:** YOLOv8n → SIFT homography → Kalman+Hungarian → **OSNet-x0.25 torchreid re-ID (512-dim, ImageNet pretrained)** → EasyOCR jersey → EventDetector (shot/pass/dribble)

**Feedback loop:** Process game → label possessions → retrain models → Monte Carlo → compare vs lines → record outcomes → repeat

---

## Module Status (Quick Ref)

**All ✅ built — see README.md for full list**

Unbuilt:
- `src/detection/tools/classes.py` 🔲
- `src/visualization/` 🔲 (Phase 14)
- `frontend/` 🔲 (Phase 14)

---

## Dataset Status

| Dataset | Count | Status |
|---------|-------|--------|
| Shot charts | 221,866 shots, 569 players | ✅ |
| PBP | 3,627 / 3,685 (98.4%) | ✅ |
| Player gamelogs | 622 players, 3 seasons | ✅ |
| Hustle / on-off / matchups / synergy | All fetched | ✅ |
| BBRef advanced | 736 players, 3 seasons | ✅ |
| Contracts | 523 players | ✅ |
| Historical lines | 1,225+ games | ✅ |
| Full game CV data | 1 clean (0022400625), 8 dirs total; 10 games reprocessing now | 🟡 Phase G — Session 21 in progress |

---

## Active Issues

| ID | Issue | Status |
|----|-------|--------|
| ISSUE-021 | Wire DATABASE_URL + run 10 full games (Phase G) | 🔴 Active |
| ISSUE-009 | 11 games reprocess — Session 21 in progress; 1/11 done (0022400625 CLEAN); 10 running | 🟡 Reprocess b8ci65tth running — check `data/phase_g_processed.txt` for progress |
| ISSUE-022 | `defender_distance=200.0` sentinel — fix in `unified_pipeline.py` (emits `""`) but 5 pre-fix games still have 200.0 in shot_log.csv: 0022400430, 0022400537, 0022400909, 0022401123, 0022401156 | 🟡 Active — those 5 games need reprocess to patch existing CSVs |
| ISSUE-023 | Shot clock MAE=17.16s — clock doesn't decrement per-frame, resets each possession | ✅ CLOSED 2026-03-25 |
| ISSUE-024 | `0022400852` — tracking ran 393K frames, tracking_data.csv never written; Stage 2 crash (FileNotFoundError); NOT in reprocess list | 🔴 New — needs full reprocess: `scripts/reprocess_failed_games.py --game-ids 0022400852` |
| ISSUE-025 | `feature_engineering.py:683` — `player_name or ""` guard fails for `float(nan)` player names (NaN is truthy); crashes Stage 2 for all games with empty rosters | ✅ FIXED 2026-03-25 — changed to `isinstance(player_name, str)` guard |
| ISSUE-026 | `team_spacing` px² normalization — FIXED. `_SPACING_NORM=4700.0` added, both hull assignments now divide by `(map_w*map_h)/4700`. Backfill ran on 11 games. | ✅ CLOSED 2026-03-25 |
| ISSUE-027 | `0022400710` — video downloaded (CLE@BOS 2025-02-04, 105MB). Reprocess running. | 🟡 Reprocessing |
| ISSUE-028 | `run_clip.py` was missing from `scripts/` — Stage 2 crashed for all games. Restored + added `--data-dir` arg + exit-3 guard. | ✅ CLOSED 2026-03-25 |
| ISSUE-029 | Ball detection 14.1% valid pct — YOLO conf lowered 0.55→0.30, orange guard removed from YOLO path, Hough param2 12→8. Re-test pending. | 🟡 Active — needs test run |
| ISSUE-030 | `0022400852` — 0 rows tracked (gameplay detector failing or homography mismatch). run_clip.py now exits 3 gracefully instead of crashing. Root cause unknown. | 🔴 Active — needs investigation |

All other issues CLOSED — see `vault/Sessions/` for history.

---

## How To Run

```bash
conda activate basketball_ai
cd C:/Users/neelj/nba-ai-system

# Tests (no video)
python -m pytest tests/ -q

# Train win probability
python src/prediction/win_probability.py --train

# Predict a game
python src/prediction/game_prediction.py --predict GSW BOS

# Daily pipeline
python scripts/daily_pipeline.py

# API server
uvicorn api.main:app --reload --port 8000

# Dashboard
streamlit run dashboards/app.py
```

**Never run:** `run.py`, `run_clip.py`, `scripts/loop_processor.py`

---

## Environment

- Python 3.9, conda env: `basketball_ai`
- PyTorch 2.0.1 + CUDA 11.8 + cuDNN 8.9 | RTX 4060 8GB
- YOLOv8n, OpenCV, EasyOCR, nba_api, XGBoost, scikit-learn
- PostgreSQL (schema ready, writes wired Phase 6)

---

## Platform Engineer Protocols

**Session Start Pulse:**
```
• Architecture: <3-word summary>
• Branch: <git branch>
• Last Modified: <3 files>
```

**Navigation breadcrumbs:** `[Module > Submodule > filename.py]`

**Token efficiency rules:**
- Use `# ... existing code ...` for unchanged blocks
- Never re-read large data directories unless asked
- Strip doc comments from code snippets unless editing the docstring

**Autonomous improvement protocol:**
1. Read `CLAUDE.md` open issues
2. Read `tests/` — find failing/missing tests
3. Implement fix (code only, no video runs)
4. Run `pytest tests/`
5. Update CLAUDE.md + STATE.md

**Code rules:** Python 3.9 | modular | max 300 lines/file | docstrings + type hints | save models to `data/` | log in `vault/Improvements/`

---

## Session Log
- Latest: `vault/Sessions/Session-2026-03-25.md`
- Full log: `vault/Sessions/`
