# S257 preregistration -- event-date default v2

## Scope and timing

This preregistration is sealed before the S257 correction and before either
post-correction arm is scored. It covers only
`scripts/platformkit/eval_gate/calibration_report.py`, its one new focused test,
and the evidence artifacts named below. This is an uncharged calibration
regeneration; no ledger is read or written and K is not applicable.

## Fixed inputs and route

Each sport is loaded separately with `load_gate_corpus(sport)`. The fixed
denominators are nba 1814, mlb 39162, soccer 25834, and tennis 41886, with zero
dropped rows required in both arms. The no-flag and `--per-unit` routes must
write the existing base paths
`docs/evidence/calibration/<sport>_reliability_2026-09-03.json`. The
`--positional` route must write the new positional-suffix paths and must not
move any reader path.

## Fixed comparison and acceptance bar

The comparison is after-ECE per sport. The no-flag base-path arm must reproduce
the archived S50 per-unit values and the `--positional` arm must reproduce the
archived positional values to max absolute difference at most 1e-9, with the
two values and the exact input/output paths reported in the S257 memo. Soccer's
six-division interleave and the WTA-dominated tennis cost are named without
selecting a preferred arm.

Every scored calibrated prediction must be produced through the shared
`cpcv_evaluate` or `walk_forward` evaluator callback, with its purge and a
symmetric, nonzero embargo asserted in the artifact. The paired-loss archive
must contain, for every scored row, both arm losses, cluster id, timestamp, and
an AS-OF/reconstructible route description. The report must retain the S05
calibration rule and S34 `SYNTHETIC` label unchanged.

## Planned checks

Run only the new focused test file. Check all imports/readers of the touched
schema and output paths; make no caller edits. Verify the committed seal below
using `git show HEAD:<path> | head -n <line-count> | sha256sum`, where the hash
input is every LF byte above the seal line.

Seal SHA-256: A9AF3C4330263D71A6A5E4A30286190F411610C2552FF99810EA6C5FC4F8FC3C
