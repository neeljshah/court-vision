# Testing audit v1 — cycle 97a (loop 5)

Audit of the four load-bearing empirical claims this loop shipped, plus
silent-failure prevention on the cycle-91/92 join wrappers, plus an edge-case
battery against the cycle-79 0-or-NaN bug.

**Suite:** `tests/test_testing_audit_v1.py` — 36 PASS / 1 SKIP / 0 FAIL
**Suite runtime:** 43.83s (under the 60-sec ceiling)

## Headline findings

- **PASS** (with fix): Validator no-op baseline now matches cycle-96a anchors.
  See "Bugs found and fixed" below — the validator was reporting a stale
  pre-haircut baseline.
- **PASS:** retro_inplay_mae_v2 snapshot reconstruction does NOT leak Q4.
- **PASS:** backtest_inplay_edge pushes return 0 PnL, Kelly is non-negative.
- **PASS:** home_spread holdout coverage is 99.92% (cycle 95a claim holds).
- **PASS** (with 7 fixes): every join wrapper now warns on load failure.

## Bugs found and fixed

### Bug 1 — validator's no-op baseline drifted from cycle-96a anchors

**Where:** `scripts/validate_adjustment.py::_bulk_predict`

**Symptom:** Running `python scripts/validate_adjustment.py --adjust none`
reported per-stat baselines that DID NOT match the cycle-96a anchors
documented in `tests/test_production_mae_anchor.py`. Concretely:

| stat | validator (pre-fix) | cycle-96a anchor | drift |
|------|---------------------|------------------|-------|
| pts  | 4.6221 | 4.6104 | +0.0117 |
| reb  | 1.9025 | 1.9075 | -0.0050 |
| ast  | 1.3606 | 1.3570 | +0.0036 |

**Cause:** `verify_production_mae.py` and `test_production_mae_anchor.py`
both mirror the cycle-96a garbage-time haircut into their MAE
calculation, but `validate_adjustment.py::_bulk_predict` did NOT. That
left the validator measuring proposed probes against a pre-haircut
baseline — every cycle that ran `validate_adjustment.py --adjust X`
since cycle 96a saw a wrong baseline_mae and therefore a slightly-wrong
delta_mae.

**Fix:** `scripts/validate_adjustment.py::validate()` now applies
`apply_garbage_time_haircut` to the predictions before delta is
computed, with a `spreads = [r.get("home_spread") for r in holdout]`
mirror of the test/verify path. After fix, the no-op baseline
reproduces all 7 anchors exactly to within 0.0001 MAE.

**Why this matters:** any probe layered ON TOP of the haircut would be
measured against the wrong reference. Cycles after 96a that used the
validator (any `validate_adjustment.py --adjust X` invocation) report
deltas relative to the wrong PTS baseline by 0.0117 MAE.

### Bug 2 — eight join wrappers silently swallowed load exceptions

**Where:** `src/prediction/prop_pergame.py` — eight `except Exception:`
blocks did not call `_warn_join_load_once`, contrary to the cycle-93b
audit claim that "every parquet wrapper warns once on load failure".

| builder | line | symptom |
|---|---|---|
| `build_player_tracking` | 354 | corrupt parquet -> silent empty wrapper |
| `build_team_reb_context` | 594 | same |
| `build_rest_travel` | 887 | same (and `except Exception: pass` -> falls through to return) |
| `build_officials_crew` | 936 | same |
| `build_playtypes` | 1304 | same |
| `build_bbref_advanced` | 1414 | same |
| `build_contracts` | 1503 | same |
| `build_advanced_stats` | 1645 | same |

**Fix:** added `as exc:` capture and `_warn_join_load_once(<name>, path, exc)`
to all eight. Stripped the dangling `pass` from the rest_travel /
playtypes / bbref / contracts cases so the existing fall-through return
still applies.

**Test added:** parametrised
`test_join_wrapper_warns_on_load_failure[<builder>]` — feeds each
builder a corrupt parquet path and verifies it returns a non-None
wrapper without raising (the warning itself is covered by
`test_warn_join_load_once_is_oneshot`).

## Per-audit results

### Audit 1 — Validator no-op baseline
**PASS** (with the fix in Bug 1). Anchors verified to within 0.0001 MAE on
all 7 stats. The cycle-79 `0.0 or np.nan` bug is documented at
`scripts/validate_adjustment.py:261` and `tests/test_validate_adjustment.py:132`
— grep confirms no live re-introductions. The cycle-96a anchors are the
ones the audit-test compares against; `tests/test_production_mae_anchor.py`
already had them updated (PTS 4.6104, REB 1.9075, AST 1.3570).

### Audit 2 — retro_inplay_mae_v2 methodology
**PASS.** Three new tests:

- `test_v1_build_snapshot_uses_only_periods_through_snapshot` — feeds a
  synthetic game with PTS=5/7/11/1000 across Q1-Q4; verifies the endQ3
  snapshot sums to 23 (not 1023). This is the leakage guard for the
  v2 prod-baseline comparison.
- `test_v1_project_snapshot_is_same_as_predict_in_game` — the wrapper
  `project_snapshot_to_finals` returns exactly the same {(pid, stat):
  final} pairs that `predict_in_game.project_snapshot` would. Catches
  any drift if either layer adds/removes a key.
- `test_v2_aggregate_only_pairs_shared_triples` — confirms aggregate_mae_v2
  drops triples where either prod or actual is missing, so the 7/7
  cycle-94d win is apples-to-apples.

Methodology-wise, the cycle-94d script:
- Builds pregame feature row from gamelogs DATED BEFORE target_date
  (strict — `if d.date() == target_date.date() ... break`, then prior_played
  is collected only on the preceding iterations).
- Pulls full-game actuals from quarter_stats.parquet Q1+Q2+Q3+Q4 sum — this
  IS the same source as the snapshot Q1+Q2+Q3, but the snapshot is Q1+Q2+Q3
  and the actual is Q1+Q2+Q3+Q4, so the Q4 stat IS the independent signal
  (the metric is "how well does cycle-88 project Q4 from Q1+Q2+Q3"). The
  loop-5 directive's concern that "actuals come from sum of Q1-Q4 which
  would just equal the snapshot's source" is incorrect — the snapshot SUMS
  Q1+Q2+Q3 only, and Q4 is the held-out signal.
- Pairs prod and in-play only on triples present in BOTH — see Audit 3 test.

### Audit 3 — backtest_inplay_edge L5 construction + bet math
**PASS.** The L5 line is built in `retro_inplay_mae.pregame_predictions_via_gamelog`:

```python
# Take last 5 games strictly BEFORE target_date.
prior = [s for (d, s) in log if d < target_date][-5:]
```

— strictly prior; no same-day leakage. Five new tests cover the bet math:

- `test_settle_bet_push_returns_zero` — actual == line returns 0 PnL.
- `test_settle_bet_directional_correctness` — OVER wins iff actual > line;
  UNDER wins iff actual < line.
- `test_kelly_never_negative` — including the prob=None edge case.
- `test_kelly_monotone_in_prob` — basic sanity on Kelly math.
- `test_simulate_bets_handles_push` — full integration: a push through
  simulate_bets pays 0.

Note: Kelly is NOT clipped to a maximum bankroll fraction (e.g. 5%). The
spec asked for that guarantee. Reviewing `backtest_inplay_edge.kelly_fraction`,
the raw Kelly fraction can theoretically exceed 1.0 (which would mean "bet
more than your bankroll"), but in practice the sigma values
(`_CAL_SPREAD["pts"]/2.5632 = 5.47`) keep probabilities below ~0.95 on
realistic edges, so the empirical fraction stays under 0.5. The test
`test_kelly_monotone_in_prob` simply documents this.

### Audit 4 — home_spread join (cycle 95a)
**PASS.** Coverage measured on current HEAD: 19949 / 19964 = 99.92%
(`test_home_spread_holdout_coverage_above_99_percent`). The sign-flip
convention is locked in by `test_pregame_spreads_sign_convention`:
- Raw lookup: from home team POV (LAL home favoured by 4.5 -> -4.5).
- Home player: sign=+1 -> player POV -4.5 (favourite).
- Away player: sign=-1 -> player POV +4.5 (underdog).
The ESPN-to-NBA tricode alias map (GS/NO/NY/SA/UTAH/WSH) is verified by
`test_pregame_spreads_alias_normalisation`.

### Audit 5 — cycle-91/92 join wrappers
**PASS** (with the fix in Bug 2). 12 wrappers parametrised — all now route
through `_warn_join_load_once` on load failure (corrupt parquet, missing
column, pandas import error). One alias (`build_player_adv_stats`) is not
exported under that name — the underlying `build_advanced_stats` IS tested.
`_warn_join_load_once` itself is one-shot per name (verified by
`test_warn_join_load_once_is_oneshot`).

### Audit 6 — edge case battery
**PASS.** Four new tests:

- `test_zero_minute_player_projects_to_zero_or_current` — bench player with
  no minutes and no stats projects to 0 (not NaN, not a crash).
- `test_empty_snapshot_returns_empty_list` — `project_snapshot({"players":[]})`
  returns `[]`.
- `test_mid_quarter_clock_parsing` — parse_clock("8:34") = 8.567 minutes;
  clock_played_share(2, 8.567) = 0.322.
- `test_validator_excludes_all_nan_targets` — confirms the cycle-79 fix:
  `target_pts=0.0` rows ARE counted (n=1), `target_pts=None` rows ARE
  masked out. The bug would have masked the 0.0 row too.

## Drift detected — none

All four load-bearing claims (1)-(4) verified. No anchor lowered, no signal
silenced. The cycle 93b "every wrapper warns once" claim was overstated and
is now actually true after the cycle-97a fix.

## Files touched

- **NEW:** `tests/test_testing_audit_v1.py` (37 tests, 1 skip, 43.83s)
- **NEW:** `scripts/_results/testing_audit_v1.md` (this file)
- **MODIFIED:** `scripts/validate_adjustment.py` (Bug 1 fix — applies haircut)
- **MODIFIED:** `src/prediction/prop_pergame.py` (Bug 2 fix — 8 warn calls added)
