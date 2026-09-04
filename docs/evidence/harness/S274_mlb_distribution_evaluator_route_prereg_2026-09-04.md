# S274 Preregistration: MLB Distributional Evaluator Adapter

## Scope and machine

This preregistration executes `docs/evidence/tracking/specs/S274_spec.md` and
self-checks sections B and Q1-Q9 of
`docs/evidence/tracking/VERIFIER_CONTRACT.md`. The machine is local:
`C:\Users\neelj\nba-track-a15`, branch `track-a15`; this route is local because
the task is a read-only corpus evaluation. No deployment, pod copy, ledger,
register, or write under `data/` is authorized.

## Re-measured premise

Before this file was sealed, one complete streaming pass over
`data/frontend/prop_history_corpus_mlb.jsonl` produced
`S244_STREAMING_CENSUS_ROWS=3000` and
`S244_STREAMING_CENSUS_NON_NULL_MARKET_PROB=0`. Therefore no market-conditioned
arm or game-clustered interval will be scored. NULL is the fixed valid outcome
for that arm; no row is excluded from the naive denominator.

## Fixed source, route, and comparison

The sole read-only corpus is `data/frontend/prop_history_corpus_mlb.jsonl`
(1,283,918 bytes; SHA-256
`97a6eebd51c89c456588119c39128099f6492185d414f49a26031a2c10a6c1d0d`; no
image resolution). The archived per-row comparison input is
`docs/evidence/harness/S244_attempt_2_naive_row_series_2026-09-04.csv`.

The new additive adapter maps every parsed CorpusRow to a state with its score
date as `state_ts`, a unique row-derived `game_id`, `outcome=realized_stat`,
and a valid strictly-earlier inert feature availability timestamp. It adds a
pre-corpus anchor only to make the first real date eligible for the shared
route; that declared anchor is excluded from the 3,000-row denominator.
`home` is the player and `away` is a fixed MLB-line label solely to satisfy the
shared route schema. The predictor returns only that player's observations from
strictly earlier score dates supplied by the route; it asserts every supplied
training state is more than the fixed three-day symmetric embargo from the
test date. A missing player history returns the fixed point mass `[0.0]` and is
recorded, never excluded.

The only scored route is
`scripts/platformkit/eval_gate/cpcv_distribution.py:cpcv_evaluate_distributional`,
using `n_groups=778`, `n_test_groups=1`, and unchanged `embargo_days=3`.
Its callback alone emits CRPS and lower-nearest-rank pinball q10/q50/q90.
The protected evaluator and
`scripts/platformkit/mlb_batter_pitcher_line_dist.py` are not edited; their
pre-score SHA-256 identities will be recorded and asserted after scoring.

The report unit is the unweighted mean of the 777 date-cluster means over all
3,000 parsed real rows. The fixed archived values and unchanged acceptance bar
are:

| Quantity | Archived value | Required absolute delta |
|---|---:|---:|
| CRPS | 0.5098297809224259 | <= 1e-9 |
| Pinball q10 | 0.08655308369594088 | <= 1e-9 |
| Pinball q50 | 0.37323931073931077 | <= 1e-9 |
| Pinball q90 | 0.2013804110232682 | <= 1e-9 |

## Outputs and checks

The adapter will create new dated S274 JSON and paired-loss CSV evidence and a
dated memo. The paired CSV will retain cluster id, timestamp, state identity,
reconstructible forecast samples, training count, archived and route losses,
and their deltas for all four quantities. RSS is printed immediately before
and after scoring and the run aborts above 600 MB. One focused test will use
exact numerical assertions only for a seeded fixture it creates; on the real
corpus it will assert only row/cluster counts and the fixed embargo setting.

This is a fixed baseline reproduction, not a charged candidate comparison, so
Q2 does not apply and no ledger write is permitted. No AHEAD result is
possible, so Q5 does not apply.

S274_PREREG_SEAL_SHA256=059b9f66161845a9582c99fab16c9fb3949e3f8c02f7d80940e5813fe91c3ed0
