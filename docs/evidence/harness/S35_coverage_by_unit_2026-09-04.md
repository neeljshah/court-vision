# S35 -- premise re-measure (Q8). FALSIFIED. 2026-09-04

## Row claim
`close_join.coverage_report.by_corpus_unit` groups MATCHED rows only, so per-unit
`join_rate` is 1.0 by construction and hides per-unit coverage holes wherever
`unjoined > 0` -- exactly the S03 case (ATP 84.4 / WTA 71.2).

## Premise re-measure (step 0) -- FALSIFIED
Register status for this exact row already reads `FIXED 2026-09-03 ff094421c`
(`docs/evidence/HARNESS_GAPS_2026-09-03.md:79`). Read the code on master today:

`scripts/platformkit/eval_gate/close_join.py:290-301`
```
    # S35: the FULL spine per unit is the denominator -- never `joined.loc[matched]`,
    # which would make every per-unit join_rate a tautological 1.0.
    by_unit = {
        str(unit): summary(frame) for unit, frame in joined.groupby("corpus_unit", sort=True)
    }
    unjoined = int((~matched).sum())
    if unjoined and any(u["join_rate"] == 1.0 for u in by_unit.values()):
        raise ValueError("degenerate by_corpus_unit denominator: per-unit rate 1.0 with unjoined rows")
```
`by_unit` groups `joined` (the FULL post-merge spine, pre-filter), not
`joined.loc[matched]`. `summary(frame)` (`close_join.py:274-286`) computes
`total = len(frame)` and `hit = frame["_spine_join"].eq("both").sum()` over that
full frame, so an unmatched row lowers the unit's `join_rate` instead of being
dropped before grouping. A guard at `:300-301` additionally raises if any unit's
rate is 1.0 while `unjoined > 0` anywhere in the corpus -- the exact degenerate
case the row warns about is now a hard error, not a silent pass.

### CONSTRUCT (n = 2, exhaustive)
One `corpus_unit` = `"TEST"`, 2 spine rows, row 1 `_spine_join == "both"`
(matched), row 2 `_spine_join == "left_only"` (unjoined):
- current code: `by_unit["TEST"] = {"denominator": 2, "joined": 1, "join_rate": 0.5, ...}`
- pre-S35 behaviour the row describes (`joined.loc[matched].groupby(...)`):
  `by_unit["TEST"] = {"denominator": 1, "joined": 1, "join_rate": 1.0, ...}` --
  the unjoined row is invisible.
Only the pre-fix construction can produce 1.0; the code on master today cannot,
by the guard at `:300-301` alone even before reading the arithmetic.

### Test evidence
`scripts/platformkit/eval_gate/test_close_join_tennis.py:63-95` asserts this
directly on the real tennis corpus (`by_corpus_unit` denominators sum to the
report denominator; each unit's `join_rate < 1.0` because `unjoined > 0` is
true for both ATP and WTA today; `# S35: the FULL spine is the denominator, so
a 1.0 rate is impossible here` at line 68).
```
python -m pytest scripts/platformkit/eval_gate/test_close_join_tennis.py -q
9 passed in 6.14s
```

## Verdict
FALSIFIED -- the gap this row describes does not exist on master; it was fixed
inside the S03 landing (`ff094421c`) and is guarded against regression by both
the `ValueError` in `coverage_report` and an existing per-file test. No spec
written; no code touched. Register row S35 already carries this verdict and
needs no further action.

## NOT VERIFIED
- Soccer/MLB/NBA-MLB `close_join_*` variants were not re-checked for the same
  pattern (row and fix are tennis/S03-scoped; out of scope for this premise
  check).
