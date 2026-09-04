# S284 Native Kalshi Trade Occurrence

Spec: `docs/evidence/tracking/specs/S284_spec.md`.
Contract self-checked: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q1-Q9.

Verdict: REJECT. The preregistered candidate is below the frozen calibration
bar and is not retained. No production path, flag, registry, ledger, or input
store changed.

## Premise binding

The two named inputs were opened one at a time. Their identities are recorded
in the scored JSON, including byte size, resolution, and SHA-256.

| Input | Bytes | Resolution | Whole-set binding result |
| --- | ---: | --- | --- |
| `data/cache/inplay_odds/nba_price_series.parquet` | 25,140,428 | parquet | Kalshi: 657,145 rows; `traded` true 370,181 and false 286,964. |
| `data/cache/inplay_odds/nba_checkpoints_full.parquet` | 2,829,826 | parquet | 465,249 rows; checkpoint `traded` true 465,249 and false 0. |

The binding parse used native `event_key` shape
`KXNBAGAME-YYMONDD<away><home>` and frozen checkpoint ticker shape
`nba-<away>-<home>-YYYY-MM-DD`. It found 53 parseable native game keys. The
date-offset distribution was computed over every same-team-pair candidate,
with offset defined as checkpoint date minus native-key date. Its zero-day bin
is 40 for away-home and 0 for home-away; the exhaustive parser output was
printed during the binding run, and every exact zero-day match is in the
committed census CSV.

| Ordering | Exact zero-day game clusters | Offset range | Best-ordering decision |
| --- | ---: | --- | --- |
| away-home | 40 | -577 through +12 days | Selected: the only ordering above 30. |
| home-away | 0 | -575 through +10 days | Reported, not scored. |

The checkpoint flag condition therefore still held, while native Kalshi's flag
was non-degenerate. This run is the first S284 arm using that native field.

## Sealed comparison

Preregistration:
`docs/evidence/harness/S284_orderflow_traded_2026-09-04_preregistration.md`.
Its LF-byte seal is
`9ea40e19826a36bc5f8de3d651403f64fcd1b78ab7c821ddd06a6ada03ea8932`.
It was committed before the first metric in
`fb433f63bdabbb1251f4503361648b33351051cd`; the required
`git show HEAD:<path> | head -n 36 | sha256sum` check reproduced the seal.
The focused test reads the preregistration from the working tree, normalizes
CRLF to LF, and hashes all bytes above the seal line.

The join uses the selected away-home ordering. A checkpoint state receives only
the latest strictly earlier native event tick at a 60-second tolerance. Its two
candidate inputs are that timestamp's event-level `traded_any` flag and the
count of true native tick rows in the preceding 60 seconds. All 6,272 joined
checkpoint ticks from 40 games met this as-of rule. The incumbent's first
calendar block has no OOF recalibration; the named, outcome-independent result
is 5,486 scored states across 35 game clusters.

Every score is from `cpcv_evaluate` with 8 groups, 2 test groups, imported
symmetric purge, and symmetric nonzero 1-day embargo. One state is one
`(game_id, checkpoint_ts)` tick. The null evaluator returns the OOF
`apply_incumbent(..., "recal_null")` probability; the candidate evaluator fits
only its own CPCV training states using that baseline logit and the two fixed
order-flow inputs. Both evaluators produced 38,402 records. The archive
aggregates the seven evaluator records per state and derives both losses only
from those records.

| Quantity | Value |
| --- | ---: |
| recal_null Brier | 0.1944820247605522 |
| candidate Brier | 0.21058286362608172 |
| calibration improvement (null loss minus candidate loss) | -0.016100838865529533 |
| game-clustered 95 percent interval | [-0.06269144274272628, 0.027467473498453215] |
| frozen bar | +0.004 |

The result is below the bar, so the comparison is REJECT. This is not an ahead
claim and no second-corpus condition is invoked. The local process RSS after
the score was 341,315,584 bytes, below the 500 MB pod threshold.

## Artifacts and reproduction

- `docs/evidence/harness/S284_orderflow_traded_2026-09-04_parse_join_census.csv`
  enumerates every parseable native key under both orderings and names every
  zero-day checkpoint match.
- `docs/evidence/harness/S284_orderflow_traded_2026-09-04.json` records input
  identities, as-of rule, joined and OOF counts, evaluator counts, score, and
  final scorer SHA-256 `9bfd2ce586e7e833485f24428d2d4f2f11afc29d000b7e8bb95acb4b0eea52de`.
- `docs/evidence/harness/S284_orderflow_traded_2026-09-04_ticks.csv` is the
  per-state paired-loss archive: cluster, as-of timestamp, candidate inputs,
  outcome, both OOF probabilities, both losses, improvement, and evaluator
  multiplicity. Its 5,486 rows are 5,486 distinct state keys.

Reproduction commands:

    python -m scripts.platformkit.eval_gate.s284_orderflow_traded --census-csv docs/evidence/harness/S284_orderflow_traded_2026-09-04_parse_join_census.csv
    python -m scripts.platformkit.eval_gate.s284_orderflow_score --output-dir docs/evidence/harness

## Contract self-check

| Clause | Result |
| --- | --- |
| B1, B9, Q7 | Every tick satisfying the preregistered strict as-of rule is named; the only removal is the incumbent's first OOF block. The native feature is non-degenerate. |
| B2-B4, B6 | Additive evidence routes only; no reader, schema, default, claim state, or production route changed. |
| B5 | Local run only; no pod or deployed-tree action occurred. |
| B7-B10 | No render sampling, self-fit evidence, recycled state identity, or moved bar. |
| Q1-Q3 | The prereg was committed and seal-verified before scoring; no ledger action occurred; the +0.004 bar is byte-identical to the spec. |
| Q4, Q9 | Both arms use CPCV purge plus symmetric embargo; the committed per-state archive is evaluator-derived and reconstructs the paired losses. |
| Q5-Q6, Q8 | No ahead claim; calibration language only. The checkpoint and native-flag premise census was re-run. |

## Test

`python -m pytest scripts/platformkit/eval_gate/test_s284_orderflow_traded.py -q -p no:cacheprovider`
returned `2 passed in 0.70s`. It parses synthetic pairs, reproduces both-ordering
overlap, verifies the normalized preregistration seal, and recomputes one
archived game's recal_null Brier.

## NOT VERIFIED

- Independent verifier reproduction and the reported process RSS.
