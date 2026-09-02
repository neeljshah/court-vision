# G75 basketball paint role assignment

**Verdict: NOT VALIDATED.** The corrected G76 blind re-labelling result is
`paint_solvable_share = 0.5732`, Wilson 95% `[0.5491, 0.5968]`, which is 5.7x
the pre-registered 0.10 rule. Raw agreement was only 83/121 (68.6%), so this
decision is robust but its point estimate is not; no G75 behavior depends on
the exact share.

## Scope and rule

This row only adds image-line role assignment. It emits no coordinates, never
calls `solve_from_lines`, does not validate against an independent landmark,
and persists neither a homography nor a sidecar. That preserves the deliberate
per-frame fail-closed boundary required after G42's stale-homography output
inflation.

The rule first forms two approximately parallel line pairs. It uses each
candidate's observed endpoint extent, not a cross-ratio: the transverse line
that extends beyond both lane intersections is labelled `baseline`; the one
that ends at the lane intersections is `free_throw`. The two lines that span
between those transverse intersections are the lane candidates. `lane_low`
versus `lane_high` is an explicit caller declaration (`left` or `right` image
side), because image pixels cannot safely infer court orientation. The caller
also declares `league` as `nba_wnba` or `ncaa_legacy`; it is never inferred.

This follows calibration strategy section 1.2's orientation-then-termination
recommendation. It deliberately does not use pure cross-ratio matching, which
the strategy says is weak when only two or three lines per direction are seen.

## Attempted held-out evaluation

`sample_manifest.csv` selects 45 existing G68 `PAINT_SOLVABLE` tiles, evenly
spaced across each source clip's solvable rows: 15 tune tiles and 30 held-out
tiles, with clips disjoint between the splits. `per_frame_assignments.csv`
records every result. Of the held-out tiles, 23 produced no assignment and 7
produced a four-line hypothesis.

The required eye check was performed on the 12 held-out renders enumerated in
`eye_check.csv`. Every emitted hypothesis in that check was wrong: it confused
paint roles with broadcast graphics, court borders, a basket/shot-clock
structure, a midcourt graphic, or close-up background edges. The remaining
checked frames emitted nothing. A lane-low/lane-high swap is therefore not the
limiting failure in this attempt; the selected structure itself is wrong.

No 40-frame hand-labelled candidate-role set existed in G68: its labels only
record `PAINT_SOLVABLE`, not which candidate group is each physical role.
Creating candidate-role labels after seeing these predictions would be
circular. Consequently, per-role accuracy and the naive image-position score
are **NOT VALIDATED**, rather than fabricated. Plainly, termination structure
does not beat the naive image-position baseline in this attempt: it generated
no valid held-out role map. A scored comparison requires a separately created,
blind candidate-role label set.

## Durability and verifier self-check

- Evidence paths present: `g75_role_assignment/sample_manifest.csv`,
  `g75_role_assignment/per_frame_assignments.csv`,
  `g75_role_assignment/candidate_previews/`,
  `g75_role_assignment/renders/`, and `g75_role_assignment/eye_check.csv`.
- A7: all paths above exist at report time. There are no named missing paths.
- B1: no headline metric is calculated; the absent hand-role labels are named.
- B2-B6: this adds APIs only; no schema, reader, gate, deployment, producer,
  tracking row, or persistence behavior changed.
- B7: samples are evenly spaced across every source clip, not a head slice.
- B8: no residual is offered as validation. B9: no recycled denominator is
  used. B10: no threshold or gate was changed.

## Not verified

- Per-role accuracy on 40 or more hand-labelled candidate-role frames.
- A numeric naive-position baseline comparison.
- Lane-low/lane-high semantic orientation without a caller declaration.
- Any independent landmark validation, coordinate output, homography solve, or
  persistence behavior.
