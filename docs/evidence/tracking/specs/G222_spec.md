GAP G222 | sport wnba | worktree a3 | log g222_direct_to_seed_propagation
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ and IMPORT only. Build in
`scripts/platformkit/tracking/`.

**HELD -- DO NOT RUN ON THE POD UNTIL G216 HAS REPORTED.** G216 is measuring read throughput there and
frame extraction would corrupt it. **Check the pod for concurrent route jobs before you start and say
in the memo that you checked and when you began.** Harness and test writing may proceed immediately.

**S1 MACHINE: RUN ON THE POD** (you need real consecutive video frames). **DISK GUARD, BINDING:** `df`
is NON-AUTHORITATIVE here -- it reports the whole cluster filesystem against a 50 GB volume cap, and
that misreading caused a `Disk quota exceeded` incident. **Do a real `dd` write probe of a few MB
before writing anything, record `du -sm /workspace/nba-ai-system/data` (baseline 30,771 MB of 50,000),
and if the probe fails STOP and report -- do not delete anything to make room.** Extract only the
frames you need, keep them small, **delete every temporary artifact and report bytes freed.** Never
kill, restart or deploy over the daemon or keeper. Delete no corpus source.

**WHY THIS ROW EXISTS -- IT TESTS G215's OWN STATED LIMITATION, AND THE ANSWER DECIDES WHETHER THE ONLY
CALIBRATION PATH WE KNOW WORKS IS VIABLE AT ALL.**

**What is established, and you should not re-derive it:**
  - **G196**: a homography from **four HAND-LABELLED corners** projects correctly, with the three-point
    arc landing OUT-OF-SAMPLE on the painted arc. **Geometry from a good seed is recoverable. This is
    the one calibration result in the programme that actually works.**
  - **G215**: seeded from those corners at frame 1600 and propagated **frame-to-frame by chained image
    motion** over a stride-1, 300-frame run: **median paint-corner drift 10.88 px at 50 frames, 38.47 px
    at 100, 187.77 px at 300**, with the eye check plausible through 50 and grossly wrong by 200-300.
    **The cause was an ordinary smooth camera PAN -- no shot cut, replay or abrupt zoom occurred.**
  - **G215's own closing limitation, verbatim, is the reason for this row:** *"naive chaining is the
    wrong instrument for long runs -- re-anchoring or global optimisation across frames is what
    published systems use, and neither was tested here."*
  - **G210b / G214**: automatic per-frame corner search scores **0 of 17**, against an oracle bound of
    1/17. **So we currently have ZERO automatic anchors.**

**THE ARITHMETIC THAT MAKES THIS THE DECIDING ROW.** With zero automatic anchors, the only working path
is a HAND-LABELLED seed. **At G215's chained horizon of ~50 frames, a one-hour 30 fps clip needs roughly
2,000 hand labels. That is not a viable path and would close hand-labelling as an option.** **If
matching each frame DIRECTLY against the seed removes the compounding and holds for hundreds or
thousands of frames, the requirement collapses toward one label per camera shot, which is a completely
different proposition.** **This row decides between those two worlds.**

**WHY DIRECT-TO-SEED SHOULD BEHAVE DIFFERENTLY, stated so you can try to refute it:** chained
composition multiplies N inter-frame estimates, so each one's error compounds and drift grows without
bound even when every individual estimate is good. Matching frame k directly to the seed uses exactly
ONE estimate whose error does not accumulate; its limit is instead **appearance change** -- as the
camera pans and zooms away from the seed view, overlap shrinks and matching degrades, then fails.
**These two failure modes have DIFFERENT SHAPES: compounding drift grows smoothly, overlap loss falls
off a cliff. Report which shape you observe; that is the real finding.**

METHOD:
  1. **Reuse G215's seed construction and its drift metric UNCHANGED** -- same clip
     (`wnba__wnba_01.mp4`), same seed frame (1600), same four hand-labelled corners via
     `court_points_for_sport`, same paint-corner drift measure. **This row must differ from G215 in
     exactly ONE respect: how the homography for frame k is obtained.** If you change anything else,
     the comparison is void and the row is worthless.
  2. **Run BOTH arms over the SAME frames**: (A) G215's chained composition, reproduced as a control;
     (B) direct-to-seed matching. **Reproduce G215's numbers in arm A first** -- 10.88 px at 50, 38.47
     at 100, 187.77 at 300. **If arm A does not reproduce, STOP and report that**, because the route is
     non-deterministic elsewhere and a failure to reproduce is itself a significant finding.
  3. **Extend the run well past 300 frames** -- far enough to find where arm B fails, or to show it has
     not failed by the end. **State the stride and run length up front.** If arm B is still holding at
     the end of your run, **say that it did not fail within the frames tested rather than extrapolating.**
  4. **Report drift versus distance from the seed for both arms in one table**, at the same intervals,
     and **name the ELIGIBLE DENOMINATOR as the frames actually propagated through in each arm.**
     Report matched-feature counts (or your matcher's equivalent) alongside the drift, since **a
     collapsing match count is the signature of overlap loss** and distinguishes the two failure shapes.
  5. **EYE CHECK IS THE DELIVERABLE, exactly as in G215**, because there is no per-frame ground truth
     after the seed: render the projected court for **both arms at the same several distances**, and
     state plainly at what distance each comes off the painted court. Commit the renders.
  6. **Then state the consequence in labels-per-hour**, carefully: given the horizon you measured, how
     many hand-labelled seeds would a one-hour clip need? **Give the arithmetic and its assumptions.**
     **"Direct-to-seed dies at the same ~50 frames, so hand-labelling needs thousands of seeds per hour
     and is not viable" is a FULL SUCCESS** -- it would close a path that currently looks open and force
     the search back to automatic anchors or a trained model. Do not prefer either outcome.

**HONEST LIMITATIONS you must state rather than discover:** drift measured against a composition is
**SELF-CONSISTENCY, not accuracy** -- the renders carry the accuracy claim and they are single-labeller
eye judgements, exactly as G215's were. The seed uses hand labels, so this measures PROPAGATION only
and says nothing about obtaining a seed automatically; that half remains at 0/17. One clip and one seed
frame measure a MECHANISM and a decay shape, **not a rate across the corpus** -- a different clip with a
tighter zoom or faster pan could behave differently. This row does not run the tracking route, so its
non-determinism does not apply; say so.

**DO NOT** change the court model, the coordinate contract, G215's drift metric, any threshold, or any
bar. **DO NOT** propose or apply a `src/` change; this row measures a mechanism.

ACCEPTANCE RULE:
  metric        = paint-corner drift versus distance from the seed for BOTH arms over the same frames,
                  with matched-feature counts; the distance at which each arm's eye check fails; the
                  observed failure SHAPE (smooth compounding versus overlap cliff); and the resulting
                  hand-labels-per-hour arithmetic
  before        = chained propagation holds about 50 frames (G215) and non-chained propagation has never
                  been measured; with automatic anchors at 0/17, whether hand-labelled seeding is viable
                  turns entirely on this horizon
  bar           = NO pass bar. **A longer horizon and a shorter one are equally valuable results.**
                  Arm A must reproduce G215 or the row stops. Do not tune either arm to widen the gap.
  n            = 2 arms over one seeded run on one clip (EXISTENCE and decay shape, not a rate)
  eye check    = the paired renders described above -- this is the deliverable
  must not move = every threshold, bar and verdict, the court model, G215's seed and drift metric, the
                  coordinate contract, `src/` (READ and IMPORT only), the pod daemon and keeper, the
                  corpus (delete NOTHING)
EVIDENCE: docs/evidence/tracking/g222_direct_to_seed_propagation_2026-09-04.md with the arm-A
reproduction of G215, the two-arm drift table, the matched-feature counts, the paired renders, the
failure-shape statement, the labels-per-hour arithmetic with its assumptions, every disk-guard probe
result, bytes freed on cleanup, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for the propagation harness, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
