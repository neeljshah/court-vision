GAP G161 | sport tennis | worktree a6 | log cx_g161_rally_denominator
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A3, A7 and Q8; self-check
section B before reporting. This row CREATES GROUND TRUTH. Move no threshold, no bar, no verdict.

WHY THIS IS THE TENNIS LEVER. The program's own verdict is that what works for tennis is the
classical solver on SELECTED RALLY-VIEW RANGES, not on whole clips. Every attempt to say how good
tennis coverage really is has then stalled on the same missing thing: **there is no per-frame rally
label for the clips we actually hold.** G152b measured declaration at 2,597/28,773 = 9.0258 pct of
decoded frames and geometry-backed rows at 1,350/28,773 = 4.6919 pct on the local reference clip, and
had to report the rally-only rate as UNMEASURED because no label exists. G34's 125/300 = 41.7 pct
(Wilson [0.362, 0.473]) is a hand census of a DIFFERENT video and must never be imported as this
clip's denominator. Until the rally denominator exists for a clip we hold, the 0.90 coverage bar
cannot be adjudicated honestly in either direction.

BUILD THE DENOMINATOR, for the local reference tennis clip:
  (a) Draw a SEEDED, EVENLY SPACED sample of at least 300 frames across the whole clip. State the
      seed and the spacing. A3 and B7 bind hard here: a head slice or a rally-biased sample makes the
      whole row worthless, and G11 v1 reported 0.93 where the honest number was 0.78 for exactly this
      reason.
  (b) Hand-label each sampled frame RALLY-VIEW or NOT, against a written rule you fix BEFORE you
      start labelling and quote in the memo. Say what a replay, a close-up, a crowd shot, a scoreline
      overlay and a serve-preparation frame each count as. Ambiguity resolved after seeing the frame
      is how a census becomes a wish.
  (c) MEASURE LABEL AGREEMENT, and the row is not creditable without it. Re-label an evenly spaced
      subset of at least 50 of your own frames in a second pass without looking at the first pass,
      and report the agreement rate with its Wilson interval. Every downstream number inherits this
      uncertainty and the memo must say so. See the eye-label reliability history: eye labels in this
      program have disagreed with themselves at rates that changed conclusions.
  (d) Report this clip's rally share with a Wilson 95 pct interval over the ELIGIBLE DENOMINATOR of
      frames you actually labelled. Never a bare sample size. Say plainly whether it agrees with
      G34's 41.7 pct on the other clip or not -- either answer is informative and neither is expected.
  (e) NOW recompute G152b's two rates against the RALLY denominator instead of all decoded frames:
      the declaration rate over rally frames, and the geometry-backed rate over rally frames. Give
      each an interval. This is the first honest rally-normalised coverage figure in the program.
  (f) State what the result implies for the 0.90 bar in ONE paragraph, and state it as position, not
      as an argument. **If the rally-normalised coverage is still far below 0.90, say so plainly and
      do NOT propose lowering the bar.** A bar found unmeetable is reported CLOSED AT LIMIT, never
      moved (Q3, B10). That is the single most important sentence in this spec: an earlier retraction
      in this program came from exactly that temptation.
  (g) Commit the labels as a durable artefact (frame index, label, pass number) so the next row reuses
      them instead of re-labelling. Commit at least 8 rendered frames, sampled EVENLY across your
      labelled set, at least 3 of them labelled NOT rally.

DO NOT change the coverage bar, the coordinate contract, the harness, the adapter, the solver, any
threshold, or any verdict. Do not label opportunistically to hit a number.

ACCEPTANCE RULE:
  metric        = this clip's rally share with a Wilson interval; the self-agreement rate with its
                  Wilson interval; declaration and geometry-backed rates renormalised to rally frames
  before        = no per-frame rally label exists for any clip we hold; G152b's rally rate is
                  unmeasured; the 0.90 bar cannot be adjudicated
  bar           = NO pass bar. Success is a seeded evenly spaced labelled census with its agreement
                  measured. A rally-normalised coverage far below 0.90 is a FULL SUCCESS.
  n             = >= 300 evenly spaced labelled frames; >= 50 re-labelled for agreement (SAMPLED, so
                  the n >= 30 rail binds and Wilson intervals are required)
  eye check     = this row IS the eye check; commit >= 8 evenly sampled renders, >= 3 of them NOT rally
  must not move = the 0.90 coverage bar, every threshold, the coordinate contract, the adapter, the
                  solver, tracking_harness.py, and every verdict
EVIDENCE: docs/evidence/tracking/g161_rally_denominator_2026-09-03.md with the labelling rule quoted
verbatim, the seed and spacing, the agreement table, the renormalised rates with intervals, and a NOT
VERIFIED list. Labels and renders under docs/evidence/tracking/g161_rally/. Commit BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: DO NOT TOUCH -- LOCAL ONLY. Never kill anything.
COMMIT: explicit pathspec only, in a6, no push. Report the sha.
NEVER PARK: label in flushed chunks, never holding a long label list only in context -- a lane lost
300 completed labels that way. Do not poll your own jobs; never end waiting.
