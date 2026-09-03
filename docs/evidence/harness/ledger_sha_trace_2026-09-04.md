# S191 system-ledger SHA trace audit

Verdict: NOT VALIDATED. The audit and append-only repair utility are implemented and
verified on a complete construct. The live results ledger was not changed because the
operator explicitly prohibited writes to the register and ledger for this run. Therefore
the live acceptance bar of zero untraceable rows is not claimed.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, including sections B and Q.
Summary artifact: `docs/evidence/ledger_sha_audit_summary_2026-09-04.json`.

## Premise first

The premise was re-measured before implementation over every line matching
`^\d{4}-\d{2}-\d{2}\s*\|` in `docs/evidence/RESULTS_LEDGER_SYSTEM.md`.
The file is 658,524 bytes, so it was safely below the 300 MB read guard.

| Metric | Spec measurement | Current observed | Required after | Projected after `--fix` |
|---|---:|---:|---:|---:|
| Data lines | 384 | 390 | 390 | 390 |
| Untraceable | 66/384 (17.19 pct) | 66/390 (16.92 pct) | 0/390 | 0/390 |
| Final field resolves | 276/384 (71.88 pct) | 284/390 (72.82 pct) | at least 276/390 | 350/390 (89.74 pct) |
| Hook rows resolving | 198/198 | 199/199 | untouched | 199/199 |

The premise is CONFIRMED at the grown denominator. It was not already fixed.

Field-count histogram over all 390 data rows:
`{4: 1, 5: 42, 6: 309, 7: 12, 8: 13, 10: 4, 11: 2, 12: 2, 13: 2, 14: 1, 17: 1, 24: 1}`.

## Ordered provenance recovery

The audit applied the spec's order to each of the 66 untraceable rows:

| Class | Rule | Count |
|---|---|---:|
| (a) | add-commit for a named `docs/evidence/harness/*.md` memo | 48 |
| (b) | commit subject contains an S-id from the row and a verdict word | 18 |
| (c) | neither; terminal `uncommitted:<reason>` | 0 |

Class (a) line numbers: 219, 225, 230, 231, 232, 233, 234, 235, 236, 238,
242, 243, 245, 248, 249, 252, 255, 257, 258, 259, 261, 264, 266, 267,
268, 275, 278, 282, 285, 289, 292, 298, 303, 306, 312, 314, 316, 317,
322, 326, 328, 331, 335, 339, 345, 346, 354, 362.

Class (b) line numbers: 226, 239, 271, 280, 288, 294, 297, 301, 307, 320,
325, 334, 340, 353, 356, 361, 364, 370.

Class (c) line numbers: none.

No SHA was sourced from a register row. In particular, no S16b register row was used.

## Untraceable rows before and after

Before line numbers: 219, 225, 226, 230, 231, 232, 233, 234, 235, 236, 238,
239, 242, 243, 245, 248, 249, 252, 255, 257, 258, 259, 261, 264, 266,
267, 268, 271, 275, 278, 280, 282, 285, 288, 289, 292, 294, 297, 298,
301, 303, 306, 307, 312, 314, 316, 317, 320, 322, 325, 326, 328, 331,
334, 335, 339, 340, 345, 346, 353, 354, 356, 361, 362, 364, 370.

Observed after line numbers: the same 66 lines, because the live ledger stayed
byte-identical under the operator's no-write instruction.

Projected after line numbers if `--fix` is authorized: none. All 66 recover through
class (a) or (b), so every appended final field would resolve to a commit.

## Implementation and reproduction

`scripts/platformkit/tracking/ledger_sha_audit.py` is stdlib-only and has no callers.
Default mode prints the two counts, percentages, histogram, hook check, line-number list,
and recovery split. `--fix` appends one final field only to currently untraceable rows.
It never changes a row that already resolves or a row already carrying `uncommitted:`.

Run in master:

```text
python scripts/platformkit/tracking/ledger_sha_audit.py
python -m pytest scripts/platformkit/tracking/test_ledger_sha_audit.py -q -p no:cacheprovider
```

Focused test result in a14: `1 passed in 5.54s`. The construct enumerates one existing
traceable row plus one row for each recovery class. It proves CRLF preservation, exact
prefix preservation before each appended field, untouched header and resolved row,
zero untraceable rows after repair, and idempotence on a second repair.

The protected `data/cache/eval_gate/backtest_fwer.jsonl` is absent from a14 by design.
Its documented main-only copy was read once and remains 18 rows with MD5
`a4ae7c13995672e478d59770591b83ba`. Nothing under `data/` was written.

## Contract self-check

- B1: every dated row is included; the 199 already-valid hook rows are not excluded.
- B2: no field, status, or reader changed; the utility is additive and has zero callers.
- B3-B6: no gate, claim lifecycle, deploy, move, retirement, import, or module reference changed.
- B7-B9: all 390 rows are enumerated; there is no sample, render, fitted residual, or recycled unit.
- B10 and Q3: the zero-row bar and final-field floor are unchanged.
- Q1, Q2, Q4, Q5, and Q9: no scored comparison, charged trial, OOS model, AHEAD verdict, or paired-loss claim exists.
- Q6: artifacts use calibration language only.
- Q7: N=390 is a CONSTRUCT enumeration of every matching data row.
- Q8: the premise was re-measured first and confirmed.
- No pod contact, copy, or deploy occurred. No flag was changed.

## NOT VERIFIED

- The live acceptance bar is not met: the protected ledger still has 66 untraceable rows.
- Live `--fix` behavior was not exercised against the project ledger.
- A live repaired artifact cannot establish prefix byte identity because the requested
  mutation was prohibited; that invariant is established only on the complete construct.
- The register and ledger were not updated, and no class (c) terminal marker was needed.
