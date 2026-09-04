# S235 Event-Date Walk Default Preregistration

## Scope and machine

Run locally in `C:\Users\neelj\nba-track-a18` on the four existing read-only
gate corpora. Read exactly one corpus at a time. Do not write under `data/`, do
not modify the register or any ledger, and do not change an evaluation bar, the
S34 `SYNTHETIC` vintage label, or `data/registry/**`.

## Inputs and fixed comparison

The fixed archive references are:

```text
docs/evidence/calibration/nba_reliability_2026-09-03.json
docs/evidence/calibration/mlb_reliability_2026-09-03.json
docs/evidence/calibration/soccer_reliability_2026-09-03.json
docs/evidence/calibration/tennis_reliability_2026-09-03.json
docs/evidence/calibration/nba_reliability_per_unit_2026-09-03.json
docs/evidence/calibration/mlb_reliability_per_unit_2026-09-03.json
docs/evidence/calibration/soccer_reliability_per_unit_2026-09-03.json
docs/evidence/calibration/tennis_reliability_per_unit_2026-09-03.json
```

Every finite prediction and binary outcome is retained and every other row is
counted as dropped. The construct is the complete set of four sports; the
denominators must be NBA 1,814, MLB 39,162, soccer 25,834, and tennis 41,886,
with zero dropped rows.

Before the first scored run, source inspection will establish one shared
evaluator route under `scripts/platformkit/eval_gate/`. Its callback will
produce every scored calibrated probability from its supplied train state only.
The route must enforce the evaluator's purge and a symmetric nonzero embargo;
no local loop may score a probability outside that callback. The event-date
route partitions by `corpus_unit`, stable-sorts within each unit by
`event_date`, and never carries calibration history across a unit boundary.
The positional arm retains the historical row-order sequence.

## Fixed acceptance and limit

No-flag default results must reproduce the archived per-unit after-ECE values
at maximum absolute difference no greater than 1e-9: NBA 0.026583, MLB
0.012666, soccer 0.028722, tennis 0.015403. The `--positional` arm must
reproduce the old positional after-ECE values exactly: NBA 0.024843, MLB
0.008077, soccer 0.009302, tennis 0.008403. Existing output key names remain
unchanged. The `--per-unit` string remains a no-op alias.

Before implementation, reproduce both archived arms from the generated JSONs,
audit all `build_report` and `main` callers, and verify soccer's partition
identity is false because six divisions interleave. If changing the default
moves a frozen S05 calibration threshold or S22 mechanism-gate threshold, close
the row `CLOSED AT LIMIT`, name the threshold and numerical movement, and do
not lower a bar. Soccer's unfavorable calibration result and the WTA-dominated
tennis cost will be reported without omission.

## Evidence and checks

The rerun uses only `walk_forward` or `cpcv_evaluate` from
`scripts/platformkit/eval_gate/`, with purge and symmetric nonzero embargo
assertions. The resulting JSONs are regenerated through `main` with no flags
and with `--positional`, and the memo records the full input paths, byte sizes,
the evaluator source hashes, all four values, caller census, and the seal below.
The single new focused test covers both flags across all four sports and is run
alone. Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and
Q, especially Q1 and Q4.

Hashing rule: the seal is the SHA-256 of the exact UTF-8 bytes from the start
of this committed file through the newline immediately before this seal line.

Seal SHA-256 of the pre-seal content above: `76DFAB9C7F8DCF67947AC1AEF316B5B7600E6A73F8F6B008563F9948B629FB43`.
