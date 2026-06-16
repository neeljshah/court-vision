# Golden fixture schema -- `game_states.json`

SYNTHETIC reproducibility/regression anchor (see `README.md`). NOT real games,
NOT a calibration claim. This document is the field-by-field contract enforced by
`scripts/platformkit/eval_gate/schema.py::validate_golden`.

## Top-level object

```json
{ "schema": 1, "_synthetic": true, "n": 103, "states": [ ... ] }
```

| key          | type   | meaning                                                       |
|--------------|--------|---------------------------------------------------------------|
| `schema`     | int    | `GOLDEN_SCHEMA_VERSION` (currently `1`).                       |
| `_synthetic` | bool   | always `true` -- this is a synthetic anchor, not real data.    |
| `n`          | int    | number of states (must equal `len(states)`, in `[90, 120]`).  |
| `states`     | list   | the array of game-state objects documented below.             |

## Per-state object (each element of `states`)

| field              | type            | meaning / provenance                                                                                   |
|--------------------|-----------------|--------------------------------------------------------------------------------------------------------|
| `game_id`          | str             | cluster key for the Diebold-Mariano clustered SE (e.g. `g0000`). In-game states of one game share it.  |
| `season`           | str             | `2023-24` or `2024-25`; the second clustering level and the two-corpus split.                          |
| `sport`            | str             | `nba` (the mlb slot is registered-but-skipped at the baseline level).                                  |
| `regime`           | str             | one of `pregame|q1|q2|q3|q4|blowout|foul_trouble|early_season|longshot`; per-regime slicing tag.        |
| `game_date`        | str (ISO date)  | date of tip -- the prediction-time boundary.                                                           |
| `state_ts`         | str (ISO datetime) | timestamp of the state; equals tip (19:00) for pregame, offset by quarter-minutes in-game.          |
| `home`, `away`     | str             | placeholder team codes from a 12-team pool; used by walk_forward purge/embargo (same-team / matchup).  |
| `features`         | dict[str,float] | as-of-`state_ts` features: `strength`, `rest`, `home_edge` (+ `foul_diff` in the foul_trouble regime).  |
| `feature_avail`    | dict[str,str]   | per-feature ISO date each became known; the leak guard asserts each is strictly `< state_ts`.          |
| `devig_close_prob` | float [0,1]     | the Shin-devigged close (the REFERENCE forecaster for BSS). Synthetic near-oracle = `p_true` + noise.  |
| `truth_wp`         | float [0,1]     | empirical/replay win-prob for the state's bucket; here `p_true` (the generative latent). Calibration target. |
| `outcome`          | int {0,1}       | realized binary outcome -- the scoring LABEL for Brier / log-loss.                                      |

All floats are rounded to 6 decimal places for stable git diffs. ASCII only.

## Invariants `validate_golden` enforces (and the gate relies on)

1. `90 <= len(states) <= 120`.
2. Every `REQUIRED` field present on every state.
3. `outcome in (0, 1)`; `0.0 <= devig_close_prob <= 1.0`; `0.0 <= truth_wp <= 1.0`.
4. **Leak guard (vintage):** for every feature, `feature_avail[f] < state_ts`
   strictly. A violation raises `AssertionError("LEAK: ...")`. The same check runs
   again inside `walkforward.assert_vintage` (defense in depth).
5. `(game_id, state_ts)` is unique across the set (no duplicate states).
6. **Coverage guard:** the fragile regimes `pregame`, `q4`, `blowout`,
   `foul_trouble` are each present at least once.

## How the gate consumes these fields

- `walk_forward` sorts by `state_ts`, builds an expanding training window that is
  strictly in the past, applies a 48h same-team purge and a 3-day same-matchup
  embargo (using `home`/`away`), re-asserts the vintage guard, then calls the
  predictor and collects `{game_id, ts, p_model, p_close (=devig_close_prob), y (=outcome)}`.
- `scoring.py` computes Brier (vs `outcome`), Brier Skill Score (vs
  `devig_close_prob`), log-loss, ECE (diagnostic), resolution and sharpness.
- `dm_test.diebold_mariano` runs the cluster-robust (by `game_id`) DM test on the
  per-game loss differences `(p_close - y)^2 - (p_model - y)^2`.
- `run_gate.py` labels each corpus `BEATS_CLOSE` / `MATCHES_CLOSE` / `BEHIND`
  (none block) and exits 1 only on regression-vs-frozen-baseline or a leak.

To regenerate the fixture or re-freeze baselines, see `README.md`.
