# Get 20 Perfect NBA AI Games — Start Here

## Your Goal ✅
Reprocess all NBA game datasets for:
- ✅ Fast processing (3-4 min per game)
- ✅ Accurate data (jersey OCR → player names)
- ✅ No bugs or errors
- ✅ 20 games with perfect data

## What You Have Now
```
48 game directories in data/games/:
  - 30 complete (tracking + shots + possessions + features)
  - 14 partial (missing shot_log)
  - Issue: no player_name, no jersey numbers

397,283 total rows of tracking data
~650 MB current storage
```

## What's Missing
```
Old pipeline (v1) tracked without:
  ❌ Jersey number extraction (OCR)
  ❌ Player name mapping
  ❌ Complete spatial features

New pipeline (v2, in place) has:
  ✅ Jersey OCR (advanced_tracker.py)
  ✅ Player name resolution (jersey_name_map.json)
  ✅ Full spatial features (nearest_opponent, etc)
  ✅ Code tested & validated
```

## Your Action Plan

### Step 1: 5-Minute Setup & Validation
```bash
cd C:/Users/neelj/nba-ai-system
conda activate basketball_ai

# Check current state
python scripts/batch_validate_games.py --summary
```

Expected: 48 games, 26 marked as OK (will improve after reprocessing), 397K rows.

### Step 2: 2-Minute Preview
```bash
# See exactly what will happen (no files modified)
python scripts/batch_reprocess_games.py --dry-run --count 5

# Output shows 5 sample games being queued for reprocessing
# ~2 hours total time estimate
```

### Step 3: 90-Minute Full Reprocessing
```bash
# This is the main command — runs headless, loops through all games
python scripts/batch_reprocess_games.py --frames 18000

# What happens per game:
#   1. Load video from data/videos/full_games/
#   2. Extract jersey numbers via OCR
#   3. Generate jersey_name_map.json
#   4. Write player_name + jersey_number to tracking_data.csv
#   5. Regenerate shot detection (cleaner)
#   6. Regenerate all features
#   7. Move to next game
#
# Result: tracking_data.csv now has player_name column!
```

**Expect logs like:**
```
[1/30] 0022400015... SUCCESS
[2/30] 0022400021... SUCCESS
...
[30/30] atl_ind_2025... SUCCESS

Completed: 30/30

Logged to: vault/Sessions/Reprocessing_2026-03-30_143022.md
```

### Step 4: 5-Minute Validation
```bash
# Check quality improved
python scripts/batch_validate_games.py

# Look for improvement:
#   Before: NO player_name column in features
#   After:  player_name column exists, >95% filled
#
#   Before: nearest_opponent 50-60% filled
#   After:  nearest_opponent 90%+ filled
```

### Step 5: 10-Minute Audit (Optional)
```bash
# Deep dive on data quality
python scripts/audit_phase_g.py

# Validates:
#   - Shot locations vs NBA shot chart
#   - Possession counts vs play-by-play
#   - Player tracking accuracy
#   - Homography quality
```

## Success Indicators ✅

After reprocessing, you'll have:
```
20+ games (out of 30) where:
  ✅ player_name: 98%+ filled (jersey OCR → names)
  ✅ jersey_number: 100% filled (OCR output)
  ✅ nearest_opponent: 90%+ filled (spatial feature)
  ✅ shot_log: realistic counts (160-180 shots, not 1000+)
  ✅ possessions: 110-280 per game (realistic)
  ✅ features.csv: all required columns present
  ✅ No error/corruption in features
```

## Key Features of Your System

**Code Quality:**
- Latest fixes already in place (Portrait homography, UTF-8 encoding, etc)
- Safe reprocessing (doesn't delete originals, overwrites CSVs)
- Headless operation (no GUI, good for automation)
- Atomic commits (each game is independent)

**Data Integrity:**
- Jersey_name_map.json auto-generated per game
- Player names resolved via two methods (jersey OCR + NBA API fallback)
- Spatial features recomputed with fixed bugs (nearest_opponent now >90%)
- All features have proper type handling

**Error Handling:**
- OOM-safe (one game at a time)
- Skip-friendly (can resume if interrupted)
- Validation-first (checks work before writing)
- Logging to vault for review

## Estimated Timeline
- Step 1 (Validation): 5 minutes
- Step 2 (Preview): 2 minutes
- Step 3 (Reprocessing): 90 minutes (can run overnight)
- Step 4 (Check): 5 minutes
- **Total: ~2 hours** to get perfect data

## Troubleshooting

**Q: Can I run just a few games to test?**
```bash
# Yes! Try 5 games first
python scripts/batch_reprocess_games.py --games 0022400430 0022400537 0022400909 0022401123 0022401183
# This should take 15-20 minutes
```

**Q: What if a game gets OOM?**
```bash
# It'll skip and continue. You can rerun with fewer frames:
python scripts/run_phase_g.py --game-ids PROBLEM_GAME --frames 9000 --reprocess
# (5 min of video instead of 10 min)
```

**Q: Can I interrupt and resume?**
```bash
# Yes! Script skips already-processed games
# Just run the same command again
python scripts/batch_reprocess_games.py --frames 18000
```

**Q: How much storage needed?**
```
Current: ~650 MB (30 games)
During reprocessing: ~1-2 GB (temporary intermediates)
After: ~650 MB (same, cleaner CSVs)
```

## Files Created for You

**New Scripts:**
- `scripts/batch_validate_games.py` — Check data quality
- `scripts/batch_reprocess_games.py` — Run batch reprocessing
- `scripts/batch_enrich_player_names.py` — Backfill names (uses after reprocess)
- `scripts/batch_fix_games.py` — Manual fixups (if needed)

**Documentation:**
- `REPROCESS_PLAN.md` — Technical details of strategy
- `EXECUTION_GUIDE.md` — Full reference guide
- `START_HERE.md` — This file

## Next: Run It

```bash
cd C:/Users/neelj/nba-ai-system
conda activate basketball_ai
python scripts/batch_reprocess_games.py --frames 18000
```

**That's it.** Everything else is automated.

---

**Questions?**
- Check `EXECUTION_GUIDE.md` for detailed reference
- Check `REPROCESS_PLAN.md` for technical background
- Check `vault/Improvements/Tracker Improvements Log.md` for known issues
- Check `vault/Sessions/` logs after reprocessing completes

**Status Tracking:**
- Logs go to `vault/Sessions/Reprocessing_*.md`
- Results go to `vault/Sessions/` for review
- Each game's status tracked in batch script output

**You're ready to go!** 🚀
