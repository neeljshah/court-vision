# G380 producer provenance preregistration

Status: PREPARE-ONLY. This preregistration authorizes no pod run, replay, deploy,
ledger change, register change, or verdict. The Claude finisher measures.

## Binding premise and inputs

Before preparation, this lane read one named artifact at a time:

- `docs/evidence/tracking/g368_evaluated_tick_motion_2026-09-09/attribution.csv`
  (32,991 bytes): `FRESH_REPL` CLAMP_OR_SUBPIXEL held share is 66723/114064 =
  0.584961.
- `docs/evidence/tracking/g370_admission_v0_2026-09-09/decisions.csv`
  (8,121,640 bytes): 0/89655 rows carry any source label.
- `docs/evidence/tracking/g376_declared_tick_observations_2026-09-10/classification.csv`
  (33,206 bytes): SEALED34 is 28276/45842 and FRESH69 is 53250/89655
  producer-evaluated versus declared ticks.

The source-label premise holds. The planned change is additive only: append
`position_source`, `source_branch`, and `matched_event_id` to tracking rows; write
the actual sorted `evaluated_tick_ids` and `attempted_frames_capped` receipt at run
end; and append `evaluated_tick_receipt_path` to the completion ledger. Existing
columns, values, statuses, coordinates, clamps, cadence, weights, thresholds, and
flags must not move.

## Sealed measurement protocol

The finisher must use a per-attempt idempotent bind before worker dispatch; a repeat
attempt gets its own stable attempt key and never reuses or blocks on another
attempt's pending state. The bind must cover the weight glob, broad non-fatal
exception handling, cleanup of pending state, and the G328 worker-accounting route.

Five exhaustive CONSTRUCT controls are: fresh detection -> DETECTION, coast ->
PREDICTION, clamp -> CLAMP, subpixel hold -> SUBPIXEL, and id merge -> PREDICTION.
A missing event must be UNKNOWN, never dropped. An independently monkeypatched
import-time trace records branch entries and evaluated ticks. It is compared row by
row with producer stamps and receipts.

Any later paired scratch replay uses at least 30 preserved sections from at least 10
videos, even sampling, identical weights and caps, and one evaluator state for each
scored tick with a stable key. If any OOS comparison is made, it uses
`scripts/platformkit/eval_gate/walk_forward` or `cpcv_evaluate` with purge and a
symmetric nonzero embargo; its archived per-tick differential derives only from
evaluator records. Improvement convention is baseline loss minus candidate loss;
positive means candidate better. No such comparison is run by this lane.

Bars are unchanged: trace-label agreement 1.000000; receipt-trace agreement
1.000000; unchanged-field differences 0; paired median seconds ratio at most 1.10
on n >= 30; and live receipt coverage 1.000 on at least 30 sections from 10 videos.
The 30 source-coloured overlays must be evenly spaced and include HELD and CLAMP.
No deploy occurs before an authorized ACCEPT.

SEAL sha256 d04ee2c4873c621944a2596131d0603dd32d9e3533fbe0fc41274d6e76471c95
