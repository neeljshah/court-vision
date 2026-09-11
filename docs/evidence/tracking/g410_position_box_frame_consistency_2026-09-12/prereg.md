# G410 Position/Box Frame Consistency Preregistration

Status: PREPARE-ONLY. This preregistration authorizes no replay, rating,
inference, scoring, pod job, deployment, restart, register update, ledger update,
or data write. The Claude finisher measures.

## Binding premise remeasurement

The whole bounded G402 population was enumerated before this preparation. Output:
`BINDING_G402_ROWS=19087`, `BINDING_CLAMP=9354`,
`BINDING_SUBPIXEL=1399`, `BINDING_COMPLETE_SECTIONS=59`,
`BINDING_RAW_IDENTITY_MISSES=0`, `BINDING_MISSING_RAW_STORES=0`,
`BINDING_RETAINED_SOURCE_RECEIPTS=60`, and
`BINDING_BLANK_ROUTE_LABELS=0`. The source labels are CLAMP, DETECTION,
PREDICTION, and SUBPIXEL. G380 semantics identify CLAMP as the final clamp
label and SUBPIXEL as the final subpixel label; the recorded source branch is
retained independently. The source-bound raw rows and their actual route are
recoverable. Matrix and predecessor history remain unmeasured bindings, not
coordinate inferences.

## Fixed inputs and identity

The parent bounded rows are
`docs/evidence/tracking/g402_mixed_provenance_target_mask_2026-09-11/target_mask.csv`.
Raw rows are read only from the matching per-section
`raw_tables/<draw_kind>/<section_id>/tracking_data.csv`; source identity and
native dimensions are taken from `source_receipts.csv`; planned section/window
identity is taken from `launch_receipts.csv`. G380 final-label and branch
semantics are retained from
`docs/evidence/tracking/g380_producer_provenance_2026-09-10/trace.csv` and
`summary.json`. No source artifact is substituted.

## Sealed future measurement protocol

1. Build separate ordered distinct tick populations for CLAMP and SUBPIXEL from
   all bounded parent rows, ordered by draw_kind, section_id, and frame. Draw
   index j of 30 with floor(j*(N-1)/29+0.5). Shared ticks are processed once
   and reported by both classes. Do not replenish a deficient class.
2. Retain every row at each selected tick and only a same-track predecessor
   inside the same sealed parent window. A missing initial predecessor is
   UNKNOWN and is never bridged across a window.
3. Archive the observed invocation's pre/post boxes, raw projected foot,
   matrix inputs, crop origin, native and cropped dimensions, prior position,
   branch inputs, rounding, and serialized output. Hash every exercised route,
   model, and configuration before execution.
4. Independently reproduce declared homogeneous projection, coordinate origin,
   branch operation, rounding, and serialized values for the same invocation.
   Compare same-invocation observations only; no second run supplies identity.
5. Classify each selected row only as CONSISTENT_BY_CONTRACT, FRAME_MISMATCH,
   BRANCH_MISMATCH, STALE_BOX, or UNKNOWN. Record current-box and
   retained-position ages separately. Retention under CLAMP or SUBPIXEL alone
   is not a defect.
6. Construct corner and foot projections test cropped/native origin handling;
   never shift court coordinates by a display offset.

## Fixed bars and closure

The unchanged bars are exactly 30 distinct even ticks per class when supply
permits, all selected rows and predecessor failures retained, and at least 30
same-invocation checks per class when bindings permit. Missing supply produces
PARTIAL without replenishment. Missing bindings produce PARTIAL; no position
quality conclusion follows. No calibration comparison is planned. If a later
comparison is authorized, improvement means baseline loss minus candidate loss;
a positive value means the candidate has lower loss, and it must use the shared
evaluator with purge and symmetric nonzero embargo.

## Planned outputs

The finisher will populate only the G410 evidence directory: input hashes,
source receipts, population, draw, branch and matrix traces, contract checks,
unknowns, construct cases, summary, repeats, eye index, renders, launch and
runtime receipts, Q6 scan, and SHA256SUMS. This lane's current memo is a
prepare-only skeleton and reports no measurement.
SEAL sha256 497659f96001e23d148af3f3358839afd8051efd2f19d97fe52722d790a795d5
