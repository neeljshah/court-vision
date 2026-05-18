# NBA AI System — 20 Perfect Games Execution Guide

## Current State
- **30 complete games** (all 4 processing stages done)
- **14 partial games** (missing shot_log.csv)
- **Total 48 games** in data/games/

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
Total games: 48
Complete & OK: ~26 (will improve after reprocessing)
Games with issues: 48 (missing player_name, etc)
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
# Process all 30 complete games (runs headless, no GUI)
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
- **Total time**: ~30 games × 3 min = 90 minutes
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
| 3 | ~90 min | Reprocess all 30 games |
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
