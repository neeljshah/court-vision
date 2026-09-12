VERDICT: PARTIAL + NOT VALIDATED -- Producer boxes are stored in the TOPCUT-cropped frame and the CSV export never inverts the crop; the cause chain is code-derived and reproduces on all 60 ticks, but the observer's stage records omit model-call/cache identity, model-input key/shape, actual CSV values and the serialized join key, so the identity/reproduction bar is NOT VALIDATED (spec line 23).
Prereg: docs/evidence/tracking/g409_box_coordinate_cause_2026-09-12/prereg.md, seal fa227df1c8aecd6f46fbc779f71c3f5bedb0f76bdf252317e95b76e87668d697 (unaltered).

## Premise and cause chain
60 distinct exact-even ticks, 206 producer rows, 592 comparator boxes, 51 frozen pairs, and 5 silent ticks reproduce exactly. All 60 retained native sources rehash equal; the 206/206 export join is exact with no absent or duplicate key.
TOPCUT=60 is executed at src/pipeline/unified_pipeline.py:1693. The export writes bbox_x1=bbox[1], bbox_y1=bbox[0], bbox_x2=bbox[3], bbox_y2=bbox[2] at :2736-2739 without an uncrop.
The code-derived, unfitted transform native_y=stored_y+60 applies to all 206 rows: pair dy median -58.2 to 1.8 px (n=51), 44/51 within 15 px after versus 0/51 before; dx is unchanged (37/51 within 15 px).
All seven CONSTRUCT cases remain, with the existing controls retained without weakening. The 1/206 extent defect and 64 non-improving blind-mark rows remain separate.

## Actual detector-input eye check
All 60 native cards were re-rendered in renders/ with the original stored/mapped/comparator view plus a separate labelled ACTUAL DETECTOR INPUT panel containing frame[60:]. The prior 60 cards are retained byte-for-byte in renders_pre_fix1b/.
crop_rebind.csv binds each panel to the sealed frame index and archived crop record by recomputing the crop-array SHA-256; a missing hash or mismatch would print UNKNOWN on that card. Result: 60/60 MATCH.
card_panel_manifest.csv records one actual-detector-input panel per tick. This establishes the visible crop only; it does not validate model input identity.

## Controls and reproduction
construct_cases.csv retains the seven cases and records categorical control_route plus detailed control_route_v2, control_route_error, and the source SHA-256 before each PC import attempt; controls.csv is its explicit routed copy. Crop is an inline statement; box-store and CSV-export imports target their enclosing archived functions, with no route substituted on PC failure.
Two fresh PC processes rebuilt every Fix 1b table and card. repeats.json preserves parent fields identical and runs and adds command, stdout, returncode, and per-table digests.
Q6 field-aware scan covers the complete delivered path manifest, this memo, renamed verifier memo, test, and Fix 1b helper. SHA256SUMS declares the byte domain and covers every file except itself.

## NOT VERIFIED
- Model-call/cache identity: the prefetch/cache call at src/pipeline/unified_pipeline.py:1909 and detector call at :1917 were not captured with a model-call or cache identity.
- Model-input key/shape: the detector call at src/pipeline/unified_pipeline.py:1917 has no archived record of the model-input key or shape.
- Actual CSV values: the row construction at src/pipeline/unified_pipeline.py:2736-2739 was observed as a statement, but the actual values written by _checkpoint_csv at :3963-3972 were not captured.
- Serialized join key: the CSV write at src/pipeline/unified_pipeline.py:3970-3972 and G402 join were not captured as one serialized event key (observer record site scripts/platformkit/tracking/g409_observer.py:43).
- Historical inference equality, court geometry, training suitability, and compensating consumers remain NOT VERIFIED.

## Fix 1b (2026-09-12)
This PC-only correction rebinds the retained TOPCUT crop to every native frame and makes it separately visible on all 60 cards. It records route status for each unchanged control and refreshes repeat, scan, and checksum receipts. No pod re-trace is licensed; the missing call-site identities cannot be recaptured on this PC. Measurements, associations, residuals, and the 206 rows are unchanged.

## Fix 1d (2026-09-12)
control_route remains the categorical copied_statement value; control_route_v2 holds detail, and the exact-vocabulary test is restored.
Seven per-control imports target the crop/store/export boundary once each; 0/7 controls executed through an archived-function route, with failures retained per control.
Only owned receipts are refreshed; measurements, cards, transforms, and the PARTIAL + NOT VALIDATED verdict are unchanged.
