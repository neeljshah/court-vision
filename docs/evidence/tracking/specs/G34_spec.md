GAP G34 (new) | sport tennis + basketball + soccer | worktree a3 | log cx_g34_view_denominator
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. MEASUREMENT-ONLY lane: no model, no new dependency, no GPU.
ORCHESTRATOR DECISION, do not revisit it: the research plan wrote this as CLIP zero-shot
classification. The pod has no open_clip, no clip and no transformers, and zero new dependencies
is a standing default. CLIP was only ever the scaler; the hand labels ARE the measurement. This
lane is a hand-labeled census and nothing else. Do not install anything.
PREMISE (step 0): every coverage number in this program is quoted against DECODED frames, but a
fixed-camera lock only ever applies to rally or wide frames, so no limit in this program is
currently quotable against its true denominator. Confirm by reading the coverage lines in
docs/evidence/tracking/tennis_camera_lock_honest_measurement_2026-09-01.md. If the denominator is
already rally-based there, STOP and report FALSIFIED.
LIMIT (step 1): this lane IS the denominator that bounds every later coverage claim. It has no
bar to beat; it has a number to establish.
CHANGE (step 2): for each of the three sports, take a SEEDED, EVENLY SPACED census of 300 frames
from one full clip and hand-label each frame into the sport view classes:
  tennis     rally | non-rally (changeover, replay, close-up, crowd)
  basketball wide | pan | tight
  soccer     wide | non-wide (replay, close-up, crowd, tight)
Record the seed and every sampled frame index so the census is exactly reproducible. Report each
share with a WILSON 95 pct interval. Then state explicitly which existing denominators change and
by how much, without recomputing any existing published number in this lane.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = view-class share per sport (denominator = 300 census frames per sport)
  before        = no measured view share exists for any sport
  bar           = the report is complete and reproducible: 300 labels per sport, the seed and the
                  frame index list recorded, a share plus a Wilson 95 pct interval per class, and
                  a named list of the denominators that change. A number is not required to beat
                  anything.
  n             = 300 per sport, 900 total
  eye check     = the labeling itself is the eye check; frames must be EVENLY SPACED across the
                  whole clip, never a head slice, and the index list proves it
  must not move = every published coverage number (this lane reports the denominator, it does not
                  restate any existing metric), and every harness threshold
NON-TAUTOLOGY: label from the frame alone. Never label a frame using the solver output or the
harness verdict for that frame, or the denominator becomes a function of the thing it is meant to
bound.
EVIDENCE: docs/evidence/tracking/view_share_denominator_2026-09-04.md -- per-sport share table
with Wilson intervals, the seed and index lists, the list of affected denominators, and a NOT
VERIFIED list.
TEST: exactly one new per-file test for the Wilson interval helper and the census sampler; run
only that file.
POD: frame extraction from the pod corpus is pod work; own nohup nice job, unique /tmp log, never
kill anything, no git on the pod, NO scp of any module.
COMMIT: explicit pathspec, in a3, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
