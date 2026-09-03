# G138 paint role assigner: before measurement

## Verdict

**NOT VALIDATED for a paint-line solve handoff.** On a seeded 21-frame subset
of G137's fixed 42 four-role claims (seed `137092026`), none of the 84 claimed
role assignments follows the physical paint role named by the assigner. This
is a correctness result, not a claim-rate result. The G137 `42/215` figure is
only the frequency of complete role claims and is not a reachability measure.

The only role available from the unchanged G134 stable groups in this review
is a free-throw line on one wide frame; it was assigned as `lane_left` instead.
The available-minus-correct gap is therefore **1 - 0 = 1 role** across the 84
reviewed role units. On this set, changing the assigner alone has almost no
available input to recover, although it would stop false complete hypotheses.

## Locked decision set and eye review

The complete decision set is G137's 42 rows in
[`g137_scale/qualifying_frames.csv`](g137_scale/qualifying_frames.csv). Before
viewing G138 renders, [`g138_assigner/review_protocol.md`](g138_assigner/review_protocol.md)
fixed the visual criteria and [`g138_assigner/review_selection.csv`](g138_assigner/review_selection.csv)
fixed a 21-row subset using `random.Random(137092026).sample` from lexical
`(clip, frame_index)` order. It is not a head slice: it spans 15 of the 18
source clips and G137 strata 1 through 11. Every selected source frame was
reconstructed read-only using G137's unchanged call chain. Every reviewed
frame is committed under [`g138_assigner/renders/`](g138_assigner/renders/),
with the claimed roles in colour and all G134 stable groups in thin grey.
The aggregate review is in [`g138_assigner/role_review.csv`](g138_assigner/role_review.csv),
with per-frame counts in [`g138_assigner/frame_review_summary.csv`](g138_assigner/frame_review_summary.csv).

`claimed_correct` requires that the coloured assigned group visibly follows
the named physical paint line. `available_from_stable_groups` is independent:
the named physical line must be visibly discernible and followed by any
thin-grey stable group, whether or not the assigner chose it. Thus an observed
line assigned the wrong role is available but not correct; missing or
undiscernible evidence is not counted as a failure of the detector.

## Claimed correctness and available lines

| role | correct claimed roles | Wilson 95 pct | available stable roles | available minus correct |
|---|---:|---:|---:|---:|
| baseline | 0/21 | [0.00, 15.46] pct | 0/21 | 0 |
| free_throw | 0/21 | [0.00, 15.46] pct | 1/21 | 1 |
| lane_left | 0/21 | [0.00, 15.46] pct | 0/21 | 0 |
| lane_right | 0/21 | [0.00, 15.46] pct | 0/21 | 0 |
| all claimed role units | 0/84 | [0.00, 4.37] pct | 1/84 | 1 |

The exact recomputable values, including Wilson intervals for availability,
are in [`g138_assigner/role_summary.csv`](g138_assigner/role_summary.csv).
The complete stable-group geometry for every rendered frame is in
[`g138_assigner/stable_group_geometry.csv`](g138_assigner/stable_group_geometry.csv).

The one available role is rank 11:
`ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss`, frame `14543`, stratum 6.
Stable group 0 follows the discernible free-throw line, while the assigner
reported it as `lane_left`. The other wide views had no stable group that
could be identified as the named paint role under the locked protocol; the
remaining selected frames are close-up, crowd, bench, interview, or graphic
views in which the paint role was not in view or not discernible. This pattern
confirms G137's five-frame rejection rather than converting a detector claim
into a line correspondence.

## What the assigner actually does

G75 added `assign_paint_roles` in commit `2f27a5d51`. Its complete-set gate is
literal:

```python
if len(candidates) < 4:
    return None
...
if best is None:
    return None
```

Between those returns it searches every pair of proposed transverse lines and
every pair of remaining lane lines. Only a pair-of-pairs whose parallel and
orthogonal scores pass can become `best`; it then returns all four fields in
one operation:

```python
return {
    "baseline": baseline,
    "free_throw": free_throw,
    "lane_low": lane_low,
    "lane_high": lane_high,
}
```

G137's wrapper preserves that all-or-none result:

```python
assigned = assign_paint_roles(stable, league, "left")
if assigned is None:
    return {role: None for role in ROLES}
```

It then maps the complete `lane_low`/`lane_high` result to G137's
`lane_left`/`lane_right` fields. There is no partial return and no fallback
that fills missing roles from another result. The named cause is therefore a
**geometric solve that returns only on a complete four-line set**, with an
explicit fewer-than-four hard gate. Its false complete maps are not evidence
of fabricated missing roles; they are full geometrical hypotheses assembled
from unrelated stable candidates.

## Recommendation (not implemented)

Do not alter the assigner in this row. A future preregistered change should
emit independently scored partial role observations with each role's candidate
identity and confidence, rather than manufacture a complete map before any
role can be inspected. G137's claim counter and a future G135 solve handoff
could consume such observations differently: the counter can measure partial
role availability, while `solve_from_lines` must remain fail-closed and accept
only four high-confidence, independently verified roles. Partial observations
would otherwise be diagnostic artifacts for review, error taxonomy, and new
candidate-quality measurement; they must not be treated as a homography input.

## Verifier-contract self-check

- A1: no code or test was added in G138, so there is no G138 per-file test to
  re-run. The work is evidence-only and leaves runtime files untouched.
- A2: the CSV recomputation independently gives 21 unique selected frames, 84
  unique `(clip, frame_index, role)` units, zero correct claims, one available
  role, and the tabled Wilson intervals.
- A3: the seeded subset was fixed before review, spans 13 clips and strata
  1-11, and is not a head slice; every selected render was inspected.
- A4: `role_review.csv` has exactly one row for each of 21 frame identities
  times four roles; no frame or role denominator is recycled.
- A5: no existing code, schema, or reader changed. New CSV artifacts are
  evidence-only and have no production readers.
- A6: this lane commits only explicit G138 evidence paths in the `a2`
  worktree. Landing to master is verifier work and is not performed here.
- A7: all paths named in this memo exist at this self-check, including the
  complete render directory and every CSV artifact.
- B1: all fixed selected identities are named before review; none was removed
  because it lacked a visible line or a correct claim.
- B2-B6: no existing field, reader, gate, lifecycle, pod file, deployment,
  module, import, caller, flag, or coordinate contract changed.
- B7: the fixed seeded selection is cross-clip and cross-stratum, not a head
  slice. B8: no fitted residual or solve claim is presented. B9: the unit is a
  unique claimed frame-role. B10: detector parameters, G134 grouping, G137
  sample and seed, thresholds, line calibration, and coordinate contract are
  untouched.

## Not verified

- Correctness or availability outside G137's 42 claimed frames.
- A modified partial-role assigner, its confidence calibration, or a
  before/after comparison.
- A four-line correspondence, homography, coordinate output, reprojection, or
  external court-distance validation.
