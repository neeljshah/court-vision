# S268 Distributional Evaluator Route

## Verdict

ACCEPT. The additive empirical-forecast CPCV route meets the sealed construct
checks and reproduces all four archived MLB distributional losses exactly. This
is a route and calibration reproduction only; it makes no comparative model
claim.

The preregistration is
`docs/evidence/harness/S268_distributional_evaluator_route_prereg_2026-09-04.md`,
committed before any metric at `8988727390d73cf0cd56c89da7e3091bbab745bf`.
Its embedded LF staged-blob prefix seal is
`92ef14c0a3d10364ce2c0e9c5d41f484f9163777a3837d64e2d2059887672b1a`.
The committed verification was exactly:

```text
git show HEAD:docs/evidence/harness/S268_distributional_evaluator_route_prereg_2026-09-04.md | head -n 77 | sha256sum
92ef14c0a3d10364ce2c0e9c5d41f484f9163777a3837d64e2d2059887672b1a  -
```

## Binding before-condition

The S268 premise was rerun before the preregistration and any scored result:

```text
S268_SCORE_NAIVE_CLUSTERS_CALLS=ValueError,_history_rows,abs,all,append,defaultdict,dumps,empirical_crps,int,isoformat,items,len,lower_nearest_rank,naive_callback,pinball,sorted,sum,timedelta
S268_SCORE_NAIVE_CALLS_SHARED_EVALUATOR=False
S268_WALK_FORWARD_VECTOR_REJECTION=TypeError: '<=' not supported between instances of 'float' and 'list'
S268_CPCV_EVALUATE_VECTOR_REJECTION=TypeError: '<=' not supported between instances of 'float' and 'list'
```

The premise therefore held. `score_naive_clusters` still owns its date-cutoff
loop and calls neither shared evaluator; both existing scalar evaluator routes
still reject an empirical sample sequence. The additive change was executed.

## Machine, inputs, and route identity

This ran locally in `C:\Users\neelj\nba-track-a17` on `track-a17`. No pod,
deployment, ledger, register, or `data/` write occurred. Stores were opened one
at a time; neither opened input exceeded 300 MB.

| Opened input or produced artifact | Bytes | SHA-256 | Resolution |
|---|---:|---|---|
| `data/frontend/prop_history_corpus_mlb.jsonl` | 1283918 | `97a6ebd51c89c456588119c39128099f6492185d414f49a26031a2c10a6c1d0d` | none |
| `docs/evidence/harness/S244_attempt_2_naive_row_series_2026-09-04.csv` | 1755183 | `87d5cb75ddb5c9cb49a85f6411df09c7734f1f6d5a00b1445cc3185cbcb6f4a0` | none |
| `docs/evidence/harness/S268_distributional_evaluator_route_fixture_2026-09-04.json` | 11695 | `8377b9281efa4e780d5aff910214a6a5003ec7d7a3b4aa9ed9a08bfab0aafe11` | none |
| `docs/evidence/harness/S268_distributional_evaluator_route_mlb_paired_losses_2026-09-04.csv` | 1984918 | `b57bfc86722eb4b49e8dbb23f2aabad6c2dd02bb8fd846d3a1a63ef75c553b81` | none |

The exercised route is
`scripts/platformkit/eval_gate/cpcv_engine.py` staged blob SHA-256
`692439c2e68d033b09cd0d03ab05a388fcad1b6686cdfe5ceef6d24e1a73c1c0`.
It contains one additive 41-line sibling, `cpcv_evaluate_distributional`, and
is 202 lines, under the 300-line limit. The pre-existing `cpcv_evaluate`
function itself is byte-identical to master: both function-source SHA-256
values are `c3bd69c2b0bfa09db0b21c7e1ebf6ba1410b3945cfebf3f3c75efb3111b2e1d8`.
The unchanged support files also match master as staged blobs:

| File | Master and staged SHA-256 |
|---|---|
| `scripts/platformkit/eval_gate/walkforward.py` | `9b5f87b0bbd4e0255489fc40f069f092439592f3c35a7b3037dd210648a1baeb` |
| `scripts/platformkit/cpcv.py` | `653428d8229541f66353698326e9921bf47586a799a994f9b21b12a0abcc1dc9` |

The new route calls the unchanged `cpcv_splits(..., embargo_blocks=0)` and the
existing `_blocked_indices` path, which imports the existing 48-hour purge and
3-day symmetric embargo helpers. The only `debug_disable_purge=True` call is
the declared synthetic construct rerun; MLB scoring uses its default False.

## Construct result

The in-file test and JSON artifact construct 32 seeded regular states plus one
planted state, with `random.Random(268)`. The planted state is 47 hours from
the target, shares a team, and carries the target's settled label in a training
feature. Normal CPCV removes it through the existing same-team purge; the
debug-only rerun retains it.

| Comparison | Brier | Required bar | Result |
|---|---:|---|---|
| New empirical route, normal purge | 0.25 | scalar match within 1e-9 | pass |
| Existing scalar `cpcv_evaluate` | 0.25 | scalar match within 1e-9 | pass; delta 0.0 |
| Debug-only purge disabled | 0.24242424242424243 | nonzero difference | pass; normal minus debug 0.007575757575757569 |
| Planted target, normal versus debug | 0.25 versus 0.0 | debug result strictly lower | pass |

The target comparison is non-tautological: the unpurged planted label produces
the strictly lower target loss, while normal CPCV does not hand it to the
predictor. The fixture records 33 route rows in both normal and scalar runs.

## MLB reproduction

The reproducible scorer is
`docs/evidence/harness/S268_distributional_evaluator_route_rescore.py` (staged
blob SHA-256 `3df7783f421de441179129c69d32362cc5e49c9420d1ede2c6b7cd61055931b0`).
It turns each corpus row into one state, adds the preregistered non-corpus
anchor solely to make the earliest real date testable, and uses 778 one-date
CPCV groups. The anchor is named before scoring and is not in the corpus
denominator. The completed result retains 3,000 unique corpus row ids over all
777 date clusters; no corpus row, cold start, or duplicate was dropped.

The predictor uses only handed training records whose player matches and whose
date is strictly earlier than the test date. A player with no such record uses
the preregistered `[0.0]` point mass. The full symmetric CPCV train side is
still constructed and purged before that as-of subset is selected.

| Quantity | Archived S244 | New route | New minus archived | Bar | Result |
|---|---:|---:|---:|---|---|
| CRPS | 0.5098297809224259 | 0.5098297809224259 | 0.0 | absolute delta <= 1e-9 | pass |
| Pinball q10 | 0.08655308369594088 | 0.08655308369594088 | 0.0 | absolute delta <= 1e-9 | pass |
| Pinball q50 | 0.37323931073931077 | 0.37323931073931077 | 0.0 | absolute delta <= 1e-9 | pass |
| Pinball q90 | 0.2013804110232682 | 0.2013804110232682 | 0.0 | absolute delta <= 1e-9 | pass |

`S268_distributional_evaluator_route_mlb_paired_losses_2026-09-04.csv` is the
Q9 differential archive. It contains every row id, cluster date, timestamp,
forecast sample sequence, training count, cold-start flag, archived and new
CRPS/pinball quantities, and their per-row deltas. Its deterministic scorer and
both named source files reconstruct every per-cluster mean without any live
state.

## Verification and contract self-check

Focused test, run alone after the implementation:

```text
python -m pytest tests/platformkit/test_s268_distributional_evaluator_route.py -q -p no:cacheprovider
1 passed
```

- B1: all 3,000 parsed corpus rows and all 777 clusters are named denominators;
  the preregistered anchor is the only non-corpus record and is explicitly
  outside that denominator.
- B2 and B6: the change is additive, with no renamed fields, moved module, or
  removed reader. The only new-route readers are the new test and reproducible
  scorer.
- B3-B5: no gate fall-through, claim-loop change, deployment, or external copy
  occurred.
- B7-B9: there are no renders, fitted comparison, or recycled denominator;
  both comparisons enumerate their stated units.
- B10 and Q3: every listed bar is the S268 bar without modification.
- Q1: the Git-blob preregistration seal above predates all metrics. Q2 is not
  applicable to this fixed baseline reproduction; no charged trial exists and
  no ledger was touched. Q4 uses the shared CPCV construction, purge, and
  symmetric nonzero embargo. Q5 has no AHEAD verdict. Q6 uses calibration-only
  language. Q7 has a 33-state construct and a 777-cluster scored enumeration.
  Q8 is the quoted before-condition. Q9 is the paired-loss archive above.
- A7: every evidence path named in this memo exists in this worktree.
