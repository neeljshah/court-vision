# S231 Signal Combination Shrinkage Preregistration

## Scope and machine

Run locally in `C:\Users\neelj\nba-track-a17` on branch `track-a17` because
the task is a read-only reproduction and SCREEN-only calibration comparison.
No pod, data registry, FWER ledger, register, feature flag, or serving route is
used or changed.

## Inputs and premise

The premise comparison opens exactly one store at a time:

```text
data/cache/eval_gate/s114_ingame_ensemble_series.csv, 44,158,218 bytes, no resolution
data/cache/eval_gate/s114_ingame_ensemble.json, 29,727 bytes, no resolution
```

First recompute S114 k=1 and k=5 Brier differences from the archived series,
on its game clusters, and require maximum absolute difference at most 1e-9
against -0.000484 and -0.000400 respectively. If either fails, write the
S231 evidence memo with verdict FALSIFIED and do not fit weighting arms.

## Predeclared method

If the premise reproduces, add an opt-in module below `scripts/platformkit/`.
For every outer game-first-date walk-forward fold, preserve S114's screened
members without post-hoc member removal. Fit all weights only on strictly
earlier training rows. Score inverse-variance and James-Stein-shrunk weights,
and a ridge/logit stack whose penalty is chosen only in an earlier inner fold.
Use the existing shared evaluator's walk-forward or CPCV route with its purge
and symmetric nonzero embargo. The confidence ensemble is a further arm only
if its separately located input is present and under the read-size rail;
otherwise archive it as unavailable without silently dropping a scored arm.

For every scored arm, archive a same-row, per-tick paired-loss series with
game cluster and timestamp, Brier and log-loss comparisons to S114 k=5 and to
the raw in-play line, game-clustered interval, effective sample size, member
count, and fold weight vectors. The new per-file test appends future rows and
requires the weights fitted on the unchanged train window to be byte-identical.

## Predeclared bar and reporting

The immutable interestingness ceiling is S114 k=5 over k=1: +0.0000830. No
weighting arm above that ceiling is assumed. If none exceeds it, report CLOSED
AT LIMIT. Use calibration language only. This is SCREEN-only: no charge, no
ledger read or write, and no register change.

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.

Seal SHA-256 of the pre-seal content above: `DB5404DD9A9979B1B0FB7E6DC1BF3CC3744EFAD823F25A6CC61E018DAB5C86F3`.
