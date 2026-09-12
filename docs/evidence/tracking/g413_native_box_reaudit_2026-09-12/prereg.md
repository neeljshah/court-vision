# G413 native box re-audit preregistration

Status: PREPARE-ONLY. This file seals the finisher's fixed procedure; it reports no
measurement, residual, association, review, or verdict.

## Binding prerequisite

Before any measurement, require the accepted G412 contract handoff, including its full
input and transform hashes, preserved G406 outputs, and the 60 original draw keys. At
preparation time this worktree has no `g412_box_frame_contract_2026-09-12` evidence
directory. The finisher must record that handoff path and hashes in `input_hashes.csv`.
If it remains absent, write PARTIAL with the exact before-condition output and perform
no association or residual calculation.

## Fixed inputs and identity

- Parent inputs: the landed G406 draw, source receipts, all 206 producer rows, all 592
  comparator boxes, historical associations, and five producer-silent ticks.
- Draw: all 60 exact-even keys; retain every source/frame/PTS receipt and every decode
  failure. The planned denominator is 60 frames, never only frames with boxes.
- Handoff transform: use only G412's accepted origin, inward padding, clipping order,
  branch labels, and deterministic IoU 0.50 association tie rule. No alternate rule,
  rematch, threshold, assignment, subset, or tuning pass is permitted.
- Identity: record SHA-256, byte size, full worktree-resolved path, dimensions, PTS, and
  route/config hashes. The model set is explicitly empty because no inference is allowed.

## Fixed transformation and accounting

For stored xyxy B, apply only the accepted native padded form
`(Bx1, By1+60, Bx2, By2+60)` and native unpadded detector-form
`(Bx1+15, By1+75, Bx2-15, By2+45)`, clipping in cropped dimensions before origin
restoration. Preserve every parent coordinate, target weight, and position source, then
add native coordinates, transform status, and clip flags. Fractional or predicted boxes
remain nominal detector-form and are never called fresh detections.

Keep all transforms, invalids, UNKNOWNs, unmatched producer and comparator boxes, and
silent ticks. Archive historical 51 pairs and state their 28 unique frames without
inflating their count. New association is one sealed full-population pass only.

## Fixed residual rule

For newly matched frames only, calculate per-frame median signed dx and dy, then
equal-frame-weighted signed medians; pool absolute residual p50, p90, and maximum by
kind and overall. Residual consistency requires at least 30 distinct newly matched
frames and both absolute equal-frame median dx and dy at most 5 px. Fewer matched frames
is PARTIAL; a failed budget is residual NOT VALIDATED; neither permits a change.

Any future delta uses: improvement = baseline loss minus candidate loss; positive means
candidate better. This is a diagnostic protocol and makes no calibration claim.

## Required retained artifacts

The finisher writes the specified G413 memo and directory tables, all 60 cards/renders,
two fresh-process repeat receipts, runtime receipts, a complete field-aware vocabulary
scan, and byte-domain SHA256SUMS. The memo ends with the required NOT VERIFIED list.
The only permitted test is `python -m pytest tests/platformkit/test_g413_native_box_reaudit.py -q`.
SEAL sha256 387cacc1e0b0084007b559318915d0aef109a1b76d1024ba92b5f819133381c4
