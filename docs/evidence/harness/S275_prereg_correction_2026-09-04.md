# S275 corrected preregistration: explicit calibration-basis consumers

Status: SEALED BEFORE VALID S275 ACCEPTANCE SCORING.

Machine: local worktree `C:/Users/neelj/nba-track-a16`; the shared evaluator
and corpus cache are local, and no pod operation is authorized or required.

## Correction record

`S275_prereg_2026-09-04.md` was sealed before its NBA call, but selected the
legacy `*_reliability_2026-09-03.json` positional family. That is not the S50
positional reference family. Its NBA output is not used for the premise or any
acceptance table. This correction leaves every threshold unchanged and binds the
actual S50 references before the first valid S275 comparison.

## Scope and fixed targets

The binding premise remains: a fresh census confirms all three specified
consumer reads are implicit, `build_report()` lacks `positional` and `per_unit`,
and fresh reports at each base reproduce the S267 premise state. A false premise
closes S275 FALSIFIED without a change.

The only valid S50 targets are eight small files, opened one at a time:
`docs/evidence/calibration/{nba,mlb,soccer,tennis}_reliability_positional_2026-09-03.json`
for positional and the matching `_reliability_per_unit_2026-09-03.json` files
for per-unit. The evidence memo will list each path, byte size, and `ece_after`.

For all four sports, the fixed positional call is
`build_report(load_gate_corpus(sport), sport)` and the fixed per-unit call is
`build_report(load_gate_corpus(sport), sport, order_by="event_date",
unit_col="corpus_unit")`. These retain the existing walk-forward expanding-fit
route; no evaluator, model, corpus, or threshold is changed.

All eight fresh values must be within `1e-6` of these S50 targets. One immediate
second fresh run must be within `1e-9` of the new committed S275 reference JSON.
All four sports and both bases are mandatory. The three explicit consumer
readings must be invariant between each sport's positional and per-unit calls,
with absolute differences exactly `0.0`.

## Deliverables

The landing contains the additive report dictionaries, compatible consumers,
one focused construct test, a new eight-scalar reference JSON, a second-run
reproduction JSON, a flip-invariance diff table, and
`S275_key_explicit_consumers_v2_2026-09-04.md`. The memo cites this correction
path and seal, records all inputs and results, and uses calibration language.

Seal SHA-256 of every LF byte above this line: B28A61637DE1BAD1DDE730723EBE1242665A0CBF482A0A53A55EB9ADE376FA0D
