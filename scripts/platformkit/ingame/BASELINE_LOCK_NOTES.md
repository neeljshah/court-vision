# Baseline lock task notes

- 2026-09-01: `scripts/platformkit/pbp_lineups.py` and
  `domains/basketball_nba/lineups/pbp_lineups.py` have disjoint APIs. The former
  provides `SUB_RE` and `clock_to_sec` for text substitution parsing and has a
  live consumer in `test_defensive_stats.py`; the latter builds PT-clock stints.
  Both modules are retained. The duplicate-module step was skipped.
- 2026-09-01: The stale `_PRIOR` is at
  `scripts/platformkit/ingame_state_lift.py:30`. The current settled-tick lock
  measured delta_brier -0.03425595343964605 with gap_effective_n 268, so its
  verdict is BEHIND under the locked comparison tolerance.
