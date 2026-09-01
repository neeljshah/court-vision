# E2 NBA Sub-Shock Latency Race Results

Status: not run. The pre-manifest eligibility check found zero events with both a qualifying native PBP/stint detection timestamp and a temporally matching line-history window. Per the Phase 2 stop rule, no manifest was created and the race was not executed.

| line-history IDs and dates | native PBP/stint source | native event interval | temporal overlap with retained quotes | eligible events |
| --- | --- | --- | --- | ---: |
| `401859967`, 2026-06-18 through 2026-07-10 | `data/cache/nba_pbp_wallclock_raw/summary/401859967.json` | 2026-06-14T00:43:27Z through 2026-06-14T03:29:26Z | None; first retained quote is 2026-06-18T18:32:04Z, more than four days later | 0 |
| `fd:*`, 2026-07-02 through 2026-07-17 | No matching PBP/stint cache under `data/cache/` | N/A | None | 0 |

Native-timestamp sources checked: `nba_pbp_wallclock_raw`, `team_system/pbp`, `team_system/lineups/stints_2025_26.parquet`, `quarter_box`, `ingame`, `ingame_grade`, `inplay_history`, and `live_bets`. The stints parquet has no native timestamp field, and the only matching ingame-grade record is a postgame settled record, not a PBP/stint detection timestamp.

Manifest: `C:/Users/neelj/nba-ai-system/data/cache/team_system/subshock_events.jsonl` was absent before and remains absent. No files were written to the main repository.

FAIL: INSUFFICIENT_ELIGIBLE_EVENTS (0 < 30); race not run.
