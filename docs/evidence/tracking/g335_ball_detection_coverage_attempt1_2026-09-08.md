Attempt 1 (codex, stopped at the original premise: the 466 tracking tables carry no cls column); superseded by attempt 2 under spec VERSION 2026-09-08b.

VERDICT: PARTIAL -- PREMISE UNMEASURABLE; no `cls` field exists in the complete current pod tracking-table set, so the binding `cls == "ball"` census and all arms stopped before scoring.

# G335 ball detection coverage (2026-09-08)

Spec: `docs/evidence/tracking/specs/G335_spec.md`. Contract checked:
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections A, B, and Q.

WHERE: pod, read-only, because the binding source is the pod tracking ledger;
no GPU or route run was needed. Interpreter: Python 3.12.3.

PREMISE RE-RUN (whole set, one file header at a time): source root
`/workspace/nba-ai-system/data/tracking`, input glob
`*/tracking_data.csv`, n = 466 files. The exact binding output was:
`G335_BINDING_CENSUS tables_total=466 cls_header_tables=0 missing_cls_header=466 zero_ball_tables=UNDEFINED median_ball_rows_nonzero=UNDEFINED`

This is not a zero-ball result. Every current table lacks the field the
before-condition names, so `zero_ball_tables` and the nonzero-table median are
undefined rather than zero. The spec's claimed 165/173 census cannot be
reproduced against this current source. Treating a missing field as zero would
violate contract B3.

No scored comparison occurred, so no preregistration seal was required or
created. No section was decoded; raw, filter, tracker, writer, plausibility,
timing, recommendation, flag, source change, evaluator, or archive-loss result
exists. `stages.csv` and `arms.csv` record this explicit stop with zero-padded
integer n cells only; they do not stand in for an arm measurement.

Input handling: each CSV was opened only for its header, never loaded as a
whole store; no file above 300 MB was opened. No pod file, daemon, guard,
`data/`, registry, ledger, flag, threshold, or production code changed.
The orchestrator must commit these three evidence paths with an explicit
pathspec via `lane_commit`; this worktree's index is sandbox-denied.

SIGN CONVENTION: for any future comparison, improvement = baseline loss minus
candidate loss; positive means candidate better. No delta is reported here.

SELF-CHECK: B1-B10 pass by non-execution of a metric/schema change; Q1/Q4/Q5/Q9
are not applicable because no scoring occurred; Q6 language is calibration-only.

WALL TIME: 24 minutes (discovery and read-only binding census).
SHA-256: stages.csv 5dd64219dae1c165dfc12ae53b0f64164946ff197fd547dde1f72b4ee8e00c9a; arms.csv 2c64c4d40aeecc01e2c3df04318458198e7bb1738c10e8fe146179bdae766797.

NOT VERIFIED:
- The prior 165/173 source identity, its original table schema, and its byte set.
- Any ball detection, stage loss, coverage arm, plausibility proxy, timing, or flag behavior.
- Whether a `cls`-bearing tracking-table source is available outside the stated pod ledger root.
