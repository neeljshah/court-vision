# NBA AI System — 20 Perfect Games Execution Guide

## Current State
- **8 complete games** (all 4 processing stages done)
- **16 partial games** (missing shot_log.csv)
- **Total 24 games** in data/games/

## What We're Doing
Reprocessing all games with the **latest tracking pipeline** which includes:
✅ Jersey number extraction via OCR
✅ Player name resolution (jersey → player_name mapping)
✅ Spatial feature recomputation (nearest_opponent, handler_isolation)
✅ Shot detection regeneration
✅ Features.csv with all required columns + player_name

## Phase 1: Quick Validation (5 min)
```bash
cd /path/to/nba-ai-system
conda activate basketball_ai

# Check what we have
python scripts/batch_validate_games.py --summary
```

Expected output:
```
Total games: 24
Complete & OK: ~8 (will improve after reprocessing)
Games with issues: 24 (missing player_name, etc)
Total rows processed: 397,283
```

## Phase 2: Preview Reprocessing (2 min dry-run)
```bash
# See what will happen (no files modified)
python scripts/batch_reprocess_games.py --dry-run --count 5
```

Output shows:
- 5 games will be reprocessed
- ~2 hours total estimated time
- Exactly which run_phase_g.py commands would execute

## Phase 3: Full Reprocessing (1-2 hours)
```bash
# Process all 8 complete games (runs headless, no GUI)
python scripts/batch_reprocess_games.py --frames 18000

# This will:
# 1. Loop through all games that need it
# 2. Call run_phase_g.py --reprocess for each
# 3. Generate jersey_number + player_name
# 4. Regenerate shot_log.csv (cleaner detection)
# 5. Regenerate features.csv with all columns
# 6. Log results to vault/Sessions/Reprocessing_*.md
```

If you get OOM on a game, the script skips it and continues. OOM games need special handling (one at a time with smaller frame count).

## Phase 4: Validate Results (5 min)
```bash
# Check quality after reprocessing
python scripts/batch_validate_games.py

# Look for:
# ✅ player_name: >95% filled (was 0%)
# ✅ nearest_opponent: >90% filled (was 50%)
# ✅ shot_log.csv: realistic counts (160-180 per game)
# ✅ No "missing cols" errors
```

## Phase 5: Audit Top Games (10 min)
```bash
# Deep dive on 5 random games
python scripts/audit_phase_g.py

# Compares your data vs NBA stats:
# - Shot locations vs NBA shot chart
# - Possession counts vs play-by-play
# - Team spacing vs court geometry
# - Player identity accuracy
```

## Success Criteria (20 Games)
```
After reprocessing, you should have:

✅ 20+ games with:
   - player_name: 98%+ filled
   - nearest_opponent: 90%+ filled
   - ft_x / ft_y: 100% filled
   - team_abbrev: 100% filled
   - shot_log: realistic counts (no 300+ shots)
   - possessions: 110-280 per game

✅ All files present:
   - tracking_data.csv
   - shot_log.csv
   - possessions.csv
   - features.csv
   - jersey_name_map.json

✅ No errors in feature engineering
✅ Audit pass on 5 sample games
```

## Important Notes

### Safety
- Run in conda environment (all deps isolated)
- Runs headless (`--no-show` flag, no GUI windows)
- Each game reprocesses independently
- Original data backed up automatically
- Can interrupt and resume (skip processed games)

### Performance
- **Per-game time**: 3-4 minutes on RTX 4060 (18K frames)
- **Total time**: ~8 games × 3 min = 24 minutes
- **Memory**: Runs 1 game at a time (safe for 8GB+)
- **Storage**: ~1-2 GB per game (cleanup old intermediates if needed)

### Troubleshooting

**If a game fails:**
```bash
# Rerun just that game (with verbose output)
python scripts/run_phase_g.py --game-ids 0022400430 --frames 9000 --reprocess
```

**If you get OOM:**
```bash
# Reduce frames (5 min instead of 10 min)
python scripts/run_phase_g.py --game-ids 0022400430 --frames 9000 --reprocess
```

**If tracking looks wrong:**
- Check `vault/Improvements/Tracker Improvements Log.md` for known issues
- Compare homography_valid column (0.0 = bad video/cuts, 1.0 = good)
- If homography_valid <0.5, video might be highlights reel (not full game)

## Commands Quickref

```bash
# Activate environment
conda activate basketball_ai
cd /path/to/nba-ai-system

# Validate current state
python scripts/batch_validate_games.py --summary

# Preview reprocessing
python scripts/batch_reprocess_games.py --dry-run --count 5

# Run full batch (1-2 hours)
python scripts/batch_reprocess_games.py --frames 18000

# Reprocess specific games only
python scripts/batch_reprocess_games.py --games 0022400430 0022400537 0022400909

# Deep audit
python scripts/audit_phase_g.py

# View session log
ls -lt vault/Sessions/ | head
cat vault/Sessions/Reprocessing_*.md
```

## Expected Timeline

| Phase | Time | Action |
|-------|------|--------|
| 1 | 5 min | Validate current state |
| 2 | 2 min | Preview with dry-run |
| 3 | ~24 min | Reprocess all 8 games |
| 4 | 5 min | Post-processing validation |
| 5 | 10 min | Audit sample games |
| **Total** | **~2 hours** | Get 20+ perfect games |

## After Reprocessing

Your data will be ready for:
- ✅ Model training (player_name enables roster matching)
- ✅ Spatial feature analysis (nearest_opponent, spacing)
- ✅ Possession simulator (clean shot + possession data)
- ✅ Analytics dashboard (accurate player tracking)
- ✅ Betting predictions (high-quality input data)

## Notes

- All scripts run **headless** (no GUI) — good for remote/background use
- Scripts **log to vault** for review + debugging
- Can run multiple instances in parallel if needed (they coordinate via file locks)
- Safe to interrupt (scripts skip already-processed games)
- Results are **reproducible** (same code + same video = same output)

---

# Predictions -> Sized Bets (Execution Pipeline)

The second half of this guide is the **execution** path: how a calibrated
prediction becomes a sized, recorded *paper* bet. It is paper-only and
units-only by construction; real money is human-gated (see the gate at the end).
The math and decision rules live in [BETTING](BETTING.md) and
[decisions](decisions.md); this section is the operational runbook.

## The pipeline at a glance

```
prediction  ->  devig + line-shop  ->  edge/EV  ->  tier floor + dual gate
            ->  units-only Kelly    ->  ledger (paper)  ->  settle  ->  CLV
```

| Stage | Module | Output |
|---|---|---|
| Edge rows from the slate | `run_daily_slate.py` | `slate_YYYYMMDD.json` (`top_edges`) |
| Select + size | `src/prediction/bet_selector.py::select` | `bets_YYYYMMDD.json` (status `paper`) |
| Pure decision (units only) | `frontend/exec_decision.py::decide_game` | per-row `decision`, `tier`, `stake_units` |
| Record placement | `src/betting/pnl_ledger.py::place_bet` | row in `data/pnl_ledger.csv` |
| Settle | `pnl_ledger.settle_bet` / `auto_settle_date` | won/lost/push + bankroll move |
| Enrich + score CLV | `src/betting/clv.py::enrich_pnl_with_clv` | `data/pnl_ledger_clv.csv` |
| Aggregate | `clv.aggregate_clv` / `pnl_summary` | beat-close rate, CLV vs ROI corr |

## Step 1 -- Select and size (paper)

```bash
# LIVE_BETTING must be 0 -- bet_selector exits non-zero otherwise.
LIVE_BETTING=0 python -m src.prediction.bet_selector --date 2026-06-18 --dry-run
```

What the selector enforces, in order (`bet_selector.select`):

1. **Edge threshold** -- `|edge| >= edge_min` (default `0.04`).
2. **Stat-direction / policy filters** -- drop zero-edge directions (e.g. BLK
   OVER) and apply the active `CV_BET_POLICY` per-stat floors, closing-line caps,
   and the **playoff-AST regime guard**.
3. **Dual CLV gate** -- also require predicted CLV > `clv_min` (~1.5%); skipped
   gracefully if `clv_predictor.pkl` is untrained.
4. **Exposure caps** -- `max_bets_per_game`, per-player combined cap
   (`max_combined_pct`), correlation-aware quarter-Kelly via `kelly_corr`.
5. **Timing** -- bets the timing optimiser says to delay are diverted to
   `bet_timing_queue.json` rather than emitted now.

Below any floor the candidate is simply **not selected** -- no-bet is the common,
intended result.

## Step 2 -- Record the placement (no API)

The operator places any real wager manually, then records it. No sportsbook API
is touched.

```bash
python -c "from src.betting.pnl_ledger import place_bet; \
print(place_bet(game_id='0022501001', player='Role Player', stat='ast', \
line=4.5, side='OVER', book='DK', odds=-110, stake=1.0, model_pred=5.2))"
```

`stake` here is a **unit count**, not dollars. Writes are atomic (tmpfile +
`os.replace`) under a sidecar lockfile, so concurrent writers cannot corrupt
`data/pnl_ledger.csv`.

## Step 3 -- Settle and score CLV

```bash
# Settle every open bet placed on a date, using cached gamelog actuals:
python -c "from src.betting.pnl_ledger import auto_settle_date; \
print(auto_settle_date('2026-06-18'))"

# Join settled bets to closing-line snapshots and write the CLV-enriched ledger:
python -c "from src.betting.clv import enrich_pnl_with_clv; \
rows = enrich_pnl_with_clv(); \
from src.betting.clv import aggregate_clv; print(aggregate_clv(rows))"
```

CLV is **positive when you held a better number than the close** (side-aware;
see [BETTING](BETTING.md) for the sign convention and the `CV_CLV_LINE_SIGN_FIX`
gate). The honesty metric to watch is `clv_vs_roi_corr` -- CLV should predict
realized ROI; if it does not, the "edge" is variance.

## Success criteria (execution layer)

```
- bets_YYYYMMDD.json written with status=paper (never pending/live)
- every emitted row carries a tier in {A,B,C} and stake_units > 0
- below-floor candidates absent from the file (no-bet, not a token bet)
- pnl_ledger.csv rows balance against pnl_bankroll.csv
- pnl_ledger_clv.csv has a closing snapshot for the bulk of settled bets
- aggregate_clv reports beat_close_rate and a non-null clv_vs_roi_corr
```

## The real-money gate (human-gated)

`LIVE_BETTING=0` is hard-enforced in `bet_selector.py`. Live capital is unlocked
**only by a human**, and only after the full evidence gate in
[risk-framework](risk-framework.md) passes simultaneously: >=50 settled paper
bets, CLV beat rate >=55%, paper ROI >=3%, calibration drift <10% per stat,
backtest ROI >= 0.7x paper, and zero circuit-breaker events in the last 7 days.
A partial pass unlocks nothing. The defensible win is a recorded positive-CLV
track record -- not a dollar ROI claim.

See also: [BETTING](BETTING.md)  -  [decisions](decisions.md)  - 
[risk-framework](risk-framework.md)  - 
[architecture/execution-engine](architecture/execution-engine.md)  - 
[label_strategy](label_strategy.md).


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
