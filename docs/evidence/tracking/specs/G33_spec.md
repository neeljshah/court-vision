GAP G33 (new) | sport baseball | worktree a7 | log cx_g33_baseball_scale_bins
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it; self-check every line of
section B before you report. This is a MEASUREMENT-ONLY lane: no code change, no tolerance
change, no gate change. If you find yourself editing a detector, you have left the spec.
PREMISE (step 0): the two-reference scale gate (mound chord vs the 24 in pitching rubber, same
image row, 10 pct tolerance) validates 9 of 36 pitch segments (25.0 pct) and 73 of 332 pitch-view
frames (22.0 pct) across the four T5b MLB day clips. Nobody knows WHY the other 27 fail, so
nobody knows whether more day footage would help. Reproduce the 9/36 from
docs/evidence/tracking/baseball_scale_validation_2026-09-01/summary.json before starting. If it
does not reproduce, STOP and report FALSIFIED.
LIMIT (step 1): this lane IS the limit measurement. It bounds what more footage can buy. There
is no public broadcast benchmark for baseball (G09 Table D), and 15 of 27 baseball-family clips
are 360p (G27, recorded as an ACCESS LIMIT), so a 360p-dominated failure profile means more day
broadcasts buy nothing until the HLS route works.
CHANGE (step 2): none to any module. Render 3 EVENLY SPACED frames per segment across all 36
segments (108 renders) and bin each of the 27 failing segments into EXACTLY ONE of:
  chord_off_dirt | rubber_occluded | row_mismatch | not_pitch_view | resolution_360p
Report the bins as counts, plus the same bins for the 9 validated segments as a control.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = failure bin per segment (denominator = 36 pitch segments; 27 failing)
  before        = 9 of 36 validated (25.0 pct); 27 failures unexplained
  bar           = EVERY one of the 27 failures carries exactly one bin, no segment is left
                  unbinned or double-binned, and the bin counts are reported
  n             = 36 segments (CONSTRUCT: every segment is examined), 108 renders
  eye check     = the 108 renders themselves, 3 per segment EVENLY SPACED within the segment;
                  never the first 3 frames of a segment and never only the first segments
  must not move = the 10 pct tolerance, the same-image-row rule, the 24 in rubber constant, the
                  scale_status column, and every harness threshold
NON-TAUTOLOGY: bin by what the render shows, not by what the detector reported. If a segment
fails for two reasons, record the DECIDING one and note the second in a comment column.
GATES G36: if resolution_360p is the dominant bin, say so in the verdict line -- the orchestrator
will not dispatch the day-corpus growth lane, because more 360p footage buys nothing.
EVIDENCE: docs/evidence/tracking/baseball_scale_failure_bins_2026-09-04.md -- the per-segment bin
table, the bin counts, the 108-render tally, and a NOT VERIFIED list.
TEST: exactly one new per-file test for the binning helper; run only that file.
POD: rendering from the pod corpus is pod work; own nohup nice job, unique /tmp log, never kill
anything, no git on the pod, NO scp of any module.
COMMIT: explicit pathspec, in a7, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
