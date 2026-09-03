# S179 fold-key purge premise, 2026-09-04

## Outcome

VERDICT: FALSIFIED.

The required S06 source store is absent from this worktree:
`data/cache/eval_gate/s06_stacker_series_2026-09-03.csv`.
The directory `data/cache/eval_gate` exists, but the named file does not.
An exhaustive filename search of this worktree found no copy, `git ls-files`
reports it is not tracked, and `git check-ignore -v` identifies the applicable
ignore rule as `.gitignore:516:data/*`.

S179 requires a read-only re-measurement of both named corpora before code is
touched. Its S06 acceptance denominator, fold enumeration, before value, and
the required two-corpus zero-row check cannot be reproduced without that
source. Per the specification's premise rule and verifier Q8, work stops here
rather than substituting a different local store or modifying the fold logic.

The distinct S88 input is present at
`docs/evidence/harness/s88_phase_recal_2026-09-04.csv` (4,311,731 bytes), but
it is not a substitute for the absent S06 corpus. No partial one-corpus result
is reported.

## Reproduction

Run from this worktree:

```powershell
Test-Path data/cache/eval_gate/s06_stacker_series_2026-09-03.csv
Get-ChildItem -Path . -Recurse -File -Filter 's06_stacker_series_2026-09-03.csv' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
git ls-files --error-unmatch -- data/cache/eval_gate/s06_stacker_series_2026-09-03.csv
git check-ignore -v data/cache/eval_gate/s06_stacker_series_2026-09-03.csv
```

Observed results: `False`, no filename matches, `NOT_TRACKED`, and the ignore
rule above. The machine-readable summary and zero-fold artifact are beside this
memo.

## No change

No implementation, test, archive, corpus, threshold, FWER ledger, register,
or deployment changed. The required new per-file test is not applicable: this
FALSIFIED premise result makes no behavior change to test.

## Verifier self-check

- B1: no metric is claimed, and no rows were excluded from a claimed metric.
- B2: no schema or reader changed.
- B3-B6: no gate, claim lifecycle, deployment, module move, or retirement changed.
- B7-B9: no rendered, fitted, or scored evidence is claimed.
- B10 and Q3: no threshold changed.
- Q1-Q2/Q4-Q5/Q9: no scored comparison, charge, model result, or AHEAD result exists.
- Q6: this is an ASCII calibration-language artifact.
- Q7: no sampled or scored metric is reported.
- Q8: the premise availability check occurred before any code change.

## NOT VERIFIED

- The S06 before count, 12-fold table, and post-cut row count were not recomputed because their only named source is unavailable.
- The S88 count, re-quote, and confidence intervals were not run because S179 requires both premise sources before scoring.
- The proposed opt-in rule was not implemented or tested.
- No artifact in this result establishes a calibration comparison.
