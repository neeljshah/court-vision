GAP G44B | sport tennis | worktree a3 | log cx_g44b_ball_spatial_gate
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including the NEW A7 clause (a
memo naming an evidence path that no longer exists is NOT VALIDATED); self-check every line of
section B before you report. THIS ROW IS THE FIX. The limit measurement is already done.
PREMISE (step 0, reproduce it): G44's limit measurement established, and you must confirm, that
this is NOT a resolution wall. The tennis ball is 6-8 px near the net and 15-30 px in cutaways, so
it is above the detectability floor. 64 pct of rally frames show a ball. But only 52 pct of those
sightings fall inside MotionDiffDetector's ONLY spatial rule for ball candidates, `y < 2/3 *
height`, giving a ceiling of about 33 pct of rally frames under the current gate. That rule
simultaneously EXCLUDES the near half of the court and ADMITS backdrop, crowd and scoreboard.
The consequence measured in G39: 12 of 12 evenly spaced renders over the offending set contain
ZERO tennis balls (9 far-player heads, bodies and rackets; 3 crowd or scoreboard blobs) while the
real ball is plainly visible elsewhere in 4 of them. Reproduce the 64 pct, the 52 pct and the
12-of-12 from g39_ball_projection_diagnosis_2026-09-02.md and g39_renders/ before changing code.
If any of those does not reproduce, STOP and report that.
LIMIT (step 1): a single horizontal cutoff cannot separate a ball from a head, because the two
overlap in image row. Any fix that is still a bare row threshold will trade one error for the
other. Say in the memo what signal you are using INSTEAD of, or in addition to, image row -- the
candidates worth measuring are size in pixels, motion magnitude between frames, colour or
brightness against the local background, and containment inside the solved court region when a
homography exists. Do not use a hand-drawn per-clip rectangle; that is a tautology (B7).
CHANGE (step 2): replace the spatial rule for BALL candidates only. Hard constraints:
  (a) Do NOT change player detection, the court solver, the camera lock, or any harness threshold.
  (b) The new rule must be derived from the labelled sample, not chosen by eye and then justified.
      Report the decision boundary and how you set it.
  (c) It must be evaluated on frames you did NOT use to set it. Hold out a disjoint set, say how
      you split, and report both numbers. A rule fit and scored on the same frames is B8.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = ball recall on rally frames (fraction of hand-labelled real ball appearances the
                  detector emits a candidate for, within a stated pixel tolerance of the label)
                  AND ball precision (fraction of emitted candidates that are the real ball)
  before        = ceiling about 33 pct of rally frames reachable; precision measured at 0 of 12 on
                  the offending set
  bar           = held-out recall materially above the 33 pct ceiling AND precision strictly better
                  than the current 0-of-12 result, with Wilson 95 pct intervals on both. Report
                  BOTH numbers always -- a recall gain bought with a precision collapse is a
                  REJECT, and saying so plainly is a success.
  n             = >= 150 hand-labelled rally frames, seeded and evenly spaced across >= 3 clips,
                  split into disjoint fit and held-out sets; state both sizes
  eye check     = MANDATORY. Render >= 15 held-out frames with the emitted candidate marked and
                  LOOK at them. Say what you saw, including every case where the candidate is not
                  the ball. Commit them under docs/evidence/tracking/g44b_renders/.
  must not move = player detection, the solver, the camera lock, every harness threshold, and the
                  coordinate contract. Ball rows must still declare their coordinate space.
DOWNSTREAM, state it explicitly: no rally-tempo, serve-speed or contact-frame teacher may be built
until this passes. Say in the memo whether it now may be.
DURABILITY (new A7 rule): copy every artifact a verifier must recompute your numbers from --
the label file and the per-frame decision records -- under docs/evidence/ BEFORE you report.
Three lanes have now been blocked by evidence that existed only in /tmp or only on the pod.
EVIDENCE: docs/evidence/tracking/g44b_ball_spatial_gate_2026-09-0X.md with the reproduced premise,
the labelling method, the fit and held-out numbers with intervals, the renders, and a NOT VERIFIED
list.
TEST: exactly one new per-file test; run only that file. Never a full pytest -- it freezes the box.
FOOTAGE -- READ THIS, attempt 1 died here. Attempt 1 returned NOT VALIDATED because it could not
find the source clip. That was an infrastructure gap and it is now FIXED: worktree_data_links.py
did not link data/footage_corpus, and now does. Your worktree sees the local corpus (4 clips,
including tennis__tennis_09.mp4 and tennis__tennis_nyYk2nPZAwY_720p.mp4). The FULL corpus is 63
clips on the pod at /workspace/nba-ai-system/data/footage_corpus/ -- see
docs/evidence/tracking/FOOTAGE_CORPUS_INVENTORY.md for every clip by name. If the clips you need
are the two local tennis ones, work locally. If you need any other tennis clip, run the frame work
ON THE POD, read-only, where the video already is. Do NOT report "source unavailable" without
first checking the inventory and the pod.
POD: read-only, and you MAY run read-only frame measurement there because that is where the
footage is. NO scp of any module and no deploy -- the verifier lands code on the pod, not the
lane. Never restart the daemon, never kill anything.
COMMIT: explicit pathspec only (never the whole tree, never the gitignored local trees), in a3,
no push. Report the sha.
SHARED MODULE: none expected. If you find yourself editing tracking_harness.py, STOP.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
