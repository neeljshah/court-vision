GAP G264 | sport ncaa_basketball | worktree a5 | log g264_line_conic_second_arena
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file and NO threshold.** Build in `scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G260 may be running on a6; N=2 is optimal). **Check first, do NOT
interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G253, G255 AND G257 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- EVERY POSITIVE RESULT TONIGHT IS ONE CLIP IN ONE ARENA.**
G233d's seeded calibration and G253's line-and-conic method both rest entirely on `wnba__wnba_01.mp4`.
Every memo carries "one clip, one seed, one arena" in its limitations, and **nothing has tested whether the
method transfers to a different broadcast of a different court.** That is the single largest gap in the
night's positive findings.

**AND THIS ROW FIXES THE GATE ITSELF, USING WHAT G255 AND G257 COST US.** G253 called its amateur fit a
PASS; G255 blind-re-judged it CANNOT JUDGE and the headline was retracted; **G257 then measured the eye
gate's resolution at 20 px.** A bare eye-gate PASS is therefore weak evidence. **From here the gate should
be a BLIND LADDER, not a single look** -- and this row is where that becomes standard practice.

**THE SOURCE, VERIFIED BY ME DIRECTLY ON THE POD:**
`/workspace/nba-ai-system/data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4`,
**3,580,059,573 bytes**, SHA-256 `9b35bd59d8b5b0e04737389b6661d7f8d37fac07a348056b081a6815ff5eea40`,
**1920x1080, 205,444 frames, 30000/1001 fps, 6,855.014 s.** **`/workspace` EXISTS ONLY ON THE POD** --
reach it over ssh as G252-G263 did. Confirm bytes and SHA-256 first and STOP if either differs.

**COURT MODEL:** `court_points_for_sport` has an `ncaa_basketball` key returning `(19,0) (31,0) (19,19)
(31,19)` -- **94 x 50 ft, 12-ft lane, 19-ft paint depth.** Use it; **do NOT add a key and do NOT use the
`wnba` 16-ft lane.**

THE QUESTION: **does the line-and-conic method transfer to a second broadcast of a different court, and
does it survive a blind ladder gate?**

METHOD:
  1. **Survey for a frame with usable far-side and centre geometry.** **Per G249/G263, the NEAR-side
     boundary is systematically absent in real footage, so build from FAR-SIDE AND CENTRE features** -- far
     sideline, centre line, centre circle, lane lines at the far end. Say how you surveyed and what you
     found. **Report how many sampled frames offer a usable configuration** -- that count transfers to
     other rows.
  2. **VERIFY IDENTITY BEFORE ANY FIT (G246's protocol): commit a zoomed crop for every fitted line and for
     any conic**, stating what is at it and **what portion you actually observed.**
  3. **Fit with G253's landed harness UNCHANGED** and report its degeneracy diagnostics: image angle
     between fitted lines, observed conic fraction if used, condition number.
  4. **THE GATE IS A BLIND LADDER, NOT A SINGLE LOOK. This is the part that matters.**
     Render the candidate **and** deliberately perturbed versions of the same map at identical scale and
     style, using **G257's displacement definition and a comparable ladder** (about 5, 10, 20, 40 and
     100 px). **Randomise the order, and COMMIT the order and your PASS / FAIL / CANNOT JUDGE verdicts in
     their own commit BEFORE un-blinding**, exactly as G257 and G255 did.
     **Judge only INDEPENDENT geometry the fit did NOT use.**
  5. **THE GATE PASSES ONLY IF BOTH HOLD: the candidate is called PASS, AND the perturbations at and above
     some stated magnitude are correctly called FAIL.** **A candidate PASS alongside a labeller who cannot
     FAIL a 40 px perturbation is NOT a pass** -- it shows the render cannot be judged, which is exactly
     what G255 found on amateur footage. **Report the discrimination threshold beside G257's 20 px.**
  6. **On a gate pass, measure withheld-geometry offsets with G252's method** and report median, p90, max
     and no-candidate count **beside G252's WNBA figures (median 5 px, p90 19 px)** -- the first
     cross-arena accuracy comparison this programme would have.
  7. **The fit residual is NOT evidence** (G242/G244/G247/G248), and **G254 showed an optimiser can improve
     its own objective while moving the projection off the markings.** **Per G257, a gate pass BOUNDS the
     error at roughly the discrimination threshold; it does NOT certify correctness.**
  8. **Do NOT tune, do NOT relabel after seeing any verdict, do NOT add a court key, and do NOT propose a
     production change. A FAIL is a full success** -- it would mean the method is arena-specific, which is
     essential to know before anything is built on it.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` ON THE POD (baseline ~33,210 MB of 50,000), STOP and report if it
fails.** Stream the decode; never write a full decode to disk. **Do NOT delete any corpus source or the
two abandoned partials in `footage_bridge`.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one frame, one labeller. **A second arena is a
replication, not a population.** **This CONSUMES manual geometry and is NOT automatic calibration**, which
remains 0/17. Eye-label reliability here has never cleared 80 pct blind agreement on four criteria, and
**G246 showed repeatable labels can be uniformly wrong.** **A perturbation is a uniform synthetic
displacement and is not a real calibration error**, which distorts non-uniformly -- say so. The NCAA court
model is assumed from the key, not measured from the footage.

ACCEPTANCE RULE:
  metric        = the source identity check; the count of frames with a usable far-side/centre
                  configuration; the identity crops with observed portions; the degeneracy diagnostics;
                  the committed blind ladder order and verdicts; **the discrimination threshold beside
                  G257's 20 px**; the combined gate verdict stated FIRST in one line; and on a pass the
                  withheld-geometry offsets beside G252's WNBA figures
  before       = every positive calibration result in this programme is one clip in one arena, and a bare
                 eye-gate PASS has been shown weak: G253 PASS -> G255 CANNOT JUDGE -> retraction, with
                 G257 measuring the gate at 20 px
  bar          = NO pass bar. **A gate pass on a second arena, with demonstrated discrimination, would be
                 the first evidence this method generalises at all.** **A FAIL is an equally full
                 success** -- arena-specificity is essential to know before building on it. **"The
                 labeller cannot discriminate on this footage either" is a third full success** and would
                 say the eye gate is the binding constraint across arenas, not the method.
  n            = 1 clip, 1 frame, 1 labeller, the ladder rungs you state -- name every denominator in the
                 verdict line
  eye check    = the blind ladder IS the gate; a single look is no longer sufficient
  must not move = every threshold, bar and verdict, `court_points_for_sport`, the coordinate contract,
                  G253's harness, G252's method and search radius, G257's displacement definition,
                  existing label files, `src/` and `domains/` (READ and IMPORT ONLY), the pod daemon and
                  keeper, the corpus, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g264_line_conic_second_arena_2026-09-04.md with the source identity, the
survey and configuration count, every identity crop, the degeneracy diagnostics, the committed blind
ladder with its ordering statement, the discrimination threshold, the combined gate verdict stated FIRST,
any offsets beside G252's, every disk-guard probe, bytes freed, and a NOT VERIFIED list. **ADD A
RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
