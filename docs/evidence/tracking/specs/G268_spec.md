GAP G268 | sport wnba | worktree a5 | log g268_dense_multiframe_accumulation
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file, NO court model and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G267 may be running on a6; N=2 is optimal). **Check first, do NOT
interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G266 MEMO AND THE G266-VERIFIER-DENOMINATOR LEDGER ROW FIRST.**

**WHY THIS ROW EXISTS -- I WROTE THAT G266 DOES NOT CLOSE MULTI-FRAME CALIBRATION, SO IT HAS TO BE TESTED
PROPERLY.**
G266 accumulated **4 transported line constraints and 8 endpoints** across a WNBA shot and failed its
binding control against G233d's published map: median 2.476 px but **max 234.542 px**, versus G253's
one-frame control at max 4.344 px. It applied its stop rule correctly and opened no NCAA frame.

**My verifier note recorded two things about that result.** Its **median and p90 rest on only 7 shared
probe points and are fragile**, while **the maximum is not denominator-fragile and is what carries the
FAIL**. And, explicitly: **"Do not cite G266 as closing multi-frame calibration -- cite it as one sparse
accumulation failing its control."** **A denser accumulation, tighter frame spacing, and a joint
refinement over all frames at once were not tried.** This row tries them, so that the hedge is either
retired or converted into a real closure.

THE QUESTION: **does DENSE multi-frame accumulation with joint refinement reproduce a known map, where a
sparse transported one did not?**

METHOD:
  1. **BINDING CONTROL, SAME TARGET AS G266 AND G253:** reproduce **G233d's published map** on
     `wnba__wnba_01.mp4` around seed frame **19599**, staying **inside one camera shot** (G241b's cut is at
     about distance 3,876 -- say which span you used and how you verified no cut lies inside it; G241b
     showed a cut collapses matching from 310 to 182 matches in one frame).
  2. **DENSE, NOT SPARSE. This is the whole difference.** Use **at least 30 frames** across the shot, not
     5, and say how you spaced them. **Report how many primitives each frame contributes and the total
     constraint count** -- G266 had 4 lines and 8 endpoints; state yours beside that.
  3. **JOINTLY REFINE OVER ALL FRAMES AT ONCE** rather than transporting a few constraints into one
     reference frame. Report the objective, the optimiser, and the convergence criterion. **Relate frames
     with G222's landed matcher UNCHANGED**, and **report the inter-frame match quality actually achieved**
     (matches, inliers, RMS) -- transported evidence is only as good as its transport.
  4. **PROBE ON A DENSE POINT SET SO THE STATISTICS MEAN SOMETHING.** G266's control statistics rested on
     **7** shared in-frame points; G253's on **231 of 634**. **Use a comparably dense probe set, report the
     shared-in-frame count as the named denominator, and report median, p90 AND max.** **The maximum is
     the number that carried G266's failure, so report it prominently either way.**
  5. **THE CONTROL IS THE GATE FOR THIS ROW.** If the dense fit does not reproduce G233d's map to
     something comparable with G253's one-frame control (median 2.849 / p90 3.992 / max 4.344 over 231 of
     634), **STOP AND REPORT. Do not proceed to any other clip.** **That would convert my hedge into a
     genuine closure of multi-frame accumulation on this evidence, which is a FULL SUCCESS.**
  6. **DO NOT INTRODUCE A NUMERIC PASS BAR.** G266 correctly said it introduced none. **Report the
     comparison and state your judgement in words**, exactly as G266 did.
  7. **The fit residual is NOT evidence** (G242/G244/G247/G248), and **G254 showed an optimiser can improve
     its own objective while moving the projection off the markings** -- **so if the control passes, render
     the result and eye-check it on INDEPENDENT geometry before claiming anything**, and remember G257:
     the eye resolves only about 20 px.
  8. **Do NOT tune, relabel, add a court key, or propose a production change.**

**DISK GUARD, CORRECTED SCOPE:** `df` is NON-AUTHORITATIVE. **Guard on `du -sm /workspace`**, the scope the
50 GB quota is enforced on, last measured **36,419 MB** with about 13.6 GB free. **`dd conv=fsync` probe
before writing, STOP and report if it fails.** **30+ frames is a lot of decoding -- stream it, decode each
frame once and reuse it, never write a full decode to disk.** **Do NOT delete any corpus source or the two
abandoned partials in the bridge directory.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one shot, one seed, one arena, one labeller.
**A dense accumulation still inherits inter-frame transport error, just spread over more observations** --
more constraints is not automatically less error, and **if it fails the same way as G266 that is the
finding.** **This CONSUMES manual geometry and is NOT automatic calibration**, which remains 0/17. The
target map itself is certified only to about 20 px (G257) and measured at 5 px median / 19 px p90 (G252),
so **"reproducing G233d" means agreeing with a map of that quality, not with truth.**

ACCEPTANCE RULE:
  metric        = the shot span with its no-cut verification; the frame count, per-frame primitive counts
                  and total constraints beside G266's 4 lines / 8 endpoints; the inter-frame match quality;
                  the control discrepancy against G233d as median, p90 AND max over a NAMED dense
                  shared-in-frame denominator, beside G253's 231-of-634 figures; and a worded judgement
                  with no new numeric bar
  before       = G266's sparse accumulation failed its control on max 234.542 px over 7 probe points, and
                 my verifier note explicitly declined to treat that as closing multi-frame calibration
  bar          = NO pass bar. **"Dense accumulation fails the same way" is a FULL SUCCESS** and would
                 convert an open hedge into a real closure. **"It reproduces the map" would reopen a route
                 that every single-frame screen tonight has blocked**, and would be the most consequential
                 positive available. Do not introduce a numeric bar and do not tune.
  n            = 1 clip, 1 shot, the frame and constraint counts you state, the probe denominator you name
                 -- every one in the verdict line
  eye check    = only if the control passes; then on INDEPENDENT geometry, remembering the 20 px eye limit
  must not move = every threshold, bar and verdict, G222's matcher settings, G233d's published map and
                  labels, the court model, the coordinate contract, G252's method, `src/` and `domains/`
                  (READ and IMPORT ONLY), the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g268_dense_multiframe_accumulation_2026-09-04.md with the span and no-cut
verification, the frame and constraint inventory, inter-frame match quality, the control comparison with
its named dense denominator, any render, every disk-guard probe with the `du -sm /workspace` figure, bytes
freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit
BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
