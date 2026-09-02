GAP G67 | sport soccer | worktree a6 | log cx_g67_box_solvable_share
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. PURE CENSUS. No detector runs. No solver is written.
WHY THIS ROW EXISTS: G47 established that the blocker for 4 of 8 sports is CALIBRATION, not
tracking quality -- 119 of 187 harness reports were rejected on coordinate_contract alone, before
coverage, oob or jump could say anything, because the producers correctly declare `image_px` and
image_px can never pass court_feet. The calibration strategy
(docs/evidence/tracking/CALIBRATION_STRATEGY_2026-09-02.md -- READ IT FIRST) ranks soccer as the
MOST tractable of the four: the solve, validation and stability stack already exists in
domains/soccer/tracking/geometry.py (>= 5 landmarks, leave-one-out at 2.0 m, temporal calibrator)
against 15 canonical landmarks defined in keypoint_calib.py. The ONE missing component is a
penalty-box corner provider -- the current keypoint provider names only the centre circle, whose
three points are COLLINEAR and therefore degenerate for a homography.
Before anyone writes that provider, this row answers the only question that decides whether it is
worth writing: how much of a real broadcast actually shows a fittable penalty box.
METRIC: `box_solvable_share` = frames where a human judges ALL FOUR penalty-box lines (goal line,
16.5 m line, both box side lines) discernible with enough extent to fit lines, divided by ALL
sampled decoded frames.
  - Secondary labels per tile, mutually exclusive: BOX_SOLVABLE / WIDE_NO_BOX / NON_WIDE.
  - Report per clip AND pooled, each with a Wilson 95 pct interval.
DENOMINATOR, and this is the part that has gone wrong before: ALL sampled decoded frames. NEVER
"wide frames only" and NEVER "frames a detector accepted" -- conditioning the denominator on the
outcome is B1 and this program has already been bitten by it (G40). The wide share falls out of the
same labels as a free cross-check against G34's measured 0.65 [0.594, 0.702]; report it and say
whether it agrees.
SAMPLING: all 5 pod soccer clips. Per clip stride = total_frames // 300, indices 0, s, 2s, ...
for 300 tiles. 1,500 tiles total. This is the exact arithmetic sequence G34 used -- reproducible
from total_frames and N with no RNG, and it is NOT a head slice. State total_frames and the stride
per clip.
EYE CHECK: every one of the 1,500 tiles is viewed and labelled. That IS the measurement. Then take
a SEEDED random 20-tile subsample of BOX_SOLVABLE and re-read those at full resolution to confirm
the tile-scale judgment (the football borderline-sheet precedent). Record the seed. Report any
disagreement between the tile judgment and the full-res re-read -- a high disagreement rate is a
finding about the method, not something to smooth over.
DECISION RULE, pre-registered here BEFORE measuring so it cannot be moved afterwards: if pooled
`box_solvable_share` is below about 0.10, the box-corner route calibrates too little of the
broadcast to change the harness picture, and this lane reports that limit honestly and NO solver
gets written. A low number is a successful outcome for this row.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = box_solvable_share, per clip and pooled, with Wilson 95 pct intervals
  before        = never measured; the wide-view share is 0.65 but box solvability is unknown
  bar           = THERE IS NO PASS BAR. Success is an exhaustive, viewed, reproducible census with
                  stated denominators. High and low are equally good answers.
  n             = 1,500 tiles, none skipped; state the per-clip counts
  eye check     = all 1,500 tiles plus the seeded 20-tile full-res re-read
  must not move = every harness threshold, the coordinate contract, and every existing verdict.
                  This row runs NO detector and writes NO solver.
DURABILITY (A7): contact sheets with BURNED-IN frame indices, the per-tile label file and the
seed all go under docs/evidence/tracking/g67_box_census/ BEFORE you report. Never /tmp -- that rule
exists because evidence in pod /tmp has already been destroyed twice (G54).
FOOTAGE: soccer footage is POD-ONLY. See docs/evidence/tracking/FOOTAGE_CORPUS_INVENTORY.md (5
soccer clips). Run the census read-only on the pod.
EVIDENCE: docs/evidence/tracking/g67_box_solvable_share_2026-09-0X.md with the per-clip and pooled
shares with intervals, the stride and total_frames per clip, the wide-share cross-check against
0.65, the re-read disagreement rate, the decision-rule verdict stated explicitly, and a
NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. No scp, no deploy, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a6,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
