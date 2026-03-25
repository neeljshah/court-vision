# NBA Pipeline — Automated Improvement + Collection Loop

One iteration: download a game → benchmark → fix one issue → run full pipeline → collect all data → write summary.
Be terse. No explanations. Act.

---

## PHASE 1 — Get a video (auto-download if needed)

**Check for existing clips first:**
```bash
ls data/videos/full_games/*.mp4 2>/dev/null | head -5
```

**If no clips exist**, download one now using yt-dlp directly — pick the first available priority matchup from `scripts/full_game_pipeline.py`'s `_PRIORITY_MATCHUPS` list, find its game_id from `data/nba/schedule/`, then run:
```bash
conda run -n basketball_ai python scripts/full_game_pipeline.py --max-frames 500 --dry-run 2>&1 | head -20
```
Then download just one game (replace with actual game from dry-run output):
```bash
conda run -n basketball_ai python scripts/full_game_pipeline.py --max-frames 500 --hours 1 2>&1 | tail -30
```

**If cookies needed** and download fails with bot/sign-in error:
- Note the error, skip download for this iteration, use any existing `.mp4` in `data/videos/` instead.
- If truly no video anywhere, skip Phase 2 and go straight to Phase 3.

Pick one `.mp4` from `data/videos/full_games/` or `data/videos/` as `$CLIP`. Note the game_id (filename without extension, or from `data/games/` folder names).

---

## PHASE 2 — Benchmark + fix one issue

**Benchmark (300 frames, headless):**
```bash
conda run -n basketball_ai bash -c "cd /c/Users/neelj/nba-ai-system && python scripts/run_clip.py --video $CLIP --no-show --frames 300" 2>&1 | tail -20
```

Extract: `fps`, `ball_valid%`, `shots_detected`, `id_switches`, `possessions`.

**Targets:** fps ≥ 20 | ball_valid ≥ 60% | shots ≥ 1 per 2 min of clip | id_switches = 0

**Read the last 80 lines of improvement log only:**
```
vault/Improvements/Tracker Improvements Log.md  (offset to last ~80 lines)
```
Find: worst metric vs target, what was last attempted (don't repeat).

**Apply ONE fix** — edit only the file(s) directly responsible. No refactoring.

**Verify (150 frames):**
```bash
conda run -n basketball_ai bash -c "cd /c/Users/neelj/nba-ai-system && python scripts/run_clip.py --video $CLIP --no-show --frames 150" 2>&1 | tail -10
```

If improved: keep. If not: revert and note "reverted".

---

## PHASE 3 — Run full pipeline (background)

If a full game hasn't been processed today, queue it in background:
```bash
conda run -n basketball_ai python scripts/full_game_pipeline.py \
  --max-frames 3000 --hours 2 --refresh-context 2>&1 &
echo "Full pipeline running in background — PID $!"
```

`--max-frames 3000` = ~100s of gameplay at 30fps, enough for meaningful data without waiting hours.

If already processed today (check `data/full_game_results.json` mtime), skip this.

---

## PHASE 4 — Collect all data sources

Run daily slate (props + injuries + lines + win probs):
```bash
conda run -n basketball_ai python scripts/run_daily_slate.py 2>&1 | tail -50
```

Read the latest output files:
- `data/output/slate_*.json` — most recently modified → top props by EV
- `data/full_game_results.json` — last entry → tracking metrics for any completed full game
- `data/games/` — scan for folders with `predictions.json` → read the 3 most recent

From each `predictions.json` extract:
- `win_probability` for home/away
- Top 3 player props by `edge_pct` or `kelly_fraction`

---

## PHASE 5 — Write summary page

Write to `vault/Sessions/pipeline_summary_YYYY-MM-DD.md` (use actual date).
If the file already exists today, append a new iteration section instead of overwriting.

```markdown
# Pipeline Summary — YYYY-MM-DD  (Iteration N)

## Tracker Health
| Metric       | Before | After  | Target | Status |
|--------------|--------|--------|--------|--------|
| FPS          |        |        | ≥ 20   | ✅/❌  |
| Ball valid % |        |        | ≥ 60%  | ✅/❌  |
| Shots        |        |        | ≥ 1/2m | ✅/❌  |
| ID switches  |        |        | 0      | ✅/❌  |
| Possessions  |        |        | ≥ 5    | ✅/❌  |

## Fix This Iteration
- **File:** `src/tracking/X.py:LINE`
- **Change:** one sentence
- **Result:** ✅ improved / ❌ reverted

## Data Sources
| Source          | Status     | Value              |
|-----------------|------------|--------------------|
| Props (DK/OddsAPI) |         | N lines scraped    |
| Injuries        |            | N active alerts    |
| Schedule        |            | N games today      |
| PBP coverage    |            | N/3685 games       |
| Full game pipeline |         | running/done/skip  |

## Today's Predictions
| Game | Home Win% | Away Win% | Grade |
|------|-----------|-----------|-------|
|      |           |           |       |

## Top Prop Edges
| Player | Stat | Line | Edge% | Kelly% |
|--------|------|------|-------|--------|
|        |      |      |       |        |

## Next Fix
- Worst metric: X (current: X, target: X)
- Likely file: `src/tracking/X.py`
- Approach: one sentence

## Full Game Pipeline
- Status: running in background / completed / skipped
- Game: TEAM vs TEAM (game_id)
- Frames queued: 3000
```

---

## PHASE 6 — Log to improvement log

Append to `vault/Improvements/Tracker Improvements Log.md`:

```
### YYYY-MM-DD — Auto Loop Iteration N
**Clip:** <filename> · 300 frames benchmark
**Metrics:** fps <X>→<X>  ball_valid <X%>→<X%>  shots <X>→<X>  id_sw <X>→<X>
**Fix:** `<file>:<line>` — <what changed> — <kept/reverted>
**Full game:** <queued/already done/skipped>
**Next:** <worst metric and planned approach>
```

---

Print the full summary table inline so the user sees it immediately.
