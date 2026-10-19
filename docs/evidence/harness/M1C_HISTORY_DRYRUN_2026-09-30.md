# M1(c): scratch dry-run of the scoreboard history step for night 2026-09-30

Orchestrator 2, 2026-09-30 ~02:0xZ. FIVE_HOUR_PLAN_2026-09-30_A.md M1(c). Read-only on the real archive.

## Method
- Scratch root: worktree C:/Users/neelj/nba-harness-h162 at master. The kalshi and state shards 2026-09-23..28 for mlb and soccer were copied byte-for-byte from data/cache/ingame_capture_view_v2 into h162 (832 MB). Neither the real manifest nor the real training rows were written.
- Command (cwd h162), matching paper_night.py:105-106 and scoreboard_history.history_step:25-28, with the budget's producer_args (prereg = PREREG_2026-09-24.json, the base seal the history step validates, lookback 7): `python -m scripts.platformkit.execution.scoreboard_history --for-night 2026-09-30 --as-of 2026-09-30T02:00:55Z --capture-root data/cache/ingame_capture_view_v2 --served-schedule docs/evidence/forward/schedules/{date}_maker_forward.json --training-rows data/cache/forward/scoreboard/training/{date}.jsonl --prereg docs/evidence/forward/scoreboard/PREREG_2026-09-24.json --lookback 7`
- Wrapper: scratchpad/m1c_history.py, with a 300 MB process-tree RSS cap.
- Two runs refused, as expected: as-of 06:00Z gave `as_of_future`, and `--prereg PREREG_2026-09-30.json` gave `prereg_mismatch`. The night passes the base seal, not the dated amendment.

## Result
- `state published, complete true, rows 2585, incomplete 0`. Boundary 2026-09-27T00:00:00Z, snapshot 2026-09-26T23:59:59.999999Z, embargo 3 days, so the window is 2026-09-23..26.
- Wall time 39.1 s, peak RSS 137,474,048 B, exit 0.
- Training rows: 2,585, all mlb, from 6 games (822842 222, 823411 474, 824707 456, 824866 496, 823491 405, 824220 532).
- Outcome classes: 1 = 754, 0 = 1,831, so both classes are present.
- model_prob is present on 0 rows. D stays empty: native state carries no model_prob.
- Per night (scorer_counts):
  - 09-23: 3 served games, 0 rows. model_state_refused 1,008, tick_refused:book_absent 63.
  - 09-24: 4 served games. model_state_refused 343, book_absent 23.
  - 09-25: 3 served games, 1 unsettled. model_state_refused 1,358.
  - 09-26: 6 served games, **6 unsettled**, because of the capture outage that began about 2026-09-26T02:13Z. model_state_refused 714.
- Soccer: no served games in the window, so no rows.

## Reading
If the 09-29 night's history step runs as planned (~06:07Z 09-30, free RAM permitting), night 2026-09-30 fits arms B and C for mlb on 2,585 training rows from 6 games with both classes present. D stays empty, and soccer has no history and no fixtures. The outage shows up as 6 unsettled 09-26 games that contribute no rows. It is not a refusal. Every 09-30 cell will still be INSUFFICIENT under the 30-game / 5-cluster floor, so this is a calibration measurement only, with no market claim. Arm A is the venue mid.
