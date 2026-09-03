# S193 Teacher Census: FALSIFIED

## Premise-first result

S193 requires a read-only census of `data/tracking` and a comparison against
`data/cache/eval_gate/gate_corpus_nba.parquet`. In worktree `track-a12`, the
input paths were checked before any census, aggregation, scoring, or output
parquet work:

| Path | Exists | Result |
|---|---:|---|
| `data/` | yes | directory exists |
| `data/tracking` | no | census source unavailable |
| `data/cache/eval_gate/gate_corpus_nba.parquet` | no | gate denominator unavailable |
| `data/cache/eval_gate/backtest_fwer.jsonl` | no | protected comparison target unavailable |

The required premise is therefore FALSIFIED in this worktree. The specified
counts, as-of rows, coverage denominators, and medians cannot be reproduced
without the two required inputs. No alternate location was read or aliased.

## Closed-at-premise scope

- No module, test, parquet, or summary JSON was created because S193 directs a
  stop when its premise is falsified.
- No file under `data/` was written or read as a store.
- `student_gate.py` was read only to confirm the stated threshold constants;
  it was not changed.
- No register, ledger, flag, or protected input was touched.
- This memo makes no scored or calibration-performance claim. The named next
  gate remains unavailable until the required inputs are present in this
  worktree.

## Verifier self-check

| Check | Result |
|---|---|
| B1-B10 | Pass by non-execution: no metric, schema change, gate, deployment, move, or threshold change occurred. |
| Q1-Q6 | Not applicable: no scored comparison, preregistration, ledger action, or claim occurred. |
| Q7 | Not applicable: no constructed or sampled result was written. |
| Q8 | Pass: the premise was re-measured before work. |
| Q9 | Not applicable: no comparison or differential exists. |

## Verdict

FALSIFIED. S193 is closed at the premise in `track-a12`; no implementation was
attempted.

## NOT VERIFIED

- Census counts and 158-row output: inputs absent.
- Calibration scoring and next gate: not run.
