GAP G261 | sport soccer | worktree a5 | log g261_soccer_penalty_box_lines
**MEASUREMENT ONLY. Change NO production code.** `src/` and `domains/` are READ and IMPORT only. **Change
NO label file, NO `IMAGE_SPACE`, NO coordinate contract and NO threshold.** Build in
`scripts/platformkit/tracking/`.

**HELD UNTIL A POD LANE IS FREE** (G260 may be running on a6; N=2 is optimal). **Check first, do NOT
interrupt a running row, and EXCLUDE YOUR OWN PROCESS, YOUR CHECKER COMMAND AND ITS PARENT.**

**READ THE LANDED G253, G256b AND G259 MEMOS FIRST.**

**WHY THIS ROW EXISTS -- I FAILED TO APPLY G253's OWN LESSON TO SOCCER, TWICE.**
G259 surveyed **1,195 samples at 5-second stride across the whole clip and found ZERO complete penalty-area
or goal-area rectangles** with four identifiable unoccluded corners, confirming candidates at native
resolution rather than from panels. That negative stands and is well-evidenced.

**But G253's whole insight was that LINES SURVIVE OCCLUSION AND CROPPING FAR BETTER THAN THE CORNERS THEY
DEFINE -- "when four identifiable points do not exist, count CONSTRAINTS, not points."** I then specified
soccer twice in terms of points and a conic, and never in terms of the box's own edges.

**THE PENALTY AREA'S FOUR EDGES ARE ALL FIXED BY RULE, INDEPENDENT OF PITCH SIZE.** In pitch coordinates
anchored at the goal centre:
  - **goal line: y = 0**
  - **penalty-area front edge: y = 16.5 m** (parallel to the goal line)
  - **penalty-area side edges: x = -20.16 m and x = +20.16 m** (40.32 m apart, symmetric about goal centre)

**Four line correspondences give 8 constraints for a homography's 8 degrees of freedom -- exactly enough,
with no dependence on pitch length or width.** **And a line can be fitted from ANY visible portion of it,
so a corner hidden by a player costs nothing.** That is precisely the case G259 kept rejecting.

Optional additional standard-dimension constraints, all pitch-size independent: **goal-area edges
(y = 5.5 m, x = +/-9.16 m)**, the **penalty mark (11 m from the goal line)**, and the **penalty arc
(radius 9.15 m about the mark)**.

**THE SOURCE, VERIFIED:** `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4`,
**2,341,768,743 bytes**, SHA-256 `7e4c123f91eb7e096ae2a018482818929b000c9bc2b8b9ca47b542b61ba8c55e`.
**`/workspace` EXISTS ONLY ON THE POD** -- reach it over ssh as G252-G259 did; the local corpus is
different and must not be used. Confirm bytes and SHA-256 first and STOP if either differs.

THE QUESTION: **can a soccer homography be fitted from the penalty box's EDGES, where its corners are
never simultaneously clean?**

METHOD:
  1. **Reuse G259's committed survey** rather than re-surveying. Its 12 panels and manifest are landed.
     **Re-screen it for frames where the box EDGES are visible in usable extent** -- a partially occluded
     line is fine, an absent one is not. **Report how many samples show 4, 3 and 2 usable edges.** That
     count is a result whatever follows.
  2. **VERIFY IDENTITY BEFORE ANY FIT (G246's protocol): commit a zoomed crop for EVERY fitted line**,
     stating in words which painted line it is. **A line inferred through a player, a goal-net edge, or an
     extended segment beyond the paint is NOT the line** -- G259 was right to refuse those and you must
     too. **Say which portion of each line you actually used.**
  3. **Fit from the four box edges.** Report the fitted lines in image space and the world dimension
     assumed for each. **NEVER fit touchline length or pitch width.**
  4. **CHECK DEGENERACY EXPLICITLY.** The box is two pairs of parallel world lines, so report the two
     image vanishing points, the angles between fitted lines, whether any three are near-concurrent, and
     the condition number of the system solved. **A near-edge-on view of the box is degenerate -- report
     it, do not fit it silently.**
  5. **HARD GATE: render and report PASS or FAIL in ONE LINE first, judged on INDEPENDENT geometry the fit
     did NOT use** -- the centre circle, the halfway line, the penalty arc, or the goal-area lines if you
     did not fit them. **Never judge on a fitted element. The fit residual is NOT evidence**
     (G242/G244/G247/G248), and **G254 showed an optimiser can improve its own objective while moving the
     projection off the markings.**
  6. **On a PASS, measure withheld-geometry offsets with G252's method** and report beside G252's WNBA
     figures (median 5 px, p90 19 px). **Per G257, a PASS bounds error at roughly the eye gate's
     resolution; it does NOT certify correctness** -- word it that way.
  7. **Do NOT change `IMAGE_SPACE`, the coordinate contract or any production module. A FAIL, or "no frame
     has four usable edges", is a FULL SUCCESS** -- report the edge counts from step 1 either way.

**DISK GUARD, BINDING:** `df` is NON-AUTHORITATIVE. **`dd conv=fsync` probe before writing, record
`du -sm /workspace/nba-ai-system/data` ON THE POD (baseline ~33,163 MB of 50,000), STOP and report if it
fails.** Stream any decode; never write a full decode to disk. **Do NOT delete any corpus source or the
two abandoned partials in `footage_bridge`.** Report bytes freed.

**HONEST LIMITATIONS to state, not discover:** one clip, one frame if a fit happens, one labeller. **This
CONSUMES manual geometry and is NOT automatic calibration**, which remains 0/17 -- hand-fitting lines is no
more automatic than hand-fitting points. Pitch length and width remain unknown, so no claim may depend on
them. **Fitting a line from a short visible segment extrapolates it across the image and small angular
error amplifies with distance** -- say how much of each line you actually observed. Eye-label reliability
here has never cleared 80 pct blind agreement on four measured criteria; **G246 showed repeatable labels
can be uniformly wrong; G257 measured the eye gate at 20 px.**

ACCEPTANCE RULE:
  metric        = the counts of samples with 4, 3 and 2 usable box edges; the identity crops with the
                  observed portion of each line; the fitted lines and assumed dimensions; the degeneracy
                  report including vanishing points and condition number; the gate verdict stated FIRST;
                  and on a PASS the withheld-geometry offsets beside G252's WNBA figures
  before       = soccer has 0 accepted homographies; G259 found 0 complete rectangles in 1,195 samples,
                 but nothing has tried the box's EDGES, which are pitch-size independent and survive
                 occlusion
  bar          = NO pass bar. **A PASS would be the first soccer pitch coordinates this programme has
                 produced, from geometry that is actually present.** **"No frame has four usable edges" is
                 an equally full success** and would close point-and-line calibration for this footage on
                 measurement. Do not assume a non-standard dimension, do not fit a degenerate
                 configuration, and do not relabel after the gate.
  n            = 1 clip, the re-screened sample count, 1 labeller -- name every denominator in the verdict
                 line
  eye check    = the identity crops gate the inputs; the withheld-geometry render is the GATE
  must not move = every threshold, bar and verdict, `IMAGE_SPACE`, the coordinate contract, G253's
                  harness, the pitch model, G259's committed survey, existing label files, `src/` and
                  `domains/` (READ and IMPORT ONLY), the pod daemon and keeper, the corpus, the two
                  abandoned partials
EVIDENCE: docs/evidence/tracking/g261_soccer_penalty_box_lines_2026-09-04.md with the source identity, the
edge-count re-screen, every identity crop and observed line portion, the fitted lines and dimensions, the
degeneracy report, the gate verdict stated FIRST, any offsets, every disk-guard probe, bytes freed, and a
NOT VERIFIED list. **ADD A RESULTS_LEDGER.md ROW IN THE SAME COMMIT AS THE MEMO.** Commit BEFORE reporting
(A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. **If your work spans several commits, make EVERY commit before
you finish.** Report the sha.
NEVER PARK.
