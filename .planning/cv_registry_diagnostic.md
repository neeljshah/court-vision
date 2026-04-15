# CV Registry Sparsity Diagnostic
Generated: 2026-04-15

## Summary

24 player-game records across 6 games in the CV registry (per CLAUDE.md) vs
29 tracking dirs. The sparsity is **entirely due to missing `jersey_name_map.json`**
— not OCR failure.

## Jersey OCR Resolution by Game

| game_id     | jersey slots | resolved | rate |
|-------------|-------------|----------|------|
| 0022400625  | 27          | 27       | 100% |
| 0022400687  | 25          | 25       | 100% |
| 0022400690  | 23          | 23       | 100% |
| 0022400710  | 30          | 30       | 100% |
| 0022400852  | 30          | 30       | 100% |
| 0022400909  | 24          | 24       | 100% |
| 0022400923  | 24          | 24       | 100% |
| 0022401156  | 26          | 26       | 100% |
| 0022401183  | 27          | 27       | 100% |
| 0022401185  | 24          | 24       | 100% |
| **TOTAL**   | **260**     | **260**  | **100%** |

**19 games have NO jersey_name_map.json** (no PlayerResolver → no OCR attempted):
`0022400689, 0022400921, 0022500002, 0022500033..0022500046, 0022500061, 0022500585`

## Root Cause

`PlayerResolver` only runs when `--game-id` is passed to the pipeline (line 652-656
in unified_pipeline.py). The 19 games without maps were processed without `--game-id`,
so OCR was never attempted.

When `--game-id` IS provided:
- Resolution rate = **100%** (260/260 slots across 10 games)
- jersey chain resolution works correctly

## Failure Mode Breakdown

| Mode                  | Count |
|-----------------------|-------|
| No jersey_name_map.json (no `--game-id`) | 19 |
| Empty map             | 0     |
| Partial (<50% resolved)| 0    |
| Full (>=50% resolved) | 10    |

## Resolution

Pass `--game-id` to all future Phase G pipeline runs. This requires:
1. Mapping video filenames (e.g., `0022500033.mp4`) to NBA game IDs (they already ARE game IDs).
2. Including `--game-id $GAMEID` in `scripts/launch_single_gpu_pod.sh` batch loop.

The OCR quality itself is excellent — sparsity is purely a pipeline invocation issue.
