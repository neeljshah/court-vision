# S809 -- the S780 daily fit reads the same history pair the night reads (PAPER ONLY)

## Premise (measured 2026-10-09 16:13Z, read-only)
- `python -m scripts.platformkit.execution.live_shadow_fit --sport nba --day 2026-10-09 --repo-root <main>` printed
  `{"counts": {"fit_refused": 1}, "detail": "config_mismatch"}`; only `_fits/<sport>/2026-10-07.json` exist.
- `live_shadow_fit.history()` built the expected config with `history_lookback_days` = 7 (budget) and a second
  constant `EMBARGO_DAYS = 3`; `paper_night_steps.scoreboard_step` (S766, commit B) builds it with
  `cumulative_lookback(day, 7)` and `POLICY["fit"]["embargo_days"]`. Manifest 2026-10-09: lookback_days 17,
  embargo_days 3, boundary 2026-10-06. `validate_pair` raises `config_mismatch` on the dict inequality.
- Second gate found at Step 0 after the config fix: `history()` also refused `history_incomplete`. The S766
  cumulative manifests 10-08 and 10-09 are `complete: false` forever because old nights 09-26 (shard_absent),
  09-27 and 09-28 (schedule_absent) are recorded and skipped; the night consumes the pair regardless
  (scoreboard_step never reads `complete`).

## Change (owned files only)
- `scripts/platformkit/execution/live_shadow_fit.py`: `EMBARGO_DAYS` is `ingame_scoreboard.POLICY["fit"]["embargo_days"]`
  (literal deleted); `history()` derives the expected config as `history_config(day, cumulative_lookback(day,
  int(producer_args.history_lookback_days)), EMBARGO_DAYS, sha256(producer_args.prereg))`, i.e. the night's
  expression; the `history_incomplete` refusal is replaced by `sources.history_nights_incomplete` (a count).
- Untouched: fit identity scheme, arms B/C, freeze, build_fit eligibility, the recorder, every non-owned file.

## Clauses
- V1 The fit's expected config equals scoreboard_step's on a cumulative night (2026-10-09: lookback 17, embargo 3).
- V2 The V1 test FAILS on the pre-S809 function (run once against `git show HEAD:...live_shadow_fit.py`).
- V3 No second embargo literal remains in live_shadow_fit.py.
- V4 An incomplete cumulative pair is consumed, and its incomplete-night count is recorded in `sources`.
- V5 Real pair 2026-10-09, read-only (no file written under data/cache): history() validates; per-sport
  build_fit counts reported for nba, nfl, soccer, tennis.
- V6 Existing tests in test_live_shadow_fit.py and test_live_shadow_fit_contract.py still pass; LOC <= 300.
- V7 No $/edge language; PAPER ONLY.
