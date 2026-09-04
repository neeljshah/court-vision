# S268 Attempt 2: Sibling Distributional CPCV Route

## Verdict

ACCEPT. The distributional route is now in the additive sibling
`scripts/platformkit/eval_gate/cpcv_distribution.py`; the protected
`cpcv_engine.py` is byte-identical to `master`.

This memo implements `docs/evidence/tracking/specs/S268_spec.md` and
self-checks sections B and Q of `docs/evidence/tracking/VERIFIER_CONTRACT.md`.
No register, ledger, deployment, or write under `data/` occurred.

## Preregistration and identity

The preregistration was committed before this run at
`7d133f60768fcaa33203d1957e01b1362841c1d6`. Its staged-prefix and committed
blob seal is:

```text
S268_ATTEMPT2_PREREG_SEAL_SHA256=cfbeb06cb7678d45b892f9941fcab389b21039d8f8e592eed2ad256ea596eff3
```

The focused test separately reads the working-tree preregistration file,
normalizes CRLF to LF, and hashes bytes above its seal line; it never uses
`git show HEAD`. The restored protected engine identity is:

```text
CPCV_ENGINE_IDENTITY_SHA256=e9fe694a721658a067bd452911b7f95627897ba4d6c6dccd86cc080f9fa6935c
```

The additive sibling is 59 lines and SHA-256
`0e006243171a92c2102c7a6a6cb52d1eee456be60d68fef85819695333311be8`.
It imports `cpcv_engine` read-only, invoking its `cpcv_splits`,
`_blocked_indices`, redaction, and vintage guard unchanged.

## Construct fixture

The complete construct contains 32 seeded regular states and one planted state
(33 total, all enumerated). The planted same-team state is 47 hours from the
target and is removed only by the normal symmetric purge. The point-mass Brier
comparison was:

```text
FIXTURE_NORMAL_BRIER=0.25
FIXTURE_SCALAR_BRIER=0.25
FIXTURE_BRIER_DELTA=0.0
FIXTURE_PURGE_ON_MINUS_OFF=0.007575757575757569
FIXTURE_TARGET_LEAKY_LOWER=True
```

Thus the sibling route matches `cpcv_evaluate` within the fixed 1e-9 bar, and
the purge-off rerun changes the score. The planted target's leaky loss is 0.0
versus honest loss 0.25, so the construct demonstrates that purge is exercised.

## MLB reproduction

The only runtime corpus opened was
`data/frontend/prop_history_corpus_mlb.jsonl`: 1,283,918 bytes, SHA-256
`97a6eebd51c89c456588119c39128099f6492185d414f49a26031a2c10a6c1d0d`,
resolution none. The reproducible 3,000-row archive names a fixed pre-corpus
anchor solely to make the earliest real date testable; that anchor is excluded
from the named real-row denominator. Every real row retains its as-of forecast
samples, training count, archive/new losses, delta, cluster id, and timestamp.

| Quantity | Archived S244 | Sibling route | Delta |
|---|---:|---:|---:|
| CRPS | 0.5098297809224259 | 0.5098297809224259 | 0.0 |
| Pinball q10 | 0.08655308369594088 | 0.08655308369594088 | 0.0 |
| Pinball q50 | 0.37323931073931077 | 0.37323931073931077 | 0.0 |
| Pinball q90 | 0.2013804110232682 | 0.2013804110232682 | 0.0 |

The sibling route produced 3,000 unique row and game ids over all 777 date
clusters. RSS was 143.472656 MB before the rerun and 155.972656 MB after it;
both are below the 600 MB memory limit.

## New artifacts

| Path | Bytes | SHA-256 |
|---|---:|---|
| `S268_distributional_evaluator_route_fixture_2026-09-04_attempt2.json` | 11,695 | `8377b9281efa4e780d5aff910214a6a5003ec7d7a3b4aa9ed9a08bfab0aafe11` |
| `S268_distributional_evaluator_route_mlb_paired_losses_2026-09-04_attempt2.csv` | 1,984,918 | `b57bfc86722eb4b49e8dbb23f2aabad6c2dd02bb8fd846d3a1a63ef75c553b81` |
| `S268_distributional_evaluator_route_rescore_attempt2.py` | 11,512 | `bce2f18988f90a057e6ab0d6831aa5fc17c157bf7c317ee636b1fd3b44fb35f7` |

## Contract self-check

- B1: all 3,000 real rows are retained; the anchor is declared before scoring.
- B2-B6: the former rescore import orphan now sources `cpcv_evaluate` from
  `cpcv_engine` and `cpcv_evaluate_distributional` from `cpcv_distribution`; no protected reader, schema, deployment, claim path, ledger, or register changed.
- B7-B9 and Q7: the construct enumerates all 33 states; the archive enumerates
  all 777 clusters and 3,000 unique real rows.
- B10 and Q3: the protected engine, fold construction, purge and embargo
  constants, and all bars are unchanged.
- Q1: the committed seal predates scoring. Q2 does not apply to this fixed
  reproduction and ledger writes are prohibited. Q4 uses CPCV with the normal
  purge and symmetric embargo. Q5 has no AHEAD verdict. Q6 uses calibration
  language only. Q8 reran the premise. Q9 archives per-row paired losses and
  reconstructible as-of forecasts.

## Tests

```text
python -m pytest tests/platformkit/test_s268_distributional_evaluator_route.py -q -p no:cacheprovider
2 passed in 1.29s
python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
1 passed in 1.85s
```
