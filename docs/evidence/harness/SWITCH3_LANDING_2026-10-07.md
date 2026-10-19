# ADOPTION SWITCH 3 (ncaaf since 2026-10-10) -- landing memo, 2026-10-07

PAPER ONLY. The owner decided this dated config row on 2026-10-05 (S739). No flag is flipped.

## What changed (3 files, re-applied onto master c0a6f0064 as branch adopt/ncaaf-2026-10-10-r5)
- `docs/operations/paper_desk_config.json`: `sports` gains `ncaaf` (now mlb, nba, ncaaf, nfl, soccer, tennis);
  `sports_since.ncaaf = 2026-10-10`; books capture argv gains `--sports mlb,soccer,tennis,nba,wnba,nfl,ncaaf`.
  Every other master value is unchanged: switch 1 and 2 rows (nba/soccer 2026-10-07, tennis 2026-10-08),
  S785 `timeouts_s.watchdog` 180, the S779 fill_realism pin, and the existing state2 argv.
- `tests/platformkit/ops/test_paper_desk_start.py`: the expected books argv includes the new `--sports` list.
- `tests/platformkit/ops/test_s709_desk_root.py`: CONFIG_SHA re-pinned. The test hashes the config bytes after
  CRLF -> LF with sha256. New pin: `f4ab74665f47689369c4dc81741bb70057347c7626586dae5537e4424d4f2308`
  (it was `cd01a3a5...c0ff` on master). The value was computed from the file, not guessed.

The r4 tip 6b99f87bb was on an older base. A plain rebase stalled, so the commit was cherry-picked onto master.
Only the CONFIG_SHA line conflicted; it was resolved by taking master's file and re-pinning it.

## When it takes effect
- `sports` and `sports_since` take effect for the desk's dated scope from 2026-10-10.
- The books argv takes effect ONLY at the next books capture restart. The dispatcher runs that restart on
  2026-10-08 between 08:45Z and 11:45Z, not today. Until then the running books capture keeps its old argv.

## Tests (one file per process, free RAM 4164-4699 MB before each file)
| file | result |
|---|---|
| ops/test_s709_desk_root.py (master baseline, before the change) | 36 passed |
| ops/test_s709_desk_root.py | 36 passed |
| ops/test_paper_desk_start.py | 34 passed |
| ingame/test_s739_ncaaf_scope.py | 6 passed |
| ingame/test_s561_live_window.py | 42 passed |
| ingame/test_wnba_registration.py | 45 passed |
| ops/test_paper_desk_scope_s736.py | 14 passed |
| ops/test_paper_desk_s520_night.py / s520_schedule.py | 20 / 18 passed |
| ops/test_paper_desk_s522_light_ram.py / s562.py / s754_recovery.py | 35 / 11 / 9 passed |
| ops/test_paper_desk_amendment / integration / issue_offday / legacy_nights | 14 / 4 / 63 / 28 passed |
| ops/test_paper_desk_runtime / r2 / r3_runtime / r3_limits / r4 | 14 / 12 / 9 / 2 / 7 passed |
| ops/test_restart_preflight.py / restart_preflight_fix.py | 60 / 17 passed |
| ops/test_s717_capture_retry.py / test_schedule_recovery_s752.py | 36 / 5 passed |
| ops/test_paper_desk_start_posix.py | 5 skipped (POSIX only) |
| ops/test_paper_desk_tick.py | 13 passed, 1 failed (test_low_ram_defers_only_compute) |

The tick failure happens on master too: it fails the same way with this change stashed. It is not caused by
switch 3. `python -m scripts.platformkit.ops.paper_desk_tick --help` imports and runs. No tick was run.

## Not verified
- No runtime row shows ncaaf captured or scored yet. The first possible ncaaf scope date is 2026-10-10.
- The books argv is not live until the 10-08 books restart, and the restart has not happened.
- The cause of the pre-existing tick-test failure was not investigated. It needs its own gap.
