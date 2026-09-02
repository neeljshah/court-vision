# G112 alternative-footage reachability protocol

This protocol was fixed before candidate-video acquisition and frame review. It
extends the G101/G104/G106 eye-judged visibility method without changing any
threshold, coordinate declaration, or solver.

## Candidate eligibility

A candidate source type is obtained only when a plain public video URL can be
read without an account, subscription, cookie, token, or organizer-issued
share link. Exactly one example may be obtained for each such source type.
The existing bridge's local `download_local()` mechanism may acquire a bounded
section only with a deliberately nonexistent cookie path and with no pod upload
or tracking call. A source requiring a credential or share token is recorded as
not obtained with its acquisition requirement; it is never bypassed.

## Fixed sample selection

For each obtained example, seed is `1122026`. Decode the acquired bounded
example and draw one frame uniformly with Python's `random.Random(1122026)`
from each of 20 equal, disjoint temporal strata. A stratum's integer interval
is `[floor(i*N/20), floor((i+1)*N/20))`; its selected frame is
`rng.randrange(start, stop)`. All 20 draws, including close-ups, cuts, blank,
or non-game frames, stay in the denominator. The unit is the unique
`(candidate_id, source_frame)` pair.

## Visibility and constraint labels

Points are counted only when a physical feature is visibly discernible and can
be assigned its named field identity without inferring an off-frame feature.
Straight lines are counted only when a continuous painted portion is visibly
traceable and has a defensible semantic identity. Parallel/repeated segments
are one direction family, never multiple independent constraints.

- Soccer: G101 named pitch lines and `lengthwise`/`crosswise` direction
  families. Named points are defensible intersections/corners of those same
  markings; a circle arc is not a straight direction.
- Football: G106 field-family direction mapping. Yard stripes, hashes, goal
  lines, and end lines are crossfield; sidelines are lengthwise. Repeated paint
  and anonymous intersections have no asserted absolute-yard identity. A named
  absolute point requires a visible goal/end corner or pylon; the count cannot
  be manufactured from periodic yard paint.
- Baseball: G104 named points are home plate, first, second, and third base,
  plus the pitching rubber. Only visibly straight foul lines add directions;
  the dirt arc does not.

`independent_direction_count` is the number of non-empty canonical direction
families, not raw segment count. `points_ge_4` is true only for four or more
named, visibly discernible point correspondences. A candidate clears the
four-constraint requirement only when at least one reviewed frame has either
four named point correspondences or four independent line-direction families;
for football it also requires an unambiguous absolute-yard anchor under G106.

## Evidence and review

Every selected frame is written as an annotated render with immutable candidate
ID, source frame, stratum, named points, named lines, and direction count. The
per-frame CSV is the primary additive record. Its summary must recompute the
20-row distribution and uniqueness count without excluding any row.
