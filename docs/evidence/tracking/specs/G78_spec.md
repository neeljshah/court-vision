GAP G78 | sport tennis | worktree a2 | log cx_g78_resolve_uncertain_ball_labels
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including the A7 clause; self-check
every line of section B before you report. THIS ROW PRODUCES A LABEL SET. It measures nothing else
and it fixes nothing.
WHY THIS ROW EXISTS: G44B attempt 3 was REJECTED, correctly, because the label set cannot yet
support an evaluation. Of G65's 150 labelled frames, **41 are ball-visible and 109 are `uncertain`**
(72.7 pct). The lane's reasoning, which is right and must be preserved: **the uncertain rows are not
valid negatives, and treating them as negatives would FABRICATE precision.** So recall and precision
are both unmeasurable and no gate change can be sized.
IT NAMED THE PRECONDITION, and this row is exactly that: resolve the 109 uncertain rows, and add
positives until there are **>= 100 resolved positives** in total (allowing a 50 fit / 50 held-out
split). 41 exist, so at least 59 more are needed.
METHOD -- do not invent one. G65 attempt 2 already found what works and attempt 1 found what does
not. Attempt 1 reviewed whole 1280x720 frames and got ZERO visible. Attempt 2 used a court-band crop
at 1.3x plus a tiled 2x fallback and got 41, with a documented second-pass recheck that flipped 8 of
30 calls from uncertain to visible. So apply MORE ZOOM to the 109, not a different method: go to the
tiled 2x path (or higher) for every one of them.
AN UNCERTAIN THAT SURVIVES A GENUINE TILED 2x-OR-BETTER LOOK IS A REAL LIMIT and stays uncertain.
The deliverable is the RESOLVED FRACTION with an honest residual, never a forced binary. A high
residual is a finding about what broadcast footage can support, and it bounds every recall claim
anyone will ever make on this corpus.
ALSO RESOLVE, because it gates whether a gate fix is worth building at all: G65 reports 32 of 41
visible balls inside `y < 2/3 * height` = **78.0 pct**, while G44 reported **~52 pct** of sightings.
G44B confirmed the evidence supports 78 pct but could not explain the gap. Re-derive BOTH on the
SAME stated denominator and say which is right. If the true figure is near 78 pct, the spatial gate
is NOT the dominant limiter and G44's remaining premise needs restating -- that would redirect the
whole tennis-ball workstream, so it is worth doing carefully.
ORIGINAL G65 CONTEXT: G44B has now stopped TWICE at its premise gate, and correctly both times. The
blocker is not footage (that was fixed) and not the detector. It is that **the per-frame ball labels
behind G44's headline never existed as an artifact**. G44 reported 64 pct of rally frames show a
ball and 52 pct of sightings fall inside the `y < 2/3 * height` gate, but only the SUMMARY survived:
the per-frame visibility and coordinate labels were never persisted. So no lane can compute recall,
compute precision, hold out a disjoint set, or re-analyse anything. Five lanes today were blocked by
missing per-item evidence; this is the tennis-ball instance of it.
DELIVERABLE: one durable, committed label file, and nothing more.
  (a) >= 150 rally frames, sampled SEEDED and EVENLY SPACED across >= 3 tennis clips. Not a head
      slice. State the seed, the clips, the frame indices and how you chose the rally windows.
      The local worktree links data/footage_corpus; the full 63-clip corpus is on the pod and listed
      in docs/evidence/tracking/FOOTAGE_CORPUS_INVENTORY.md. Frame work may run read-only on the pod.
  (b) For EACH sampled frame record exactly: clip, source_frame, ball_visible (true/false), and when
      visible the ball centre x and y in IMAGE PIXELS with the frame width and height alongside, plus
      an approximate ball radius in pixels. Declare the coordinate space explicitly -- these are
      image_px rows and they must never be confused with court_feet (the rung ladder is binding).
  (c) ZOOM METHOD -- MANDATORY, and attempt 1 failed on exactly this. Attempt 1 rendered whole
      1280x720 frames, could not resolve the ball in ANY of 150, and returned 100 pct uncertain.
      A broadcast-view tennis ball is 4-8 px; it is NOT reliably visible in a whole frame, and the
      orchestrator confirmed this by viewing one. G44 ALREADY SOLVED THIS and its method is the
      one to copy: crop to the COURT BAND and upscale (G44 used 1.3x), review at that zoom, then
      RE-CHECK a subset a second time -- G44's first pass under-counted and three of six
      spot-rechecked "not visible" calls turned out to have a visible ball at higher zoom. Do the
      same: a first pass, then a documented re-check pass, and report how many calls the re-check
      flipped. If you still cannot resolve the ball at court-band zoom, tile the court band into
      overlapping crops and view each tile magnified. Do not report 100 pct uncertain again without
      having tried both.
  (c2) Label by LOOKING. Render, view, record what you see.
      A label produced by running the existing detector and calling its output ground truth is
      circular and is an automatic REJECT (B7/B8) -- the whole point is to have truth INDEPENDENT of
      the detector you intend to evaluate.
  (d) Record honest uncertainty: an `uncertain` flag with a one-clause reason for any frame where you
      cannot tell (motion blur, occlusion, ball leaving frame). Do NOT force a binary call. Report
      how many you flagged; a high uncertain rate is itself a finding about the achievable ceiling.
  (e) Commit the label file AND the rendered frames under docs/evidence/tracking/g65_ball_labels/.
      Durability is the entire deliverable (A7).
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = label-set completeness and independence
  before        = no per-frame ball label set exists anywhere; only G44's summary numbers survive
  bar           = >= 150 frames labelled by eye across >= 3 clips, every field present or explicitly
                  uncertain-with-reason, the sampling reproducible from the stated seed, and the
                  labels demonstrably NOT produced by the detector under test
  n             = >= 150; state the exact count and the per-clip breakdown
  eye check     = this row IS the eye check. Describe what you saw, including the hard cases.
  must not move = every harness threshold, the detector, the solver, the coordinate contract. You
                  are creating evidence, not changing behaviour.
DO NOT, in this row: change MotionDiffDetector, propose a new spatial rule, or compute recall and
precision. That is G44B's job and it becomes possible the moment this lands. Staying out of it is
what keeps the evaluation honest -- the person who labels must not also tune the rule against the
labels in the same pass.
ALSO REPORT, in one line each, so G44B can be re-specified accurately: how many labelled frames have
a visible ball, and of those how many fall inside `y < 2/3 * height`. These two numbers are the
independent re-measurement of G44's 64 pct and 52 pct. If they disagree with G44, say so plainly --
that is a finding, not a failure.
EVIDENCE: docs/evidence/tracking/g78_resolve_uncertain_ball_labels_2026-09-0X.md with the sampling method, the
per-clip counts, the two re-measured fractions with Wilson intervals, the uncertain rate, and a
NOT VERIFIED list.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: read-only frame work is fine. No scp, no deploy, no daemon restart, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a2,
no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
