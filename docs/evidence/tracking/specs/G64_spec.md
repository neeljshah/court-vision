GAP G64 | sport baseball | worktree a9 | log cx_g64_segment_count_bisect
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check every
line of section B before you report. BISECT, do not fix. Name what changed; stop there.
PREMISE (step 0, reproduce it): G33B attempt 2 located both 2026-09-01 DAY clips on the pod and
re-ran the historical pipeline read-only. It got **32 segments (19 + 13)** where the retained
artifact `baseball_scale_validation_2026-09-01/summary.json` records **30 (19 + 11)**. The lane
controlled for the obvious suspect by injecting the historic green-precondition function read-only;
that ALSO produced 32, so the G61 `gate_mode` change is NOT the cause. Reproduce the 32 and the 30
yourself before proceeding. Read docs/evidence/tracking/g33b_baseball_scale_bins_2026-09-02.md first.
WHY THIS MATTERS MORE THAN THE ROW THAT FOUND IT: G53 repaired the PROVENANCE of the day fraction
9/30, but 9/30 is now known to be reproducible only FROM THE RETAINED ARTIFACT and not by re-running
the pipeline. That makes it frozen evidence rather than a recomputable measurement, and the
21-failure binning G36 depends on cannot be reconstructed at all. G36 stays BLOCKED until this row
reports.
BISECT (step 1): the thing that moved is the SEGMENT COUNT, so bisect the count, not the scale
fraction. The second clip moved 11 -> 13 while the first held at 19, so start there -- a change that
affects one clip and not the other is a strong constraint and you should say what it rules out.
Candidate axes, and you must state which you tested and which you did not:
  (a) the code -- walk `git log` for the segmenter, the pitch-view gate and the scale-validation
      driver between 2026-09-01 and now, and test the specific commits that touch segment
      boundaries. Note that the environment stamp helper landed today
      (scripts/platformkit/tracking/run_environment.py) -- ATTACH A STAMP to every run you make, so
      this row does not itself become unreproducible.
  (b) the ENVIRONMENT -- this is a live and cheap hypothesis, not a formality. G52 was resolved
      today by exactly this: the same tennis code gives different coverage on local cv2 4.11.0 vs
      pod cv2 4.14.0, and a "non-reproducible pipeline" turned out to be two environments. The pod
      was rebuilt and its cv2 pinned during this program's lifetime. Establish what cv2 the
      2026-09-01 run used if you can, and say so if you cannot.
  (c) the FOOTAGE -- confirm by hash that the clips on the pod today are byte-identical to what the
      2026-09-01 run consumed, or state that you cannot confirm it. A re-downloaded clip is a
      perfectly ordinary explanation and it must be ruled in or out, not assumed away.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = the segment count per clip on a re-run, against the retained 19 and 11
  before        = 32 (19 + 13) re-run versus 30 (19 + 11) retained, cause unknown
  bar           = THERE IS NO PASS BAR. This row succeeds by NAMING the axis that moved the count,
                  with the evidence. "The footage changed" and "cv2 changed" and "commit X changed
                  the segmenter" are all good answers. "Cannot determine, and here is what I ruled
                  out with what evidence" is an acceptable answer and must list the ruled-out axes.
  n             = both day clips, every segment; state counts, never a sample
  eye check     = view the 2 extra segments on the second clip and say what they are. Two segments
                  that appeared from nowhere are the most informative thing here, and a count
                  compared without looking at what it counted is not a measurement.
  must not move = every harness threshold, the segment definition as the 2026-09-01 run applied it,
                  the G11 night verdict, and the retained artifact itself. Do NOT regenerate or
                  overwrite summary.json -- it is the only surviving record of the original run.
NON-TAUTOLOGY: do not conclude "the code changed" from the mere existence of commits. Show the
count moving when you move that one thing, or say you could not isolate it (B1).
DURABILITY (A7): commit every re-run's output and its environment stamp under
docs/evidence/tracking/g64_segment_bisect/ BEFORE reporting.
FOOTAGE: both clips are on the pod; the corpus is listed in
docs/evidence/tracking/FOOTAGE_CORPUS_INVENTORY.md. Frame work runs read-only on the pod.
EVIDENCE: docs/evidence/tracking/g64_segment_count_bisect_2026-09-0X.md with the reproduced counts,
the axes tested and ruled out, the named cause or an honest cannot-determine, the two extra segments
described from having viewed them, and a NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. No scp, no deploy, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a9,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
