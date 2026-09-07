# S301 preregistration: unique evaluator state keys

## Scope

This construct checks three shared evaluator routes: `walk_forward`, `cpcv_evaluate`, and `cpcv_evaluate_distributional`. It uses no external store, no pod, and no ledger charge because it is an exhaustive local harness construct, not a predictive trial.

## Fixed inputs and evaluator settings

Each route receives four states. Rows 0 and 1 share the exact stable state key `(game_id, state_ts) = (duplicate-game, 2024-01-01T19:00:00)`; rows 2 and 3 have unique keys at 2024-01-05 and 2024-01-09. Features are available at same-day midnight, strictly before each 19:00 prediction tick. CPCV routes use `n_groups=3`, `n_test_groups=1`, and `embargo_days=1`, preserving their symmetric nonzero embargo. The walk-forward route uses its fixed 48-hour purge and 3-day matchup embargo.

The simultaneous-games control differs from the duplicate fixture only in `game_id`: its two 2024-01-01 rows are `simultaneous-a` and `simultaneous-b`. Every state is one scored tick and has a stable `(game_id, state_ts)` key.

## Fixed checks and bar

The exhaustive construct has n = 6: three routes times duplicate and simultaneous fixtures. With `guard_state_keys=True`, each duplicate fixture must raise `ValueError("duplicate state key: duplicate-game|2024-01-01T19:00:00")`; each simultaneous fixture must return its pre-change record count. With the guard omitted or explicitly false, each route's deterministic record payload and fixture score must match byte-for-byte, with max absolute loss difference 0. The deterministic probability is 0.5. Distributional forecasts are `(0.25, 0.75)` and use squared error of their mean.

## Archived comparison records

The post-change JSON will archive only evaluator-produced records for the guard-off comparisons, including route, fixture, stable state key, cluster id (`game_id`), timestamp, baseline loss, candidate loss, and delta. Improvement is defined as baseline loss minus candidate loss; positive means the candidate is better. The expected result is zero for every record because the default remains off.

## Evidence and verification

The result memo is `docs/evidence/harness/S301_unique_state_key_routes_2026-09-04.md`; the result records are `docs/evidence/harness/S301_unique_state_key_routes_2026-09-04.json`; and the sole focused test is `tests/platformkit/eval_gate/test_unique_state_key_routes.py`. The test must read this preregistration file, normalize CRLF to LF, and hash the bytes above the seal line without invoking Git.

Seal-SHA256: 1ec2383a3fd2cbd9da3fb366dfecbc4b1055fe49e23d47052b0638a6dd1e152f
