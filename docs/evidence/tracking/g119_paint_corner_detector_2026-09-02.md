# G119 direct paint-corner detector feasibility

**Verdict: NOT VALIDATED.** The localisation tolerance is preregistered at
**16 canonical pixels** (2.5 percent of the 640-pixel width, to allow a local
response to lie within a visibly rasterised intersection rather than exactly
on a one-pixel crossing) in
[`g119_corners/protocol.md`](g119_corners/protocol.md), written before this
proposal route ran.

## Fixed input and proposal

This uses the unchanged committed G111 seed (`1112026`), its exact 220 unique
`(clip, source_frame, slot)` rows, and its committed corner-visibility labels.
It neither samples nor labels another frame. The simple proposal is Harris
`goodFeaturesToTrack` on each G111 render after cropping only G111's added
34-pixel title band and resizing to canonical width 640. Its full fixed
parameters are in the protocol. It does not call any line detector, line
grouping, role assignment, or `line_calibration.py`.

The raw output is [`g119_corners/proposals.csv`](g119_corners/proposals.csv):
36,434 ranked local responses across all 220 fixed frames. This is a proposal
artifact, not a success count.

## Why no recall is reported

G111's committed labels identify which named physical corners were visible,
but provide no target pixel coordinates for any of them. The label schema has
no coordinate column; the deterministic audit records that fact in
[`g119_corners/validation.json`](g119_corners/validation.json). The
predeclared 16-pixel rule consequently has no non-circular target against
which to apply itself. Treating any detected local response as the visible
corner after inspecting it would make detector output become ground truth.

The scorer therefore fails closed at the first requested visible role, with
the exact failure retained in [`g119_corners/score_blocker.txt`](g119_corners/score_blocker.txt).
No rows were excluded, and no post-hoc target coordinates were drawn.

| Corner role | G111 visible-role denominator | Recall / Wilson 95 percent interval |
|---|---:|---|
| `paint_near_baseline_left_corner` | 161 | NOT VALIDATED: no committed target pixels |
| `paint_near_baseline_right_corner` | 161 | NOT VALIDATED: no committed target pixels |
| `paint_near_free_throw_left_corner` | 147 | NOT VALIDATED: no committed target pixels |
| `paint_near_free_throw_right_corner` | 147 | NOT VALIDATED: no committed target pixels |
| **Overall** | **616** | **NOT VALIDATED: no committed target pixels** |

## Eye check

The committed [`g119_corners/renders/`](g119_corners/renders/) directory has
44 overlays: slots 2, 7, 12, and 17 from each of the 11 clips, so the render
selection spans the decision set rather than a head slice. The first 30 of up
to 180 raw local responses are marked in each overlay. I inspected NCAA and
WNBA overlays from both wide and close views. The high-ranked responses visibly
cluster on lower-third score graphics, crowd texture, players, centre logos,
and painted art as well as court imagery; they are not evidence that a marked
point is a named paint corner.

## Line-route comparison and decision

G115 had not landed a line-recall result at the time this G119 measurement
ran, so a same-frame comparison is pending; this memo does not restate a
line-route recall it did not measure.

**One-sentence decision:** No verified conclusion shows that corner-first finds
more constraints than the line route, so this route does not justify a
production row.

## Ceiling caveat

G111's 147/220 (66.8 percent) is only per-frame geometric visibility through
four paint corners, not a solved homography. Even a future perfectly scored
corner detector could reach four constraints only on that visibility subset,
and a solver would still require held-out real-world distance validation.

## NOT VERIFIED

- Corner-detection recall, per-role recall, Wilson intervals, or comparison to
  the line route: the committed G111 visibility labels lack localisation
  targets and this row was not permitted to relabel them.
- Precision, role assignment, or robustness of the local proposal set; the
  render check shows obvious non-court responses.
- Any homography, `court_feet` declaration, coordinate contract, downstream
  tracking change, production integration, pod copy, or deployment.
- Generalisation beyond G111's committed 11-clip basketball corpus.

## Verifier self-check

- **A7:** every evidence path named by this memo exists at report time:
  `g119_corners/protocol.md`, `proposals.csv`, `validation.json`,
  `score_blocker.txt`, and the 44-file `renders/` directory.
- **B1 circular metric:** clear. No success count was calculated; all 616
  named visible-role units are retained, and the missing location is explicit.
- **B2 non-additive schema:** clear. Only additive G119 evidence artifacts and
  an evidence script/test were added; no production field or reader changed.
- **B3 fall-through loss / B4 re-claim loop:** clear. The score is an explicit
  `NOT_VALIDATED` artifact, not a gate or claim-state change.
- **B5 pre-verification deploy:** clear. No pod or deployed file was written.
- **B6 orphans:** clear. No module, import, command, or test was moved or
  retired.
- **B7 head-slice evidence:** clear. Raw proposals cover all 220 fixed
  temporally stratified G111 rows; the 44 diagnostics use four spread slots
  from every clip.
- **B8 self-fit as independent:** clear. A local response was not accepted as
  a target. Missing target coordinates cause a fail-closed result.
- **B9 degenerate denominator:** clear. The role denominator is 616 named
  visible physical-corner roles from 220 unique G111 frame keys, not recycled
  tracker identifiers.
- **B10 moved bar:** clear. No existing line-route parameter, harness
  threshold, coordinate contract, or rung-ladder value changed. The new
  proposal parameters and 16-pixel rule were written before execution.
