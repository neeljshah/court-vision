# S246 Box-Score Scoring Harness

## Verdict

FALSIFIED at premise step 0. No implementation, fixture JSON, score table, or
focused test was created. Q8 of
`docs/evidence/tracking/VERIFIER_CONTRACT.md` requires this close when the
premise is false.

## Scope and machine

Static source and evidence survey only, run locally in
`C:\Users\neelj\nba-track-a15` because S246 step 0 is a repository premise
check. No data store, raw closing-prop JSON, box score, pod, ledger, register,
or external input was opened. The direct inputs were:

```text
docs/evidence/tracking/specs/S246_spec.md, 3456 bytes, no resolution
docs/evidence/tracking/VERIFIER_CONTRACT.md, 11979 bytes, no resolution
docs/evidence/harness/S233_walkforward_embargo_prereg_2026-09-04.md, 5604 bytes, no resolution
docs/evidence/tracking/specs/S228_spec.md, 3830 bytes, no resolution
scripts/platformkit/eval_gate/walkforward.py, 8207 bytes, no resolution
```

## Premise remeasurement

The required file was searched in the working tree and Git index with:

```powershell
Get-ChildItem -Path 'scripts' -Recurse -File -Filter 'walkforward_embargo_prereg.py'
git ls-files | Select-String -Pattern 'walkforward_embargo_prereg\.py$'
Get-ChildItem -Path 'scripts/platformkit','tests/platformkit' -Recurse -File -Include '*.py' |
    Select-String -Pattern 'purge_embargo_walk_forward|seal_prereg|assert_sealed'
```

All three commands produced zero requested utility paths or export references.
`git log --all -- scripts/platformkit/eval_gate/walkforward_embargo_prereg.py`
also produced no history. The named commit `63d5ec4b7` exists, but its two
changed paths are S233 evidence memos only; it did not add the claimed module.

The existing `scripts/platformkit/eval_gate/walkforward.py` exposes
`walk_forward`, whose predictor contract returns one float. It is not the
requested `walkforward_embargo_prereg.py` utility and cannot serve as an
importable substitute without changing the S246 premise.

S233's committed evidence independently records the same premise
falsification. S228 is still an open spec: its required tidy table has no named
output path or committed S228 evidence memo. Therefore the raw
`data/cache/cv_fix/closing_props/` substitution was not opened; the missing S233
utility is an earlier blocking premise.

## Consequence

No CRPS, pinball, coverage, or comparison result was computed. The conditional
construct, its two fixture JSON files, and its focused test are not applicable
after the premise stop. No protected module, schema, threshold, ledger, or
register was changed.

## Verifier self-check

- B1-B10: no metric, row exclusion, schema, threshold, deployment, or route change was made.
- Q1-Q6 and Q9: no scoring or charged trial occurred.
- Q7: no construct was entered because the prerequisite failed.
- Q8: satisfied by the current worktree source and Git-index remeasurement.

## NOT VERIFIED

- The additive scoring harness was not built.
- The two fixture JSON files were not created.
- The focused S246 test was not created or run.
- The raw closing-prop store and any score table were not opened or produced.
