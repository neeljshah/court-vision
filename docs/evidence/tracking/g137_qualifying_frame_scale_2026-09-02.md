# G137: qualifying-frame scale

## Result

On a seeded draw of 216 frames from all 18 basketball pod clips, one named
source frame was unreadable through both seek and sequential decoding. The
count denominator is therefore the remaining **215** decodable frames. The
unchanged G134 stable-grouping plus union path made an all-four-role claim on
**42/215 = 19.53%** of frames, Wilson 95% **[14.79%, 25.35%]**.

This is a detector-claim rate, not a verified paint-line rate. The required
five-frame eye check rejected every selected claim, so none is handed to G135's
solve attempt. Treating those frames as correspondence sets would chase noise.
No solve, calibration, coordinate claim, or `court_feet` declaration occurred.

## Fixed seeded sample

The seed is `137092026`. For each clip, one random index was drawn from each
of 12 equal temporal strata, not from a head slice. The complete draw and
per-clip allocation are in [`sample_manifest.csv`](g137_scale/sample_manifest.csv)
and [`per_clip_counts.csv`](g137_scale/per_clip_counts.csv): each of the 18
clips has 12 drawn frames (216 total). The metric uses 11 frames for
`ncaa_basketball__ncaa_basketball_IB-_u4gW3ds` and 12 for every other clip;
[`unreadable_sample_frames.csv`](g137_scale/unreadable_sample_frames.csv)
names its stratum-11 frame `28850` and the decode reason. It was not scored as
zero roles or silently removed.

The sample has **zero G84 overlap**. Thus the old frozen, PAINT_SOLVABLE-selected
G84 slice remains a separate comparison: G135 saw 0/30 qualifying frames, and
the reference independence model stated 3.79% with P(0 in 30) = 0.321.

## Role-claim distribution and independence

| claimed roles detected | frames |
|---:|---:|
| 0 | 173 |
| 1 | 0 |
| 2 | 0 |
| 3 | 0 |
| 4 | 42 |

The raw per-role and per-frame records are in
[`frame_role_claims.csv`](g137_scale/frame_role_claims.csv) and
[`frame_joint_distribution.csv`](g137_scale/frame_joint_distribution.csv).
The observed 19.53% claim rate is above the 3.79% independent-line reference,
but that is **not evidence of positive physical-line correlation**. The existing
`assign_paint_roles` function returns a complete four-role hypothesis or
`None`; it cannot emit one, two, or three roles. The apparent 0/4 bimodality is
therefore structurally imposed by role assignment, so this call chain cannot
test the independence assumption empirically.

## Eye check and solver handoff

The five lexical-evenly-spaced positions across the 42 qualifying claims were
rendered and inspected. Their exact selection and decisions are in
[`eye_check.csv`](g137_scale/eye_check.csv); each corresponding render is named
there and exists in [`g137_scale/renders/`](g137_scale/renders/). All five are
REJECT: four are player/crowd close-ups and the remaining wide view lacks four
correctly assigned physical paint lines. [`forwarded_for_solve.csv`](g137_scale/forwarded_for_solve.csv)
records each rejected candidate as `blocked_false_role_claim`, not as a solver
input.

No hand labels were added to compute the count. A frame counted as qualifying
only means the detector claimed four roles; it does not mean those roles are
correct. The eye check demonstrates why the distinction matters here.

## Reproduction

```text
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g137_qualifying_frame_scale --sample
conda run --no-capture-output -n basketball_ai python -m scripts.platformkit.g137_qualifying_frame_scale --write
conda run --no-capture-output -n basketball_ai python -m pytest tests/evidence/tracking/test_g137_qualifying_frame_scale.py -q
```

The source access is read-only. The implementation reuses G134's 28px LSD,
union, and immutable 5-degree/10px grouping unchanged; it does not edit
`line_calibration.py`, the G84 sample, G115 marks, frozen protocol, thresholds,
or the coordinate contract.

## Verifier-contract self-check

- A2: independently parsed the role CSV: 860 unique `(clip, frame, role)`
  rows over 215 unique frames, 42 qualifiers, rate 0.195349, Wilson
  [0.147897, 0.253496].
- A3: rendered and inspected five evenly spaced qualifier positions, not a
  head slice.
- A4: role and frame units are unique; the one named unavailable source frame
  is outside the decode-only metric denominator rather than recycled or scored.
- A5: only new G137 module, test, and evidence fields were added; no existing
  reader or schema changed.
- A7: all memo-named G137 evidence paths exist at this self-check.
- B1: all 216 drawn identities are named in the manifest. The sole excluded
  metric input is named with an input-decode reason, not a detection outcome.
- B2-B6: no existing schema, reader, gate, lifecycle, pod deployment, module
  move, caller, or flag changed.
- B7: eye-check selection spans the complete ordered qualifier set.
- B8: no same-input residual or solve claim is presented.
- B9: frames and frame-role records are unique, non-recycled metric units.
- B10: detector, union, grouping, protocol, sample seed, hand marks,
  calibration module, coordinate contract, and thresholds are unchanged.

## Not verified

- A verified all-four physical-paint-line frame on this sample.
- An empirical line co-occurrence distribution independent of the all-or-none
  role-assignment implementation.
- A frame solve, external distance validation, reprojection, or court-feet
  calibration.

## Verdict

**NOT VALIDATED for a solve handoff.** The adequately sized detector-claim
count is complete, but the evenly distributed eye check shows the claimed
four-role frames are not valid physical paint-line correspondences.
