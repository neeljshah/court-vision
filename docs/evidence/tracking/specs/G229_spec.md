GAP G229 | sport ncaa_basketball / wnba | worktree a5 | log g229_keypoint_gate_funnel
**MEASUREMENT ONLY. Change NO production code.** `src/` is HUMAN-GATED: READ only. `domains/` and
`scripts/platformkit/calibration/` are READ and IMPORT only -- **import them, edit nothing.** Build in
`scripts/platformkit/tracking/`.

**S1 MACHINE: RUN LOCALLY. Do NOT use the pod** -- three rows are running there. Everything is committed:
the 17 frames under `docs/evidence/tracking/g130_recensus/source_decodes/` and the labels at
`docs/evidence/tracking/g140_corner_targets/corner_pixel_targets.csv`.

**WHY THIS ROW EXISTS -- IT COULD MATERIALLY CHANGE A CONCLUSION I LANDED TONIGHT.** G227 scored
`BasketballKeypointProvider` at **0/17 all-four, 0/68 corners, and 17/17 ABSTENTIONS** -- it never
selected a paint quad on any frame. On that basis I recorded the in-repo classical calibration route as
**CLOSED AT LIMIT**, alongside G205/G208/G210b/G214 (0/17), G224 (top-hat worse) and G223 (scatter, no
correction). **But G227 explicitly left the decisive question NOT VERIFIED: WHICH GATE rejects.**
**If a single over-strict threshold explains 17/17 abstentions, "closed at limit" is too strong and I
will amend it. If the rejections are spread across gates, or the evidence genuinely is not there, the
closure stands and is now properly evidenced rather than merely asserted.**

**THE TOOL ALREADY EXISTS -- REUSE IT, DO NOT WRITE YOUR OWN.**
`scripts/platformkit/basketball_gate_funnel.py` was built for exactly this. Its docstring: *"The
basketball provider deliberately fails closed. This read-only diagnostic replays its actual paint gates
on real frames and counts the first one that rejects each frame. It also reports landmark co-occurrence,
which answers whether a partial paint can furnish a four-point solve."* It already imports
`BasketballKeypointProvider` and `_line_support`. **It takes a VIDEO argument
(`<video> [frames]`); this construct is 17 committed JPEGs, so adapt the INVOCATION in your own harness
-- call its `inspect_frame` on each image -- rather than editing the module.**

**THE GATES, read from `domains/basketball/tracking/keypoints.py` by the orchestrator, in the order they
reject:**
  1. `_candidate_quads`: `Canny(blurred, 50, 150)` -> `findContours` -> **`perimeter < 120.0` rejected
     (ABSOLUTE pixels)** -> `approxPolyDP(0.025 * perimeter)` -> **kept only if `len(approx) == 4`** ->
     `_ordered_quad` must succeed.
  2. `_paint`: **area >= `0.006 * width * height`**, and **shortest side >= `0.15 * height`**.
  3. `_paint`: **`_line_support(gray, quad) >= min_edge_support` (default 0.16)**.
  4. Only a surviving quad is named by baseline adjacency.
**G227 recorded plentiful contour evidence -- for example 1,970 / 1,955 / 817 raw contours and
594 / 570 / 115 at or above the 120 px perimeter -- so gate 1's perimeter cut is NOT the whole story and
the rejection happens later.**

THE QUESTION: **for each of the 17 frames, which gate is the FIRST to reject, and how close did the best
candidate come to passing it?**

METHOD:
  1. **Reproduce G227's 17/17 abstention first as a control**, with `min_edge_support=0.16` and native
     pixels. **If you cannot reproduce it, STOP and report that.**
  2. **Report the first-rejecting-gate distribution over 17 frames**, naming each gate exactly as above.
  3. **For every frame, report the BEST candidate's MARGIN at the gate that rejected it** -- how many
     quads reached each stage, the largest area as a fraction of `0.006 * W * H`, the longest shortest-
     side as a fraction of `0.15 * H`, and the highest `_line_support` against 0.16. **The margins are
     the deliverable**: "the best quad reached support 0.155 against a 0.16 bar" and "the best quad
     reached support 0.02" are completely different findings.
  4. **Report landmark co-occurrence**, which the tool already computes: **can a PARTIAL paint furnish
     four points?** If three corners are routinely available and one is not, that is a different and
     more tractable problem than total abstention.
  5. **Diagnose, do not fix. Do NOT tune any threshold, do NOT relax a gate, and do NOT report a score
     from a relaxed configuration as a result.** **If your margins suggest a specific threshold is the
     binding one, say so as a PROPOSAL for a future row and state what it would cost** -- a looser area
     or support gate admits scorebugs and non-court rectangles, which is precisely what those gates
     exist to exclude, so a proposal must name that risk.
  6. **Say plainly whether "CLOSED AT LIMIT" survives.** **"One threshold is binding and it is close" =
     the closure should be AMENDED, and say so. "Rejections are spread across gates" or "the best
     candidates are nowhere near any gate" = the closure STANDS and is now evidenced.** Both are full
     successes; do not prefer either.

**HONEST LIMITATIONS to state, not discover:** 17 frames is a small exhaustive construct and the same one
every calibration row uses. A margin measured on the BEST candidate per frame says nothing about whether
that candidate is actually the painted lane -- **a quad can pass every gate and still be the wrong
rectangle**, so a near-miss margin is not evidence that relaxing the gate would yield a correct paint.
Say that explicitly. `Canny(50, 150)` and the 120 px perimeter are ABSOLUTE while the area and side
gates are frame fractions, so the 640x360 frame is not treated like the 1080p ones; report it separately.

ACCEPTANCE RULE:
  metric        = first-rejecting-gate distribution over 17 frames; per-frame best-candidate margin at
                  each gate with the gate's own bar; landmark co-occurrence; the 640x360 frame reported
                  separately
  before        = G227 measured 17/17 abstentions and left the rejecting gate explicitly NOT VERIFIED;
                  the in-repo classical route was recorded CLOSED AT LIMIT on that basis
  bar           = NO pass bar. **This row does not try to make the provider work.** "A single gate is
                  binding with a small margin" and "no candidate is close on any gate" are equally full
                  successes, and the second one strengthens a closure I have already published.
  n             = 17 frames (CONSTRUCT, exhaustive)
  eye check     = for the 3 frames whose best candidate came closest to passing, render that candidate
                  quad against the labelled corners; commit them
  must not move = every threshold, `min_edge_support`, the area / side / perimeter / Canny gates, the
                  12 px protocol, G205's scorer contract, the court model, the coordinate contract,
                  every bar and verdict, `src/` (READ ONLY), `domains/` and
                  `scripts/platformkit/basketball_gate_funnel.py` (READ and IMPORT ONLY), the pod (DO
                  NOT USE IT), the corpus
EVIDENCE: docs/evidence/tracking/g229_keypoint_gate_funnel_2026-09-04.md with the abstention control, the
first-rejecting-gate table, the per-frame margins against each gate's bar, landmark co-occurrence, the
renders, an explicit verdict on whether CLOSED AT LIMIT survives, any proposal clearly marked for a
future row with its scorebug-admission risk named, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: a per-file test for any harness added, pasted. NEVER a full pytest. **If a commit grows an
allowlisted file, raise its entry in `tests/platformkit/test_loc_rail_scope.py` in the SAME commit
(contract A12).**
COMMIT: explicit pathspec only, no push. Report the sha.
NEVER PARK.
