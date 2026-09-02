# Line-candidate pattern analysis: is the four-sport failure shared?

**Date:** 2026-09-02. **Status:** design/analysis document only. No code,
threshold, or register row changed. Sources: `g60_clay_horizontals_2026-09-02.md`,
`g75_paint_role_assignment_2026-09-02.md`, `CALIBRATION_STRATEGY_2026-09-02.md`,
and a read of the six geometry modules named below. Every numeric claim here is
either quoted from those memos or derived by reading code; nothing new was run
except one arithmetic check on the basketball gate constants (noted inline).

**Verdict up front.** The failure is NOT one shared mechanism. The four sports
fail at the same STEP -- turning anonymous image line candidates into named
physical lines -- through four different proximate causes: evidence recall
(tennis clay), selection invariants (basketball), symbolic identity degeneracy
(football), and provider absence (soccer). No single kernel change raises the
accept rate of more than one sport. Two genuinely shared, fix-once pieces do
exist, but they are discipline components, not accept-rate fixes: a sport-blind
independent-verification accept gate (four eventual consumers) and a
termination-topology role scorer (exactly two prospective consumers: basketball
and soccer). The "fix it once at the kernel" hypothesis is rejected for the
accept-rate failures and accepted only for those two components.

---

## 1. Classification of the four failures

| sport | proximate failure | class | evidence |
|---|---|---|---|
| tennis (clay) | far-baseline candidate missing/unusable in the surviving horizontal evidence; clutter is an aggravator, not the binding constraint | true-candidate RECALL | G60 counterfactual (measured): exclusion of every above-court horizontal gives 4/40 role passes, 0/40 accepts |
| basketball | hypothesis scorer built on image-space (affine) parallel/orthogonal invariants that reject the perspective-distorted true paint and maximally reward screen-aligned graphics; plus the only candidate pipeline of the four with no on-plane evidence mask | hypothesis SELECTION | G75 eye check (measured): 23/30 emit nothing, every emitted quad follows graphics/borders/structures; mechanism is code-derived (section 3), not yet measured |
| football | yard lines are periodic and locally pixel-identical; every classical identity route measured dead (OCR read 12.39 pct, cross-ratio 0/4 conditions, rigid solve 0/175); module deliberately fails closed | symbolic IDENTITY degeneracy | FOOTBALL_POST_OCR_DECISION via CALIBRATION_STRATEGY sec 1.3 (measured) |
| soccer | the naming step was never built: `detect_pitch_corners` returns `None` by design, and the one named landmark family (centre circle: centre/top/bottom) is three collinear points, degenerate for a planar solve | provider ABSENCE | code (`domains/soccer/tracking/keypoints.py`, `geometry.py`) + CALIBRATION_STRATEGY sec 1.1 |

Adversarial check, as instructed: "spurious segments swamp the true ones"
describes NONE of the four bindingly. G60 measured that away for tennis.
Basketball's polluted candidate pool is real (no mask) but the eye-checked
wrong emissions and the 23/30 silence are both explained by the scorer, not by
swamping (section 3). Football's candidates are clean and correctly detected --
identity, not clutter, is dead. Soccer never reaches the step where clutter
could matter. Genuinely shared mechanism pairs: none. What tennis-clay and
basketball share is a NEGATIVE result: cleaning the candidate pool is not the
fix, because the acceptance logic cannot accept the true structure from these
inputs (tennis: the true line is not in the pool; basketball: the pool may
contain it but the gates reject it -- G84's question).

---

## 2. What the G60 counterfactual means, from the code

The G60 decision set is frames whose production gate is `horizontal_roles`.
In `domains/tennis/tracking/court_lines.py`, that gate is emitted only at the
END of `select_court_lines`, after all three role templates fail:

```python
_ALONG_TEMPLATES = (
    ("far", "far_service", "net", "near_service", "near"),
    ("far", "far_service", "near_service", "near"),
    ("far", "net", "near_service", "near"),
)
...
    for roles in _ALONG_TEMPLATES:
        picked = _match(positions, len(roles), _ALONG_TARGETS[roles], [windows[role] for role in roles])
        ...
    return None, "horizontal_roles"
```

Every template requires `"far"`, whose window is
`"far": (top - 0.1 * span, top + 0.1 * span)` -- the top decile of the derived
court region. So a frame with NO horizontal candidate near the top of the
court region fails `horizontal_roles` no matter how clean the rest of the
evidence is. Removing spurious segments is a precision operation; the binding
failure is recall of the far baseline. CALIBRATION_STRATEGY section 4 states
the same thing as a measurement: "the far baseline is never found under
white-on-orange contrast plus ~250 spurious horizontals" (their claim, cited,
consistent with the counterfactual; I did not re-measure it).

So the answer to "which is it" is: BOTH, split by subpopulation, and the code
says where.

- **36/40: the spurious segments were never the binding constraint.** With all
  above-court horizontals removed, role assignment still fails. Two code paths
  produce that: (a) no surviving candidate satisfies the `far` window in any
  template (missing true line), or (b) horizontal cluster starvation --
  `if len(horizontal_clusters) < 4 or len(vertical_clusters) < 5: return None,
  "vertical_cluster_count"` fires because removing 82.6 pct of horizontals
  drops the cluster count below 4 (note this gate name conflates the
  horizontal and vertical conditions; G60 does not record which of (a)/(b)
  each frame hit, so the split between them is unknown). Either way the
  constraint is missing true horizontal structure at or below the horizon,
  not clutter.
- **4/40: something else fails immediately after.** Role assignment passed but
  `solve_corners` rejected all four (0/40 accepts), i.e. one of `depth_order`,
  `homography`, `skew`, `image_bounds`, or `far_right_consistency` fired.
  Which gate is not recorded in G60. Given G60's own frame-4838 observation
  (a crowd cutaway reaching `horizontal_roles` on a spurious vertical guide),
  the plausible reading is that those 4 role sets were structures that fit the
  windows without being the court, and the independent-correspondence gates
  did exactly their job. The exclusion boundary itself is derived from the
  solver's chosen verticals, so when the verticals are wrong the "above-court"
  label is wrong too -- G60 flags this and it bounds how much the exclusion
  could ever help.

Note also a subtlety in why exclusion moved role passes from 0 to 4 at all:
`select_court_lines` already windows horizontal candidates to
`top - margin <= row <= bottom + margin`, so most above-court segments were
never candidates directly. But `TennisAdapter._cluster_lines(horizontal, ...)`
clusters ALL horizontals BEFORE fitting and windowing, so above-horizon
segments pollute the clusters whose fitted lines are then windowed. Exclusion
changes the clustering, which is where the marginal 4 passes came from.

**Implication for basketball G84.** G84 is measuring candidate line quality.
G60's lesson transfers directly: proving the candidate set clean (precision)
answers the wrong question if the true lines are absent (recall) or if the
selection logic cannot accept them. A clean candidate set would help
basketball ONLY IF both (a) the four true paint lines are present among the
candidate groups and (b) the true four-line set passes `assign_paint_roles`'
gates. Section 3 argues from the code that (b) is currently false for
perspective views, in which case a perfectly clean candidate set converts
G75's "7 wrong + 23 nothing" into "30 nothing" -- the exact shape of the G60
counterfactual. G84 should therefore measure both: true-line recall in the
candidate groups AND the gate scores of the hand-labelled true four-line set.

---

## 3. Basketball: the two code-level mechanisms behind G75

Both mechanisms are read from `domains/basketball/tracking/line_calibration.py`;
neither has been measured yet. They are stated here as testable predictions
for G84, not as results.

**Mechanism 1: no on-plane evidence mask -- unique among the four sports.**

```python
def detect_lsd_segments(frame: np.ndarray, min_length: float = 60.0) -> list[ObservedSegment]:
    """Return observed grayscale LSD fragments; no brightness-mask tuning."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    detected = cv2.createLineSegmentDetector().detect(gray)[0]
```

LSD runs on the raw full-frame grayscale. Tennis gates evidence through the
white top-hat mask; football through `field_roi_mask` plus
`segment_field_support`; soccer through `_pitch_mask` plus adaptive white.
Basketball alone admits score-bug graphics, broadcast borders, and arena
structure into the candidate pool at full strength -- exactly the structures
the G75 eye check found in every emitted hypothesis.

**Mechanism 2: the scorer's invariants are affine, not projective.**

```python
parallel = _parallel_score(transverse[0], transverse[1]) + _parallel_score(lanes[0], lanes[1])
orthogonal = _orthogonal_score(transverse[0], lanes[0]) + _orthogonal_score(transverse[1], lanes[0])
if parallel < 1.8 or orthogonal < 1.6:
    continue
```

where `_parallel_score` is the absolute dot product of IMAGE direction
vectors. Arithmetic on the constants (this I ran; it is arithmetic, not a
frame measurement): `parallel >= 1.8` requires each pair to average
`|cos| >= 0.9`, i.e. within ~25.8 degrees of parallel in image space;
`orthogonal >= 1.6` requires the transverse lines to average `|cos| <= 0.2`
against the lane line, i.e. within ~11.5 degrees of image-perpendicular.
Parallelism and perpendicularity are NOT preserved under projection. A
midcourt broadcast view foreshortens the paint so that baseline-to-lane image
angles are commonly far from 90 (at 60 degrees the per-term orthogonal score
is 0.5, total 1.0, rejected before scoring). Meanwhile a screen-aligned
graphic or frame border is a genuine image-space rectangle and scores the
theoretical maximum, 2.0 + 2.0, on both gates. One pair of thresholds thus
explains both G75 symptoms at once: the true paint is filtered out (23/30
emit nothing) and, when anything survives, it is the most fronto-parallel
rectangle in frame -- a graphic (7/7 eye-checked hypotheses wrong). G76's
`paint_solvable_share = 0.5732` says humans judge the true structure visible
in a majority of tiles, which is consistent with selection, not visibility,
being the failure. Uncertain until G84 scores real frames, and said so.

The fix shape, when G84 confirms or refutes this: (a) add an on-plane
evidence gate (court-colored-region support per segment, the pattern the
other three sports already implement -- inherently sport-specific, belongs in
the basketball adapter); (b) replace the parallel/orthogonal gates with
projective-consistent selection -- termination topology (the module's own
`_covers` machinery, currently a minor additive term) as the primary score,
plus a solve-and-verify step against an independent feature. Tennis's
cross-ratio trick does not transfer (2-3 lines per direction, as
CALIBRATION_STRATEGY 1.2 already notes); termination has to carry the load.

---

## 4. What is genuinely shared, and where it belongs

**Shared and fix-once (build in kernel space): the independent-verification
accept gate.** Tennis implements it inline and it is the reason clay fails
HONESTLY instead of emitting garbage:

```python
    # Independent fifth correspondence: the corner the four-anchor fit predicts
    # must land on the far/right intersection the image actually shows.
    observed = TennisAdapter._intersection(court.far, court.right)
    if observed is None or float(np.linalg.norm(observed - far_right)) > FAR_RIGHT_TOLERANCE_WIDTH_FRACTION * width:
        return None, "far_right_consistency"
```

Basketball has `line_residual` but no gate and no caller; soccer's
leave-one-out in `_validated_homography` validates on the SAME structure it
fits (the heldout_validation_blindspot lesson: it passed a wrong-scale grid);
football's design already refuses to emit without one. The sport-blind
contract: given a solve from named features and at least one PHYSICALLY
DIFFERENT withheld feature (a fifth line, a circle radius, a known width),
predict it, gate on tolerance, fail closed with a named gate. This is one
helper, four eventual consumers, and it raises no accept rate anywhere -- it
converts wrong emissions into honest rejections, which is what the harness
actually needs (G42, B8). Placement: `scripts/platformkit/calibration/`
(kernel/ is human-gated; this is the designated safe kernel-space landing
zone), signature over named-feature dicts so it is sport-blind.

**Shared with exactly two consumers (kernel-space helper, smaller): a
termination-topology role scorer.** "Line A ends at line B; line C continues
past both" -- tennis pins horizontal roles this way (one-sided extent
windows), basketball's rewrite needs it as the primary score, and soccer's
box-corner provider is specified to use the same reasoning (box side lines
terminate at the goal line and the 16.5 m line, CALIBRATION_STRATEGY 1.1).
Football cannot use it: periodic yard lines all terminate identically at the
sidelines. Tennis works and should not migrate. So: two consumers, one
helper -- given candidate groups with fitted lines and observed extents plus
a per-sport termination table, score role assignments. Worth sharing by the
two-uses rule; do not oversell it as a four-sport fix.

**Not shared -- and explicitly do NOT build a kernel declutter/cleaning
helper.** G60 measured that cleaning is not binding for tennis; section 3
predicts the same for basketball; football and soccer do not have a clutter
problem. Each remaining accept-rate blocker is sport-specific:

- tennis clay: evidence RECALL of the far line under clay contrast (the
  top-hat contrasts 45/60 were tuned on 720p hard court per the module's own
  header comment) -- a per-sport, likely per-surface evidence problem;
- basketball: adapter-level mask + scorer rewrite (section 3);
- football: the real-labelled 5-way numeral classifier behind its pre-sized
  gate (a learning project, per the post-OCR decision);
- soccer: the box-corner provider (a detection project consuming the two
  shared helpers above).

The shared candidate PLUMBING (segments -> cluster -> fitLine -> groups) is
near-duplicated four times (`_fit_line` in the soccer and football modules is
byte-similar), but deduplicating it fixes none of the four failures; it is
refactoring, not a fix, and is not recommended as a lane.

---

## 5. Ranking: what to build next

1. **Amend G84 (basketball candidate quality) to measure two things, then run
   it.** (a) True-line recall: are the four hand-labelled paint lines present
   among `candidate_line_group_details` output? (b) Gate admissibility: does
   the true four-line set pass `assign_paint_roles`' parallel/orthogonal
   thresholds on real broadcast frames? This is the cheapest measurement, it
   uses existing G68 tiles, it directly tests section 3's code-derived
   prediction, and it is the exact G60 lesson applied before anyone writes a
   cleaner: if (b) fails, a clean candidate set yields 30/30 nothing and the
   fix is the scorer, not the input.
2. **Soccer: run the pre-registered box-solvability census (CALIBRATION_
   STRATEGY 3.1), then build the box-corner provider.** Highest expected
   payoff per the existing tractability ranking: the entire solve/validation
   stack is built and waiting on one detector, and the decision rule
   (pooled share below ~0.10 kills the lane) is already registered.
3. **Build the sport-blind independent-verification accept gate in
   `scripts/platformkit/calibration/`, alongside item 2.** Small, one helper,
   consumed immediately by the soccer provider and the basketball rewrite;
   also the correct replacement for soccer's same-structure leave-one-out.
   The termination-topology role scorer rides in the same lane (two
   consumers, same file family).
4. **Tennis clay: a far-baseline recall limit measurement.** Before touching
   any contrast constant: on the G60 decision-set frames, does ANY evidence
   pass at ANY top-hat contrast contain Hough segments inside the `far`
   window? If no, clay needs a different evidence channel (surface-
   conditional contrast or color-plane choice) and that is a new G-row; if
   yes, the failure moves to clustering/windowing and the fix is different.
   Pre-register the question; do not move `TOPHAT_CONTRASTS` on sight of a
   result (B10).
5. **Football numeral classifier: fund last, unchanged.** The re-entry gate
   is already sized (per-crop accuracy ~2x to ~0.22); it is a labelling and
   training project and no kernel work in items 1-4 changes its economics.
   Football stays honestly at IMAGE_PX_DECLARED until the gate clears.

The honest conclusion the task allowed for is close to the truth but not
exactly it: these are four separate accept-rate problems, and the ONE thing
worth building once is not a fix for any of them -- it is the verification
discipline (items 3) that keeps all four honest while their separate fixes
land in the order above.

---

## NOT VERIFIED

- Section 3's basketball mechanisms (fronto-parallel gate rejection of the
  true paint; graphics scoring maximally) are code-derived predictions. No
  frame was scored in this analysis. G84 item 1 is their test.
- "The far baseline is never found under white-on-orange contrast" is
  CALIBRATION_STRATEGY's statement, cited, not re-measured here.
- The 36/40 split between missing-far-candidate and horizontal-cluster
  starvation on G60's clean counterfactual is not recorded in G60 and was
  not measured here; both paths are recall-side and the conclusion does not
  depend on the split.
- Which `solve_corners` gate rejected G60's 4 clean role passes is not
  recorded in G60.
- No solver, threshold, gate, or register row was changed by this document.
