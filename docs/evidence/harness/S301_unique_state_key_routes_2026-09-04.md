# S301 unique evaluator state-key routes

## Scope and contract

This local construct implements `docs/evidence/tracking/specs/S301_spec.md` and self-checks `docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q. No store was opened, no pod was used, and neither the register nor a ledger was written. The construct has n = 6, exhaustively enumerating three routes times the duplicate and simultaneous-games fixtures.

## Binding premise before change

The exact four-row fixture had rows 0 and 1 with the same `(game_id, state_ts)`: `duplicate-game|2024-01-01T19:00:00`. The unmodified routes printed:

```text
walk_forward records=4
cpcv_evaluate records=4
cpcv_evaluate_distributional records=4
duplicate-key routes raised=0/3
```

The premise held, so the additive change was required.

## Sealed preregistration

The preregistration is [S301_unique_state_key_routes_2026-09-04_prereg.md](S301_unique_state_key_routes_2026-09-04_prereg.md), committed before the comparison as `2572c649bd92a0b6640b1c0c255d13e3eefcad7c`. Its seal is `1ec2383a3fd2cbd9da3fb366dfecbc4b1055fe49e23d47052b0638a6dd1e152f`. It was staged with LF bytes and verified after that commit with:

```text
git show HEAD:docs/evidence/harness/S301_unique_state_key_routes_2026-09-04_prereg.md | head -n 24 | sha256sum
1ec2383a3fd2cbd9da3fb366dfecbc4b1055fe49e23d47052b0638a6dd1e152f  *-
```

The focused test reads the preregistration file directly, normalizes CRLF to LF, and hashes bytes above `Seal-SHA256:`; it does not use Git.

## Construct and results

`assert_unique_state_keys` defines the stable evaluator key as `game_id|state_ts`. Each scored control state is one evaluator tick with that key. The simultaneous-games control changes only `game_id` from the duplicate fixture, preserving its wall-clock time. `cpcv_evaluate` and `cpcv_evaluate_distributional` ran with `n_groups=3`, `n_test_groups=1`, and their existing symmetric one-day embargo; `walk_forward` retained its existing purge and embargo. Each callback produced the deterministic evaluated forecast (0.5, or distributional samples 0.25 and 0.75).

| Route | Exact duplicate, guard on | Distinct simultaneous games, guard on | Guard-off max abs loss difference |
| --- | --- | --- | --- |
| `walk_forward` | raises exact `ValueError` | accepts 4 records | 0.0 |
| `cpcv_evaluate` | raises exact `ValueError` | accepts 4 records | 0.0 |
| `cpcv_evaluate_distributional` | raises exact `ValueError` | accepts 4 records | 0.0 |

The differential archive is [S301_unique_state_key_routes_2026-09-04.json](S301_unique_state_key_routes_2026-09-04.json). Its 12 rows are evaluator-produced control records only; each stores both losses, cluster id, timestamp, and stable state key. The duplicate guard-on cases intentionally produce exceptions and therefore have no loss rows. Improvement = baseline loss minus candidate loss; positive = candidate better. Every archived delta is 0.0.

## Code identity

| Route file | SHA-256 before | SHA-256 after |
| --- | --- | --- |
| `scripts/platformkit/eval_gate/walkforward.py` | `9b5f87b0bbd4e0255489fc40f069f092439592f3c35a7b3037dd210648a1baeb` | `6a59fbc9446bf07846eb7f7e0198e46c96911143444e488224467c7c744f4fc9` |
| `scripts/platformkit/eval_gate/cpcv_engine.py` | `8da9186c9b8da1d726733ec345850281e2de83ac268ed19aaeb09cccf053cbb5` | `9b152531852a9fd435be82ca69584929fe718da9bd1554ad293cb4cd11717c01` |
| `scripts/platformkit/eval_gate/cpcv_distribution.py` | `0e006243171a92c2102c7a6a6cb52d1eee456be60d68fef85819695333311be8` | `ddc2611d27a5741016743fd9d3762ac80586ca337f67ad014866c06e2388eaa3` |

New additive module: `scripts/platformkit/eval_gate/state_key_guard.py` (14 lines). Existing defaults, split constants, purge, embargo, archived artifacts, and callers remain unchanged because all three new keywords default to `False`.

## Test

```text
python -m pytest tests/platformkit/eval_gate/test_unique_state_key_routes.py -q
10 passed
```

## Verifier self-check

- B1-B4, B6-B10: no schema removal, exclusion, fall-through, claim loop, orphan, moved bar, or charged metric; this is a complete fixed construct.
- B5: local-only work; no deployment or pod activity.
- Q1: preregistration seal committed and verified before the comparison.
- Q3-Q4: fixed bar; the shared routes retain their purge and symmetric nonzero embargo.
- Q5: no AHEAD claim; this is a harness behavior construct.
- Q6-Q9: calibration-only wording; exhaustive n = 6; premise rerun first; archived differential rows are evaluator records with reconstructible callbacks.

## NOT VERIFIED

- Behavior of callers not covered by the three named evaluator routes.
- Any external corpus, real-time feed, pod environment, or deployment.
- Any claim beyond duplicate-key rejection, simultaneous-game acceptance, and guard-off fixture reproduction.
