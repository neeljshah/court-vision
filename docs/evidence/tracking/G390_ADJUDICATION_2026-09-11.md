# G390 adjudication -- 2026-09-11

## Verifier verdicts
fix1b verifier (verbatim): `VERDICT: REJECT`

att1 verifier (verbatim): `VERDICT: REJECT`

## Orchestrator adjudication
ACCEPTANCE-1 is unmet. The sealed preregistration names readiness digest `fe8bcbe...`; G389's landed correction made the actual readiness file `d11a1c8c...`. The sealed preregistration cannot be altered. This is a disclosed Q1 identity deviation, while the loaded landed G389 frame/reference inputs are named and SHA-256 hashed in the G390 memo.

B5 is unmet. Compute occurred under `/workspace/g390_scratch`, not `/workspace/wt/a11`. This is a disclosed process deviation. The preregistration permits exactly one A8 execution, and that allowance is spent, so the run cannot be repeated to repair the path.

ACCEPTANCE-3 is repaired. The 30 deterministic, evenly spaced native-frame renders now overlay the reference boxes, archived deployed-route A0 predictions, and archived A8 predictions. They were regenerated from `predictions_paired.csv` and `predictions_A8.csv` only; no model was loaded and no inference occurred. The old set remains under `renders/pre_fix1c/`.

The verifier reproduced the measurement identically twice: A8 TP 90 / FP 169 / FN 212; C0 0.1639; Wilson95 lower 0.2921; ALL FP/188 0.8989; ABSENT-only 50/188 = 0.2660; A0 0/8/302. All sealed quality bars are missed.

Landing status = NOT VALIDATED (adjudicated): the sealed quality bars are missed and the arm allowance is spent. No threshold moved and no operational adoption follows.
