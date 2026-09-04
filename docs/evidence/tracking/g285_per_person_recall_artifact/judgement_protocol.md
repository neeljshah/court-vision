# G285 fixed judgement protocol

This protocol is written before any G285 marker render is reviewed.

## Fixed unit and order

The unit is one of G284's sealed visible on-court player slots, not a marker
count and not a newly counted person.  The review order is G284's ascending
`blind_id` order after excluding its seven `CANNOT_COUNT` rows.  Each frame has
exactly the number of player slots sealed in
`g284_detector_recall_bound_artifact/per_frame_join.csv`.
Within a frame, slots are assigned in visually judged left-to-right footpoint
order; ties are broken by top-to-bottom image order.  This creates a stable
audit handle for the pre-sealed slots and does not change their count.

## Marker and matching policy

Each finite G267 footpoint satisfying G270's unchanged inclusive court
rectangle is rendered as a magenta filled circle with a one-pixel black outline
and a seven-pixel radius.  No label, rectangle, crop boundary, inferred box, or
other annotation is drawn.

A player slot is `MATCHED` only when the centre of one rendered marker is on
that visible player's feet or is visually within 25 source-image pixels of
them.  Otherwise it is `UNMATCHED`.  The 25-pixel radius is fixed before
review, is a coarse eye-judgement convention rather than a calibrated geometry
threshold, and will not be tuned after review.  A verdict is marked
`near_boundary=YES` when the labeller judges the marker-to-feet separation to
be approximately 20--30 pixels; all other verdicts receive `NO`.  A marker can
match at most one player slot. More than one marker may land on the same player;
each such marker remains a marker on a visible person, while that player still
contributes one `MATCHED` per-person verdict.

Each rendered marker is also judged separately: `MATCHED` if assigned to a
sealed player slot under that same rule and `UNMATCHED` if it is on no visible
on-court player.  The latter are reported as detector-box observations, with
their own marker denominator.
