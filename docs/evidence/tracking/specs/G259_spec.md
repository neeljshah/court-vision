GAP G259 | sport soccer | worktree a5 | log g259_soccer_penalty_area_seed
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file, NO `IMAGE_SPACE`, NO coordinate contract and NO threshold.** Build in
`scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G258 may be running on a6; N=2 is optimal). **Check first, do NOT
interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G256b AND G253 MEMOS FIRST.**

**WHY THIS RE-ISSUE EXISTS -- TWO FAULTS, BOTH MINE.**
G256b closed at limit, honestly and correctly given what it was asked to do. But:

**FAULT 1: I OVER-CONSTRAINED THE CONFIGURATION.** I told it to fit **two lines plus a conic**, because
that is what worked for basketball. **A soccer penalty area is a RECTANGLE of fixed, standard dimensions:
16.5 m deep by 40.32 m wide. Its four corners are four coplanar points with known relative coordinates --
a complete, non-degenerate 4-point homography on their own, with NO conic and NO dependence on pitch size.**
That is the classic soccer calibration input and I excluded it by construction. The goal area (5.5 m by
18.32 m) is a second such rectangle.

**FAULT 2: THE SURVEY STRIDE WAS TOO COARSE FOR THE TARGET.** G256b sampled **one frame every 60 seconds**
across a 5,975-second clip. **Penalty-area views in soccer occur in short bursts -- attacks, corners, set
pieces -- lasting seconds**, so a once-a-minute sample will usually miss them. G256b said exactly this in
its NOT VERIFIED list: *"whether a different unsampled camera instant has the required legal
configuration"*. **Its closure is therefore about its sample, not about the clip.**

**THE SOURCE, VERIFIED:** `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4`,
**2,341,768,743 bytes**, SHA-256 `7e4c123f91eb7e096ae2a018482818929b000c9bc2b8b9ca47b542b61ba8c55e`.
**`/workspace` EXISTS ONLY ON THE POD** -- reach it over ssh as G252, G253, G254 and G256b did; the local
`data/footage_corpus` is a different, smaller corpus and must not be used. Confirm bytes and SHA-256 first
and STOP if either differs.

THE QUESTION: **does a frame showing a full, unoccluded penalty area exist in this clip, and does its four
corners produce a soccer pitch homography?**

METHOD:
  1. **SURVEY AT A STRIDE MATCHED TO THE TARGET.** Use roughly **5 seconds**, not 60 -- about 1,195 samples
     across the clip, at low panel resolution so it stays cheap. **Say what stride you used and why.**
  2. **SCREEN FOR THE PENALTY AREA FIRST**, then the goal area, then any legal 2-line-plus-conic set as a
     fallback. **Report how many sampled frames show each configuration** -- that count is a useful result
     in itself, whatever the outcome.
  3. **STANDARD DIMENSIONS ONLY. The pitch is NOT a fixed size** (roughly 100-110 m by 64-75 m by rule).
     Permitted: **penalty area 16.5 m x 40.32 m; goal area 5.5 m x 18.32 m; penalty mark 11 m from the goal
     line; centre circle radius 9.15 m.** **NEVER fit touchline length or pitch width.** Report every
     feature used and the dimension assumed for it.
  4. **VERIFY IDENTITY BEFORE ANY FIT (G246's protocol): commit a zoomed crop for every labelled corner or
     fitted element, stating in words what is at that pixel.** G246 found all eight of G243b's labelled
     pixels were the wrong features and that **no fitted number can detect it** -- a 4-point fit has
     residual 0.000000000 px whether or not the correspondence is right.
  5. **CHECK CONDITIONING BEFORE TRUSTING THE FIT**: the quadrilateral's area as a fraction of the image
     and the minimum perpendicular distance of any corner from the line through the other three.
     **A foreshortened penalty area seen edge-on can be near-degenerate -- report it, do not fit it
     silently.**
  6. **HARD GATE: render and report PASS or FAIL in ONE LINE first, judged on INDEPENDENT geometry the fit
     did NOT use** -- the centre circle, the halfway line, the penalty arc, the far touchline. **Never
     judge on a fitted element. The fit residual is NOT evidence** (G242/G244/G247/G248), and **G254 showed
     an optimiser can improve its own objective while moving the projection off the markings.**
  7. **On a PASS, measure the withheld-geometry pixel offset with G252's method** and report it beside
     G252's WNBA figures (median 5 px, p90 19 px). **Remember G257: the eye gate resolves only ~20 px, so
     a PASS bounds the error, it does not certify correctness** -- word it that way.
  8. **Do NOT change `IMAGE_SPACE`, the coordinate contract or any production module, and do NOT propose a
     production change.** **A FAIL or a "no such frame exists" is a full success** -- report the
     configuration counts from step 2 either way.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` ON THE POD (baseline ~33,150 MB of 50,000), STOP and report if it
fails.** **A 5-second-stride survey is many samples -- stream it, keep panels small, never write a full
decode to disk.** **Do NOT delete any corpus source or the two abandoned partials in `footage_bridge`.**
Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one frame if a fit happens, one labeller. **This
CONSUMES manual geometry and is NOT automatic calibration**, which remains 0/17. Pitch length and width
are unknown by rule, so any claim depending on them is unsupported. Eye-label reliability here has never
cleared 80 pct blind agreement on four measured criteria; **G246 showed repeatable labels can be uniformly
wrong; and G257 measured the eye gate's resolution at 20 px.** A single-frame PASS says nothing about
propagation, coverage, detection or tracking on this clip.

ACCEPTANCE RULE:
  metric        = the survey stride and the count of sampled frames showing a penalty area, a goal area,
                  and any legal fallback configuration; the identity crops; the conditioning numbers; the
                  gate verdict stated FIRST in one line; and on a PASS the withheld-geometry offsets beside
                  G252's WNBA figures
  before       = soccer is `image_px` only with 0 accepted homographies over 200 reference frames; G256b
                 found no legal configuration in a 60-second-stride sample and said so was about its
                 sample, not the clip
  bar          = NO pass bar. **A PASS would be the first soccer pitch coordinates this programme has
                 produced.** **"No frame in a 5-second-stride survey shows a full penalty area" is an
                 equally full success** and would be a strong statement about broadcast framing. Do not
                 assume a non-standard dimension, do not fit a near-degenerate quad, and do not relabel
                 after the gate.
  n            = 1 clip, the survey sample count you state, 1 labeller -- name every denominator in the
                 verdict line
  eye check    = the identity crops gate the inputs; the withheld-geometry render is the GATE
  must not move = every threshold, bar and verdict, `IMAGE_SPACE`, the coordinate contract, G253's
                  harness, the pitch model, existing label files, `src/` and `domains/` (READ and IMPORT
                  ONLY), the pod daemon and keeper, the corpus, the two abandoned partials
EVIDENCE: docs/evidence/tracking/g259_soccer_penalty_area_seed_2026-09-04.md with the source identity, the
survey stride and configuration counts, every identity crop, the features and assumed dimensions, the
conditioning numbers, the gate verdict stated FIRST, any pixel offsets, every disk-guard probe, bytes
freed, and a NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit
BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
