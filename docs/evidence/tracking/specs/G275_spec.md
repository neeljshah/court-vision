GAP G275 | sport wnba | worktree a6 | log g275_map_eligible_footage_census
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only --
**`src/tracking/advanced_tracker.py` and `src/tracking/player_detection.py` are HUMAN-GATED.** Build in
`scripts/platformkit/tracking/`.

**HOLD RULE -- COUNT DISTINCT LANE WORKTREES, NOT PYTHON PIDs.** N=2 is the measured optimum (G200/G216).
**One lane routinely shows TWO python PIDs sharing one `cwd`** -- G274 verified that `/workspace/wt/a17`
held PIDs 3084857 and 3085457, which is ONE lane, and a sibling row had already deadlocked on that
miscount. **Collect the `cwd` of every python process under `/workspace/wt/a*`, reduce to the SET of
distinct worktree directories, and compare THAT count to 2.** Exclude your own process, your checker and
its parent. **Report the distinct-worktree SET you observed.** Do NOT interrupt a running row.

**READ THE LANDED G274, G241b AND G242 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- G274 JUST SHOWED THE NEXT SHOT HAS NO COURT IN IT AT ALL.**
The tracking-defect chain (G267, G269, G270, G271, G272b, G273) was measured on source frames
**19599-23399** of `wnba__wnba_01.mp4`. **That clip is 174,430 frames, 5,814.33 s, 1920x1080 at 30 fps
(ffprobe, 2026-09-04), so the chain rests on 3,801 frames = 2.2 pct of ONE clip.**

G274 selected the adjacent distinct shot, frames **23476-24127**, and found **a tight player close-up with
no painted court**: direct-to-seed matching still returned **0.285-1.434 px RMS and up to 350 inliers**
while the projected court ran across a player's body. **It correctly refused to build on that and
stopped.**

**So the binding question is no longer "does the profile replicate in another shot". It is "how much of
broadcast footage could EVER carry a court-space measurement at all?"** Nobody has measured that, and it
sets the ceiling on the entire court-space programme.

THE QUESTION: **what fraction of this clip's runtime shows enough painted court geometry to be a
candidate for calibration?**

METHOD:
  1. **CENSUS THE WHOLE CLIP, NOT THE STUDIED SPAN.** Sample frames **uniformly across all 174,430
     frames** -- **at least 180 frames**, evenly spaced. **State the exact stride and the sampled
     indices.** **Seek with `ffmpeg -ss`; NEVER decode the whole file.** **The denominator is SAMPLED
     FRAMES, never seconds of game.**
  2. **CLASSIFY BLIND IN RANDOMISED ORDER, COMMITTING THE ORDER AND VERDICTS IN THEIR OWN COMMIT BEFORE
     UN-BLINDING** (as G255, G257, G260, G272b, G273 did). **Categories are PURELY VISUAL -- every one
     must be something the eye can OBSERVE, never inferred.** G272b's category (a) failed exactly this
     way by fusing an observation with an inference, and it needed a public correction.
     **(a) TWO OR MORE distinct painted court lines visible AND at least one intersection of painted lines
         visible;
     (b) painted court SURFACE visible, but fewer than two distinct lines, or no visible intersection;
     (c) NO painted court surface visible at all -- crowd, bench, faces, graphic, blank;
     (d) CANNOT JUDGE.**
     **Do NOT ask whether a frame is a replay, live play, or any particular camera** -- none of those is
     observable from a single frame. **Keep (d) separate and never merge it.**
  3. **MEASURE LABEL AGREEMENT.** **Re-judge at least 40 of the sampled frames blind, in a FRESH
     randomised order, after the first pass is committed**, and **report the agreement rate and the
     per-category confusion.** Eye labels in this programme have never cleared 80 pct blind agreement on
     four measured criteria. **A census without an agreement figure is not usable.**
  4. **REPORT (a) AS AN UPPER BOUND, AND SAY SO IN THOSE WORDS.** Category (a) is **NECESSARY, NOT
     SUFFICIENT.** G242, G244, G247 and G248 each failed to find any signal separating a valid court from
     an invalid one; G257 bounded the eye at 20 px; and **G274 produced sub-pixel RMS on a frame with no
     court in it.** **So the (a) fraction is the MOST footage that could ever be calibrated, not footage
     that will calibrate.** Any wording stronger than that is an overclaim.
  5. **LOCATE THE STUDIED SPAN IN THE DISTRIBUTION.** State which sampled frames fall inside 19599-23399
     and **whether that span is typical or unusual for this clip.** **If the studied span is unusually
     court-bearing, say so plainly** -- it would mean the whole chain was measured on the friendliest
     footage in the clip, which is a finding in its own right.
  6. **Report the RUN STRUCTURE descriptively**: how (a)-frames are distributed along the clip, in long
     stretches or scattered singletons. **Do NOT propose a shot detector, filter, gate or threshold**, and
     do not fit anything (G269 showed how easily a filter fakes an improvement).
  7. **Do NOT run the detector, the tracker, or any calibration. Do NOT touch `src/`.** This row decodes
     frames and classifies them; nothing else.

**DISK GUARD:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`** -- the scope the 50 GB quota
is enforced on, **40,074 MB at 2026-09-04 12:35, roughly 9.7 GB free**, and **a peer session writes under
`/workspace/wt`, which a subtree measurement cannot see.** **Re-measure yourself; do not trust that
figure.** **`dd conv=fsync` probe before writing, STOP and report if it fails.** **180+ JPEGs are the
bulk -- keep them modest and report committed bytes.** **Do NOT delete any corpus source, and do NOT
delete the two abandoned bridge partials (`baseball__npb_05.mp4.part` 2.4 GB,
`football__football_m8UWuQoflJo.mp4.part` 4.7 GB): they are resumable acquisitions, and the football one
is the only football footage anywhere in the programme.** Report bytes freed.

**PATHS ARE ON THE POD.** The clip is `wnba__wnba_01.mp4` in the corpus directory under the pod repo's
gitignored footage store, 2,796 MB, sha256 beginning `f361ad7a32ccc6d98ae8e98e`. **Verify the file and its
frame count before decoding** (G256: a spec path that does not say pod-or-local sent a lane searching
locally; G243: a spec named a clip that did not exist).

**HONEST LIMITATIONS to state, not discover:** **ONE clip, ONE broadcast, ONE arena, ONE labeller.** A
uniform frame sample measures **frames, not shots** -- a long static shot and a one-second cut contribute
in proportion to their length, which is exactly what "fraction of runtime" means, **but it is NOT a count
of shots and must never be reported as one.** **Category (a) is necessary, not sufficient** (step 4).
Painted-line visibility is a judgement at the margin, so **expect (d) to be non-trivial and do not
suppress it.** Nothing here says anything about other clips, other sports, or amateur footage.

ACCEPTANCE RULE:
  metric        = the stride, sample size and sampled indices; the committed randomised order and blind
                  verdicts; counts and fractions for (a)-(d) with (d) separate; **the re-judge agreement
                  rate and per-category confusion**; the upper-bound statement in step 4's words; where
                  19599-23399 sits in the distribution; and the descriptive run structure
  before        = the whole court-space chain rests on 3,801 frames, 2.2 pct of one 174,430-frame clip,
                  and the single adjacent shot anyone has checked (G274) had no painted court at all
  bar           = **NO pass bar, and no number here is a failure.** **A LOW (a) fraction is a major
                  finding** -- it would mean court-space tracking can only ever address a small slice of
                  broadcast footage, and it would reframe the programme. **A HIGH (a) fraction is equally
                  informative** and would mean the studied span was not special. **A poor re-judge
                  agreement rate is ALSO a full success** and would mean the census must be read as
                  indicative only. Do not tune, do not filter, and do not assert what any frame would
                  calibrate to.
  n             = 1 clip, 174,430 frames, the sample size you state, 1 labeller -- **name the
                  sampled-frame denominator in the verdict line**
  eye check     = the blind classification IS the measurement; it is a COARSE categorical judgement, not
                  the sub-pixel geometric one G257 bounded at 20 px. **Say that distinction in the memo.**
  must not move = every threshold, bar and verdict, G233d's published map and labels, G267's retained
                  records and span, the court model, the coordinate contract, `src/` and `domains/` (READ
                  and IMPORT ONLY), the pod daemon and keeper, the corpus, the bridge partials
EVIDENCE: docs/evidence/tracking/g275_map_eligible_footage_census_2026-09-04.md with the sampling
description, the committed blind order and verdicts, the four counts and fractions, the re-judge agreement
and confusion, the upper-bound statement, the position of the studied span, the run structure, every
disk-guard probe with the `du -sm /workspace` figure, bytes freed and committed, and a NOT VERIFIED list.
**ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
