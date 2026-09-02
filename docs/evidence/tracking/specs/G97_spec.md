GAP G97 | sport basketball | worktree a8 | log cx_g97_g84_render_durability
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. An EVIDENCE DURABILITY repair with a live consumer waiting.
WHAT BLOCKED. G93 was dispatched today to measure basketball line DETECTION RECALL on the 33 seeded
G84 frames. It preregistered its correspondence rule, wrote its test, and then honestly refused to
report, because the G84 source contact sheets it needed are ABSENT. That refusal was correct and it
is the third time in two days that a row has been blocked by evidence that did not survive: G38B
found zero retained tennis tables, G83 could not verify its adapter run, and now this. Read
docs/evidence/tracking/EVIDENCE_DURABILITY_AUDIT_2026-09-02.md before starting.
THE TASK, and it has two halves that must not be confused:
  1. REGENERATE the G84 frame renders so G93 can run. The selection is already fixed and committed:
     docs/evidence/tracking/g84_candidate_quality/selection.json (seed 84092026, 33 frames, 11
     clips) and sample_manifest.csv. Regenerate from the SAME selection -- do not draw a new
     sample, do not change the seed. A different frame set would make the G84 precision number and
     the G93 recall number describe different frames, which is how two true numbers combine into a
     false one.
  2. DIAGNOSE why they did not survive, in one paragraph, and say what would have kept them. The
     candidates worth checking: they were committed only inside a codex worktree that the dispatch
     wrapper later hard-resets to master; they were written under a gitignored tree (data/ and
     vault/ are gitignored and ABSENT in a worktree); or they were never committed at all. The
     wrapper provisions read-only junctions with worktree_data_links.py and resets the worktree on
     every dispatch, so a render written to the wrong side of that line is deleted by design. Name
     which of these actually happened, from the reflog and the tree, rather than guessing.
VERIFY THE REGENERATION IS FAITHFUL, do not just produce images. For at least 4 of the 33 frames,
re-derive the candidate counts and check them against the committed sample_manifest.csv. If a count
does not reproduce, the environment has drifted and that is a bigger finding than the missing
renders -- report it and stop rather than shipping renders that do not match the manifest. Note the
precedent: G52 was resolved when local cv2 4.11 and pod cv2 4.14 turned out to be two environments
being compared as one, so state the cv2 version you rendered with.
DO NOT re-run the G84 audit, do not relabel anything, do not change any threshold or detector
parameter, and do not touch line_calibration.py. This row restores an input; it does not re-measure.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = number of the 33 G84 frames with a committed, readable render, plus the number of
                  spot-checked frames whose candidate count reproduces the committed manifest
  before        = 0 of 33 renders present; G93 blocked
  bar           = 33 of 33 renders committed and readable, AND at least 4 of 4 spot-checked
                  candidate counts matching sample_manifest.csv exactly, AND a named cause for the
                  loss. A count that does NOT reproduce is a valid stopping point and a real
                  finding; report it rather than papering over it.
  n             = all 33 frames; at least 4 spot-checked against the manifest
  eye check     = open at least 4 of the regenerated renders and confirm they show a basketball
                  court frame with candidates drawn, not an empty or corrupt image. A committed
                  file that does not open is the same outage in a new costume.
  must not move = the G84 seed and selection, sample_manifest.csv, per_group_labels.csv, every
                  detector parameter, line_calibration.py, and every harness threshold
EVIDENCE: docs/evidence/tracking/g97_g84_render_durability_2026-09-0X.md with the regenerated count,
the spot-check table, the cv2 version, the named cause, what would have prevented it, and a NOT
VERIFIED list. Commit the renders under docs/evidence/tracking/g84_candidate_quality/renders/
BEFORE reporting (A7) -- that is the path G93 will look for.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY, pull clips only. Never kill anything -- the track daemon and seven footage bridge
lanes are live.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a8,
no push. Report the sha. The renders MUST be committed to a tracked path, which is the entire point
of this row.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
