GAP G265 | sport ncaa_basketball | worktree a5 | log g265_ncaa_lines_only_second_arena
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file, NO court-model key and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G260 may be running on a6; N=2 is optimal). **Check first, do NOT
interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G253, G257 AND G264 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- G264 CLOSED ON A MISSING CONIC, AND NAMED THE WAY ROUND IT IN THE SAME MEMO.**
G264 screened 300 chronological frames of the NCAA broadcast and found **0/300 with an identifiable
centre-circle conic: the permanent Final Four centre logo obscures or replaces the painted circumference,
measured at 0.00 identifiable arc.** It correctly refused to relabel logo curves as a conic, and correctly
called that **"a configuration failure, not a method failure."**

**But its own survey says what IS there: "Wide broadcast views commonly show the far sideline, centre line,
and a far-end key."** Those are **lines**.

**AND LINES-ONLY IS ALREADY A VALIDATED METHOD IN THIS PROGRAMME.** G253's binding positive control was
**lines-only on the WNBA seed** and it **PASSED**, reproducing G233d's published map to **2.849 px median /
4.344 px max over 231 of 634 shared in-frame points** -- and G255 independently re-judged that same control
**PASS**. **Four line correspondences give 8 constraints for a homography's 8 degrees of freedom. No conic
is required.**

**THE SOURCE, VERIFIED ON THE POD:**
`/workspace/nba-ai-system/data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4`,
**3,580,059,573 bytes**, SHA-256 `9b35bd59d8b5b0e04737389b6661d7f8d37fac07a348056b081a6815ff5eea40`,
1920x1080, 205,444 frames, 30000/1001 fps. **`/workspace` EXISTS ONLY ON THE POD.** Confirm bytes and
SHA-256 first and STOP if either differs.

**COURT MODEL:** use the existing `court_points_for_sport("ncaa_basketball")` contract -- **94 x 50 ft,
12-ft lane, 19-ft paint depth.** **Do NOT add a key and do NOT use the WNBA 16-ft lane.**

**DISK GUARD, CORRECTED SCOPE -- THIS SUPERSEDES EVERY EARLIER SPEC OF MINE.** `df` is NON-AUTHORITATIVE.
**Guard on `du -sm /workspace`, which is the scope the 50 GB quota is actually enforced on** -- it was
**36,419 MB** when last measured, leaving about 13.6 GB. **Earlier specs guarded on the corpus subtree and
could not see a peer session's `/workspace/wt` compute scratch at all**; that is landed as
DISK-GUARD-SCOPE-CORRECTION. **`dd conv=fsync` probe before writing, STOP and report if it fails.** Stream
the decode; never write a full decode to disk. **Do NOT delete any corpus source or the two abandoned
partials in the bridge directory.** Report bytes freed.

THE QUESTION: **does a lines-only fit -- the method G253's control already validated -- transfer to a
second arena?**

METHOD:
  1. **Reuse G264's committed 300-frame survey** rather than re-surveying. **Re-screen it for frames with
     four usable, independently identifiable LINES**, built from **far-side and centre geometry** per
     G249/G263 (the near-side boundary is systematically absent in real footage). Candidates: far sideline,
     centre line, far-end baseline, the two far-end lane boundaries, the far-end free-throw line.
     **Report how many frames offer four, and how many offer three with which one missing.**
  2. **VERIFY IDENTITY BEFORE ANY FIT (G246's protocol): commit a zoomed crop for every fitted line**,
     stating which painted line it is and **what portion you actually observed.** A line inferred through
     players, or extended beyond the paint, is not the line. **G264 set the right standard by refusing
     logo curves; hold it.**
  3. **Fit with G253's landed harness UNCHANGED, lines-only** -- the same configuration as its passing
     control. **Report degeneracy: image angles between fitted lines, whether any three are near-concurrent
     or all four near-parallel, and the condition number.**
  4. **THE GATE IS A BLIND LADDER, exactly as G264 required.** Render the candidate plus perturbations at
     about 5, 10, 20, 40 and 100 px using **G257's displacement definition**, randomise the order, and
     **commit the order and your PASS / FAIL / CANNOT JUDGE verdicts in their own commit BEFORE
     un-blinding.** **Judge only INDEPENDENT geometry the fit did NOT use.**
  5. **THE GATE PASSES ONLY IF BOTH HOLD: the candidate is called PASS, AND perturbations at and above a
     stated magnitude are correctly called FAIL.** **A candidate PASS from a labeller who cannot FAIL a
     40 px perturbation is NOT a pass** -- that is what G255 found on amateur footage. **Report the
     discrimination threshold beside G257's 20 px.**
  6. **On a gate pass, measure withheld-geometry offsets with G252's method** and report median, p90, max
     and no-candidate count **beside G252's WNBA figures (median 5 px, p90 19 px)** -- the first
     cross-arena accuracy comparison this programme would have.
  7. **The fit residual is NOT evidence** (G242/G244/G247/G248), and **G254 showed an optimiser can improve
     its own objective while moving the projection off the markings.** **Per G257 a gate pass BOUNDS error
     at roughly the discrimination threshold; it does NOT certify correctness.**
  8. **Do NOT tune, relabel after any verdict, add a court key, or propose a production change. A FAIL, or
     "no frame offers four usable lines", is a FULL SUCCESS** -- report the screen counts either way.

**HONEST LIMITATIONS to state, not discover:** one clip, one frame, one labeller; **a second arena is a
replication, not a population.** **This CONSUMES manual geometry and is NOT automatic calibration**, which
remains 0/17. **Fitting a line from a short observed segment extrapolates it across the image and small
angular error amplifies with distance** -- report how much of each line you observed. Eye-label reliability
here has never cleared 80 pct blind agreement on four criteria; **G246 showed repeatable labels can be
uniformly wrong; G257 measured the eye gate at 20 px.** A perturbation is a uniform synthetic displacement,
not a real calibration error.

ACCEPTANCE RULE:
  metric        = the source identity check; counts of frames with four and with three usable lines and
                  which was missing; identity crops with observed portions; degeneracy diagnostics; the
                  committed blind ladder order and verdicts; the discrimination threshold beside G257's
                  20 px; the combined gate verdict stated FIRST in one line; and on a pass the
                  withheld-geometry offsets beside G252's WNBA figures
  before       = G253's lines-only control PASSED on WNBA and was independently re-judged PASS by G255;
                 G264 could not test the second arena because its centre-circle conic is replaced by a logo
  bar          = NO pass bar. **A gate pass would be the first evidence this method generalises across
                 arenas.** **A FAIL is an equally full success** -- arena-specificity matters before
                 anything is built on it. **"No frame offers four usable lines" is a third full success**
                 and would extend the camera-geometry finding to a third court.
  n            = 1 clip, the re-screened frame count, 1 frame fitted if any, 1 labeller -- name every
                 denominator in the verdict line
  eye check    = the blind ladder IS the gate; a single look is not sufficient
  must not move = every threshold, bar and verdict, `court_points_for_sport`, the coordinate contract,
                  G253's harness, G252's method and search radius, G257's displacement definition, G264's
                  committed survey, existing label files, `src/` and `domains/` (READ and IMPORT ONLY),
                  the pod daemon and keeper, the corpus
EVIDENCE: docs/evidence/tracking/g265_ncaa_lines_only_second_arena_2026-09-04.md with the source identity,
the line-count screen, every identity crop, the degeneracy diagnostics, the committed blind ladder and
ordering statement, the discrimination threshold, the combined gate verdict stated FIRST, any offsets,
every disk-guard probe with the `du -sm /workspace` figure, bytes freed, and a NOT VERIFIED list. **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
