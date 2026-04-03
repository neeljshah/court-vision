# NBA AI Games Reprocessing Plan

## Current State
- **30 complete games** (tracking + shots + possessions + features)
- **14 partial games** (missing shot_log.csv)
- **48 total game directories** in `data/games/`

## Data Quality Issues
1. **No player_name column** — Old games tracked without jersey OCR (Phase G v1)
2. **No jersey_number column** — Not extracted during tracking
3. **nearest_opponent <60% filled** on many games — Spatial feature gaps
4. **Missing shot_log.csv** on 14 games — Need to re-run event detection

## Reprocessing Strategy (Efficient)

### Phase 1: Code Validation (no video)
✅ Verify current pipeline includes:
- Jersey OCR (advanced_tracker.py)
- Jersey→player_name mapping (jersey_name_map.json)
- Player_name write-through to tracking_data.csv
- Spatial feature computation (nearest_opponent)
- Features.csv with all required columns

### Phase 2: Video-Based Reprocessing
Run games in sequence:
```bash
python scripts/run_phase_g.py --game-ids GAME_ID --frames 18000 --reprocess
```

This will:
1. Reload video from data/videos/full_games/GAME_ID.mp4
2. Re-run tracking pipeline (YOLOv8 → SIFT → Jersey OCR)
3. Generate jersey_name_map.json
4. Write player_name to tracking_data.csv
5. Regenerate shot detection
6. Regenerate all features

### Phase 3: Validation
Run audit for each game:
```bash
python scripts/audit_phase_g.py --game-id GAME_ID
```

Check:
- player_name fill rate >95%
- nearest_opponent fill rate >90%
- shot_log row count ~160-180 (realistic count)
- possessions row count ~110-280 (realistic range)
- features.csv has all required columns

## Batch Execution

### Games to Reprocess (Priority Order)
**High Priority (most complete):**
- 0022400430, 0022400537, 0022400909 — 3 early large games
- 0022401123, 0022401183 — 2 recent medium games

**Medium Priority (complete but need jersey data):**
- 0022400625, 0022400687, 0022401185, 0022401190, 0022401196, 0022401198
- atl_ind_2025, bos_mia_2025, den_phx_2025, lal_sas_2025, mil_chi_2025

**Low Priority (custom/test games):**
- cavs_gsw_2016_finals_g7, bos_mia_playoffs, den_gsw_playoffs, etc.

## Expected Results

### After Reprocessing (Per Game)
- tracking_data.csv: +player_name column, +jersey_number column (100% filled)
- shot_log.csv: Regenerated with accurate counts (160-180 per game)
- possessions.csv: Regenerated with correct timing
- features.csv: All columns + player_name + nearest_opponent >90% filled

### Success Criteria (20 Games)
- 20 games with all 4 stages complete (tracking + shots + poss + features)
- player_name: >98% filled in all games
- nearest_opponent: >90% filled
- shot_log: realistic counts vs game-time shot logs
- No OOM errors (run 1 game at a time)
- Processing time: ~2-4 min per game on RTX 4060

## Implementation Steps

1. **Verify current code** ✅
   - advanced_tracker.py has jersey OCR
   - jersey_name_map generation in place
   - player_name write-through in unified_pipeline.py
   - features.csv generation includes player_name

2. **Create batch runner**
   - Loop through games in sequence
   - Catch + skip OOM games
   - Log success/failure per game
   - Save metrics to vault

3. **Run reprocessing**
   - Start with 5 high-priority games
   - Validate each
   - Expand to all 30+ as confidence grows

4. **Final validation**
   - Run batch_validate_games.py
   - Audit top 20 games
   - Document data quality metrics

## Storage Estimate
- Per game: ~500MB-1GB (tracking data + intermediates)
- 30 games: ~15-30GB (current: ~650MB)
- Safe max: Keep original tracking CSVs, overwrite shot_log + features

## Time Estimate
- 5 games × 3 min/game = 15 min (quick validation)
- 30 games × 3 min/game = 90 min (full batch)
- Can parallelize 2 games if memory available

## Notes
- Run in `conda activate basketball_ai` environment
- Use `--no-show` flag (headless mode per feedback)
- Log failures to vault/Sessions/ for review
- Stop if OOM — that game needs one-at-a-time processing
