---
phase: quick
plan: 2
type: execute
wave: 1
depends_on: []
files_modified:
  - CLAUDE.md
autonomous: false
requirements: [QUICK-2]

must_haves:
  truths:
    - "3600-frame benchmarks complete on all 4 clips"
    - "gsw_lakers and cavs_vs_celtics report ball_valid_live and ball_valid_dead (PBP mask active)"
    - "ball_valid >= 80% on gsw_lakers_2025"
    - "CLAUDE.md Open Priority Issues updated with new ball_valid numbers and build_live_mask note"
  artifacts:
    - path: "data/benchmarks/report_*.json"
      provides: "benchmark results for each clip"
    - path: "data/nba/pbp_0022401117.json"
      provides: "GSW vs Lakers PBP cache enabling live mask on that clip"
  key_links:
    - from: "_bench_run.py --game-id"
      to: "build_live_mask()"
      via: "nba_enricher.build_live_mask"
      pattern: "ball_valid_live.*ball_valid_dead"
---

<objective>
Run 3600-frame benchmarks across all 4 tracked clips with the Guard 2/3 fixes and vision fallback
now in place. Fetch the missing gsw_lakers PBP (0022401117) so the live/dead mask fires on that
clip too. Record final ball_valid numbers and update CLAUDE.md.

Purpose: Validate that the quick-1 infrastructure (build_live_mask, vision fallback, Guard 2 skip)
delivers the target ≥80% ball_valid on gsw_lakers and captures live vs dead split for all game-id
clips.

Output: Benchmark JSONs in data/benchmarks/, updated CLAUDE.md with final numbers.
</objective>

<execution_context>
@C:/Users/neelj/.claude/get-shit-done/workflows/execute-plan.md
@C:/Users/neelj/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/quick/1-ball-valid-80pct-nba-api-live-mask-guard/1-SUMMARY.md

Infrastructure completed in quick-1:
- `build_live_mask(game_id)` in `src/data/nba_enricher.py` — reads pbp_{game_id}.json, marks frames live/dead/unknown
- `_ball_track_suspended` vision fallback in `src/pipeline/unified_pipeline.py` — fires when `_sc_ever_seen=False`, ball absent 20+ frames, <8 persons
- `_bench_run.py` default --frames=3600, reports ball_valid_live / ball_valid_dead when --game-id set
- Guard 2 `not _bbox_from_hough` condition confirmed present in `ball_detect_track.py`

Clip registry (from _bench_run.py):
  gsw_lakers_2025     → game_id 0022401117   (PBP NOT yet cached)
  cavs_vs_celtics_2025 → game_id 0022400710  (PBP cached ✅)
  bos_mia_2025        → game_id 0022400307   (PBP likely not cached)
  mia_bkn_2025        → game_id None         (no live mask possible)

Latest 600-frame baselines (end of last session):
  gsw_lakers_2025     80% ball_valid, jump_resets=206
  bos_mia_playoffs    26.7%, jump_resets=197
  mia_bkn_2025        31.2%, jump_resets=265
  cavs_broadcast_2025 34%, jump_resets=257
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fetch gsw_lakers PBP + run 3600-frame benchmarks on game-id clips</name>
  <files>data/nba/pbp_0022401117.json</files>
  <action>
Fetch the missing GSW vs Lakers PBP so build_live_mask fires on that clip.

In a Python shell or one-off script (do NOT call the season-wide scraper, only one game):

```python
import sys; sys.path.insert(0, "C:/Users/neelj/nba-ai-system")
from src.data.pbp_scraper import scrape_game_pbp
rows = scrape_game_pbp("0022401117", force=False)
print(f"GSW PBP: {len(rows)} rows cached")
```

Verify data/nba/pbp_0022401117.json exists and is non-empty before continuing.

Then run 3600-frame benchmarks on the two game-id clips:

```bash
cd C:/Users/neelj/nba-ai-system
conda run -n basketball_ai python _bench_run.py --video gsw_lakers_2025 --frames 3600 --game-id 0022401117
conda run -n basketball_ai python _bench_run.py --video cavs_vs_celtics_2025 --frames 3600 --game-id 0022400710
```

Record from output:
- gsw_lakers: ball_valid_pct, ball_valid_live, ball_valid_dead, suspended_frames, jump_resets
- cavs_vs_celtics: same fields

Expected: gsw ball_valid_pct >= 0.80 (600-frame baseline was 80%).
If cavs_vs_celtics ball_valid_pct < 0.40 after 3600 frames, note but do not try to fix in this task.
  </action>
  <verify>
    <automated>python -c "import json, glob, os; reports=sorted(glob.glob('C:/Users/neelj/nba-ai-system/data/benchmarks/report_*.json')); clips=[json.load(open(f))['clip'] for f in reports[-6:]]; print(clips); assert 'gsw_lakers_2025' in clips and 'cavs_vs_celtics_2025' in clips, 'Missing clips'"</automated>
  </verify>
  <done>
    Both gsw_lakers_2025 and cavs_vs_celtics_2025 have 3600-frame benchmark reports.
    pbp_0022401117.json exists and is non-empty.
    ball_valid_live and ball_valid_dead appear in the gsw_lakers report.
  </done>
</task>

<task type="auto">
  <name>Task 2: Run 3600-frame benchmarks on bos_mia + mia_bkn</name>
  <files></files>
  <action>
Run benchmarks on the two remaining clips (no --game-id for mia_bkn, check if bos_mia_2025 PBP is cached):

```bash
cd C:/Users/neelj/nba-ai-system

# Check if bos_mia PBP is cached (game_id 0022400307)
python -c "import os; print(os.path.exists('data/nba/pbp_0022400307.json'))"

# Run bos_mia — add --game-id only if cache confirmed True above
conda run -n basketball_ai python _bench_run.py --video bos_mia_2025 --frames 3600 --game-id 0022400307
# (If PBP not cached, omit --game-id flag)

conda run -n basketball_ai python _bench_run.py --video mia_bkn_2025 --frames 3600
```

Record from output:
- bos_mia_2025: ball_valid_pct, suspended_frames, jump_resets, ball_valid_live (if game_id present)
- mia_bkn_2025: ball_valid_pct, suspended_frames, jump_resets

Note any clips still below 50% — these are candidates for further tracker work, NOT to be fixed in this task.
  </action>
  <verify>
    <automated>python -c "import json, glob; reports=sorted(glob.glob('C:/Users/neelj/nba-ai-system/data/benchmarks/report_*.json')); clips=[json.load(open(f))['clip'] for f in reports[-8:]]; print(clips)"</automated>
  </verify>
  <done>
    bos_mia_2025 and mia_bkn_2025 have 3600-frame benchmark reports.
    All 4 clips now have 3600-frame baselines recorded.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <what-built>
    3600-frame benchmarks for all 4 clips. build_live_mask active on gsw_lakers and cavs_vs_celtics.
    All ball_valid numbers for the new baseline.
  </what-built>
  <how-to-verify>
    Collect the final numbers from the benchmark output above and confirm:
    1. gsw_lakers_2025 ball_valid_pct >= 0.80 (target met)
    2. ball_valid_live / ball_valid_dead appear for gsw_lakers and cavs_vs_celtics
    3. Note actual numbers for all 4 clips (will go into CLAUDE.md)

    Provide the 4 ball_valid numbers so Task 4 can write them accurately.
  </how-to-verify>
  <resume-signal>Type the 4 ball_valid numbers: "gsw=X bos=X cavs=X mia=X" or "approved" with numbers in your message</resume-signal>
</task>

<task type="auto">
  <name>Task 4: Update CLAUDE.md with new ball_valid baseline + build_live_mask note</name>
  <files>CLAUDE.md</files>
  <action>
Update CLAUDE.md in two places:

1. **Open Priority Issues section** (near top of file) — update the ball tracking status line.
   Find the line referencing ball tracking / CV tracker quality and add the new baseline:
   ```
   4. 🟡 Ball tracking baseline (3600 frames): gsw={X}% / bos_mia={X}% / cavs_broad={X}% / mia_bkn={X}%
      build_live_mask() active — live vs dead split now in bench reports
   ```
   (Use the actual numbers from the checkpoint.)

2. **Known Issues table** — add a new entry if not already present:
   ```
   | ISSUE-023 | Ball valid <50% on bos_mia/mia_bkn/cavs_broadcast | 🟡 Active — 3600-frame baseline established 2026-03-18; Guard 2/3 + vision fallback in place; next: jump_resets root cause |
   ```
   (Only add if ball_valid < 0.50 on those clips.)

3. **Session Log section** (if present near top): update "Last Updated" date and note build_live_mask done.

Do NOT change any other sections. Preserve all existing content.
  </action>
  <verify>
    <automated>python -c "content=open('C:/Users/neelj/nba-ai-system/CLAUDE.md').read(); assert 'build_live_mask' in content, 'Missing build_live_mask note'; print('CLAUDE.md updated OK')"</automated>
  </verify>
  <done>
    CLAUDE.md contains the 4 ball_valid numbers from the 3600-frame benchmarks.
    build_live_mask() referenced in Open Priority Issues or Known Issues.
  </done>
</task>

</tasks>

<verification>
After all tasks:

```bash
# Confirm all 4 clips have 3600-frame benchmark reports
python -c "
import json, glob
reports = sorted(glob.glob('C:/Users/neelj/nba-ai-system/data/benchmarks/report_*.json'))
clips_3600 = [(json.load(open(f))['clip'], json.load(open(f)).get('frames_requested'), json.load(open(f))['summary'].get('ball_valid_pct')) for f in reports[-10:] if json.load(open(f)).get('frames_requested', 0) >= 3600]
for clip, frames, bv in clips_3600:
    print(f'{clip}: {bv:.1%} ({frames} frames)')
"

# Confirm gsw PBP cached
python -c "import os; print('gsw PBP cached:', os.path.exists('C:/Users/neelj/nba-ai-system/data/nba/pbp_0022401117.json'))"

# Confirm CLAUDE.md has build_live_mask
python -c "c=open('C:/Users/neelj/nba-ai-system/CLAUDE.md').read(); print('build_live_mask in CLAUDE.md:', 'build_live_mask' in c)"
```
</verification>

<success_criteria>
- 4 benchmark reports at 3600 frames (gsw, cavs_vs_celtics, bos_mia, mia_bkn)
- gsw_lakers_2025 ball_valid_pct >= 0.80 at 3600 frames
- gsw_lakers and cavs_vs_celtics reports include ball_valid_live and ball_valid_dead fields
- CLAUDE.md updated with actual ball_valid numbers and build_live_mask note
- Tests still pass: pytest tests/test_hardening.py tests/test_phase2.py -q
</success_criteria>

<output>
After completion, create `.planning/quick/2-ball-valid-80pct-nba-live-mask-guard2-gu/2-SUMMARY.md`
with the standard summary format: what was built, commits, metrics (ball_valid per clip), deviations.
</output>
