GAP G260 | sport wnba | worktree a6 | log g260_paired_displacement_sensitivity
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G259 may be running on a5; N=2 is optimal). **Check first, do NOT
interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G258 MEMO AND THE G258-SENSITIVITY-CORRECTION LEDGER ROW FIRST.**

**WHY THIS ROW EXISTS -- G258's DESIGN HAD A ZERO NOISE FLOOR, AND THAT WAS MY SPEC'S FAULT.**
G258 pre-registered a displacement ladder properly, sealed it before scoring, and reported every rung. It
concluded that edge-response contrast detects a **10 px** displacement. **The correction row withdraws
that**, because its control was **five byte-identical decodes of ONE frame** -- zero variance -- so any
numerical change at all counted as detection. Against real variation:

| | value |
|---|---|
| shift from a 10 px displacement | **1.158 units** |
| spread of the same signal within G248's VALID class across real frames | **44.3 units** |
| ratio | **38x too small** |

**And the ladder is not monotone:** +0.138 at 5 px, +1.158 at 10, +2.075 at 20, +2.875 at 40, and
**+0.847 at 100 px.**

**My spec said to estimate the control spread "using repeated frames"; the lane reasonably repeated
DECODES of the same frame. The fix is a PAIRED DESIGN, which is strictly better than either.**

THE QUESTION: **measuring the SAME frame with and without a known displacement, so that scene content
cancels, is a projection signal sensitive enough to detect a court error -- and at what magnitude?**

METHOD:
  1. **PAIRED, WITHIN-FRAME DESIGN. This is the whole point of the row.** For **many different frames** --
     at least 30, and say how you sampled them across the clip -- compute each signal **twice on the same
     frame**: once with the unperturbed map and once with the map displaced by each ladder magnitude.
     **Report the PAIRED DIFFERENCE per frame.** Pairing cancels scene content, which G258 showed is the
     dominant nuisance term at 44.3 units.
  2. **Reuse the landed routes unchanged** -- G247's persisted maps, G248's edge-response/LSD/contrast/
     coverage signals, G252's offset machinery with its search radius and censoring statement. **Reuse
     G258's ladder magnitudes and G257's displacement definition** so all four rows stay comparable.
  3. **THE NOISE FLOOR IS NOW THE SPREAD OF THE PAIRED DIFFERENCE ACROSS FRAMES, NOT ZERO.** Report, per
     signal and per rung, the **median paired difference and its spread across frames**, and **how many of
     the frames show a paired difference in the same direction.** **Consistency of sign across frames is
     the real evidence**; a large median with mixed signs is not a detector.
  4. **DECLARE THE DETECTION CRITERION BEFORE SCORING and commit it**, as G258 correctly did -- seal a
     preregistration file in its own commit and cite its SHA-256. **Base it on the paired spread, not on
     zero.**
  5. **CHECK AND REPORT MONOTONICITY ACROSS THE WHOLE LADDER, INCLUDING THE TOP RUNG.** G258's signal
     reversed by 100 px. **A non-monotone signal cannot be a one-sided gate at any threshold -- say so
     explicitly if it recurs.**
  6. **REPORT THE SMALLEST RELIABLY DETECTED DISPLACEMENT PER SIGNAL**, or state plainly that none is
     detectable. **Place it beside G257's 20 px eye-gate resolution, and state clearly that G257 measured
     AMATEUR footage while this measures WNBA broadcast**, so the comparison is across footage classes and
     is indicative only.
  7. **Do NOT fit a threshold and report its accuracy on the same data. Do NOT propose a production gate.
     Do NOT claim this bears on automatic calibration**, which remains 0/17 -- **detecting a bad map is not
     finding a good one.**
  8. **A clean negative is the expected and most likely outcome given the 38x gap, and it is a FULL
     SUCCESS.** It would close the hand-built validity question against known ground truth, not just
     against noisy eye labels.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` ON THE POD (baseline ~33,163 MB of 50,000), STOP and report if it
fails.** **30+ frames times 7 rungs is a lot of decoding -- stream it, decode each frame once and reuse it
across rungs, never write a full decode to disk.** **Do NOT delete any corpus source or the two abandoned
partials in `footage_bridge`.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one seed map, one arena. **A synthetic uniform
displacement is NOT a real calibration error**, which distorts non-uniformly across the image; a signal
that detects synthetic displacement may still fail on real error. **The unperturbed map is only
"unperturbed", not correct** -- G257 shows it is certified only to ~20 px, and G252 measured its offset at
5 px median / 19 px p90. **Frames differ in how much court is visible**, so paired differences will be
undefined or censored on close-ups and graphics -- **report how many frames were excluded and why, and
never silently drop them.** Automatic calibration remains 0/17.

ACCEPTANCE RULE:
  metric        = the sealed preregistered detection criterion and its commit sha; per signal and per rung,
                  the median paired difference, its across-frame spread, and the count of frames agreeing
                  in sign; monotonicity across the full ladder including the top rung; the smallest
                  reliably detected displacement per signal or a plain statement that none is; and the
                  comparison to G257's 20 px with the cross-footage caveat
  before       = G258's 10 px sensitivity rests on a zero-variance control and is withdrawn; the same
                 signal's real between-frame spread is 38x the effect and the ladder is non-monotone
  bar          = NO pass bar. **"No signal reliably detects any displacement under a paired design" is a
                 FULL SUCCESS and the expected outcome**, and would close the hand-built validity question
                 against KNOWN ground truth rather than noisy labels. **"Signal X detects N px with
                 consistent sign across frames" is the other full success** and would be the programme's
                 first real validity signal. Do not fit a threshold to this data.
  n            = the frame count and ladder rungs you state, 1 clip, 1 seed map -- name every denominator
                 in the verdict line
  eye check    = none required; this row is paired signal differences against known displacement
  must not move = every threshold, bar and verdict, G233d's seed and labels, G247's maps, G248's and
                  G252's methods and settings, G257's and G258's committed artifacts, the court model, the
                  coordinate contract, `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and
                  keeper, the corpus, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g260_paired_displacement_sensitivity_2026-09-04.md with the sealed
preregistration and its sha, the frame sampling, the per-signal per-rung paired-difference tables with
spreads and sign-agreement counts, the monotonicity statement, the excluded-frame count with reasons, the
smallest reliably detected displacement or its absence, the G257 comparison with the cross-footage caveat,
every disk-guard probe, bytes freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME
COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
