GAP G243c | sport basketball (amateur) | worktree a6 | log g243c_amateur_seed_verified_points
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO existing label file and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G247 may be running on a5; N=2 is optimal per G200/G216). **Check
first, do NOT interrupt a running row, and say in your memo that you checked and when you began.** The
`track_daemon`, `keep_track_daemon.sh`, `adapter_run` jobs, `inplay_capture_runner` and `foundry_runner`
are PERMANENT residents and the load floor.

**READ `G243b_spec.md`, `G246_spec.md` AND BOTH LANDED MEMOS FIRST.**

**WHY THIS ROW EXISTS -- G243b's FAILURE WAS BAD LABELS, NOT AMATEUR FOOTAGE. THE QUESTION IS STILL
OPEN.**
G243b failed both amateur seed gates. **G246 then diagnosed it precisely: ALL EIGHT labelled pixels are
NOT the features their role names claim.** None is a paint corner; none is a centre-circle extremum. Two
were occluded by a coach and a player. Its finding was blunt: **"The clustered input has no four visible
paint corners; the spread input has no two visible centre-circle extrema."** Exhaustive enumeration of
every four-point correspondence and axis convention found no variant that works, so **it is not a role
mapping or an axis problem -- the inputs were simply the wrong points.**

**THE METHODOLOGICAL LESSON THIS ROW MUST APPLY, IN G246's OWN WORDS: "Repeating an incorrect point within
11.39 px can be repeatable without identifying the intended feature."** G243b's three labellings agreed to
about 10 px -- inside G140's p90 -- **while all three were consistently wrong. LABEL REPEATABILITY IS NOT
LABEL CORRECTNESS**, and this programme has been leaning on repeatability as though it were.

THE QUESTION: **with point identity verified BEFORE fitting, does one hand-labelled seed produce a court on
amateur high-school footage?**

**THE SOURCE** (verify it yourself, as G243b and G246 both did):
`/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4`, 24,523,745 bytes,
SHA-256 `773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea`, 1280x720, 3,601 frames,
30 fps, 120.1 s.

METHOD -- THE ORDER IS BINDING:
  1. **SELECT A FRAME BY WHETHER ITS FEATURES ARE ACTUALLY VISIBLE AND UNOCCLUDED.** Survey the clip and
     **choose a frame where four court features are genuinely identifiable and NOT occluded by players,
     coaches or officials.** G243b's frame 2760 had two occluded points. **Commit a zoomed crop of each
     candidate feature and state what is at it.** Decode frame-exactly with a `select=eq(n,N)` filter
     (`ffmpeg -ss` before `-i` is NOT frame-exact) and state the index and method.
  2. **VERIFY POINT IDENTITY BEFORE ANY FIT, USING G246's PROTOCOL.** For every point you intend to use,
     **commit a zoomed crop and state in words what court feature is at that pixel.** **If a point is not
     the feature you need, choose a different point or a different frame -- but do this BEFORE fitting,
     and say so.** Identity verification before the fit is required; **adjusting a label AFTER seeing a
     gate result is forbidden and would void the row.**
  3. **Label three times independently and report the spread**, but **state explicitly that repeatability
     is NOT correctness** and that the identity crops, not the spread, are what establish the points are
     right. This is the G246 lesson and it must appear in the memo.
  4. **RUN THE GATE UNDER TWO COURT MODELS, because the model is a free parameter here.** G246 established
     that **an uncalibrated oblique view cannot measure 12 versus 16 ft or 84 versus 94 ft**, so the
     high-school model is assumed, not proven.
     **(a)** the row-local high-school model G243b used: 84x50 ft, 12-ft lane, 19-ft paint depth.
     **(b)** the existing `ncaa_basketball` key: 94x50 ft, 12-ft lane, 19-ft paint depth.
     **A wrong court LENGTH would also fail the gate, and running both separates that from a labelling
     problem.** Report both verdicts. **Do NOT add a new `court_points_for_sport` key.**
  5. **HARD GATE: render and report PASS or FAIL in ONE LINE PER MODEL, BEFORE ANYTHING ELSE.** If both
     FAIL, STOP -- no propagation, no in-court fraction, no labels-per-hour. **The labelled points are
     FITTED INPUTS and are NOT evidence. Judge on INDEPENDENT geometry -- the three-point arc, the
     sidelines, and the CENTRE CIRCLE, which this footage shows.** **Ignore RMS entirely: with four points
     it is identically zero and carries no information** (G243b reported 0.000000000 px and correctly
     called it degenerate).
  6. On a PASS, propagate **DIRECT-to-seed with G222's landed harness unchanged**, never chained. **The
     bound is 3,601 frames**, the whole clip.
  7. **CRITICAL, FROM G242 AND G244:** G222's acceptance rule accepted 89 of 89 whole-game frames
     including replays, graphics and the wrong hoop end, and **G244 then showed NO match diagnostic
     separates a correct court from a wrong one** -- matches, inliers, ratio and RMS all interpenetrate.
     **So ONLY THE RENDERS establish a hold. Never report one from acceptance.** Say this in the memo.
  8. Report the in-court fraction to **three decimals** against the court extent you name, and say it is
     one draw from a non-deterministic detector.
  9. **Compare to G233d** -- gate, horizon, inliers -- with the resolution caveat (720p has fewer pixels
     per foot than G233d's 1080p, so a same-size pixel error is a larger real-world error).
 10. **IF NO FRAME IN THE CLIP HAS FOUR IDENTIFIABLE UNOCCLUDED COURT FEATURES, SAY SO AND STOP.** That is
     a complete and important result about this footage, and it must be reported as a finding rather than
     worked around.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` (baseline ~33,038 MB of 50,000), STOP and report if it fails.**
**Do NOT delete the two abandoned partials in `footage_bridge`.** Decode to memory, keep renders and crops
small, delete every temporary artifact and report bytes freed. Delete no corpus source.

**HONEST LIMITATIONS to state, not discover:** one clip, one seed, one camera, one labeller, 120.1 seconds.
**This CONSUMES A HAND LABEL and is not automatic calibration**, which remains 0/17. **Plausibility is
necessary, never sufficient.** Eye-label reliability in this programme has never cleared 80 pct blind
agreement on any of four measured criteria, and **G246 showed repeatable labels can be uniformly wrong**.
The court model is assumed, not measured. The in-court fraction includes officials, bench and spectators.

ACCEPTANCE RULE:
  metric        = the frame-selection justification with occlusion check; the per-point identity crops and
                  statements, BEFORE the fit; the three-labelling spread with the repeatability-is-not-
                  correctness statement; the two gate verdicts stated FIRST, one line each; then on any
                  PASS, inliers versus distance to failure or the 3,601-frame bound, the in-court fraction
                  to three decimals against a NAMED extent, the renders, and the G233d comparison
  before       = G243b failed both gates; G246 proved the cause was that all eight labelled pixels were
                 not the claimed features, and that no role mapping or axis convention repairs it
  bar          = NO pass bar. **A PASS would be the first calibration of non-broadcast footage this
                 programme has produced.** **A FAIL with verified point identity is a FULL SUCCESS and a
                 far stronger negative than G243b's**, because it would no longer be attributable to
                 labelling. **"No frame has four identifiable unoccluded features" is a third full
                 success.** Do not relabel after seeing a gate.
  n            = 1 clip, 1 seed, 2 court models, 3 independent labellings -- state this in the verdict line
  eye check    = the identity crops gate the inputs; the seed renders gate the result
  must not move = every threshold, bar and verdict, `court_points_for_sport`, the coordinate contract, the
                  harness, G222's matcher settings, existing label files, `src/` and `domains/` (READ and
                  IMPORT ONLY), the pod daemon and keeper, the corpus, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g243c_amateur_seed_verified_points_2026-09-04.md with the source check,
the frame-selection and occlusion evidence, every identity crop and statement, the three labellings, both
gate verdicts stated FIRST, any propagation and in-court results, all renders, the G233d comparison, every
disk-guard probe, bytes freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT
AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
