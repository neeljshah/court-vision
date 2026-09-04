# G269 preregistration: fixed physical reassociation measurement

Status: sealed before baseline reproduction and reassociation scoring.

## Question and fixed input

This is a post-hoc headroom measurement, not a proposed tracker or production
change. It will reuse, without decoding, detection, map, relabelling, or
refitting, G267's retained artifact:
`docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json`.
The input population is every retained finite class-0 detector-box footpoint in
source frames 19599 through 23399 inclusive. Detector boxes can include
officials, bench personnel, spectators, and duplicates; they are not
authenticated players.

## Fixed constraint and scoring

The sole speed constraint is strictly greater than 40.0 ft/s for an
implausible step, identical to G267's descriptive reference. It is a generous,
uncontroversial reference for this measurement, not a production threshold or
performance bar. No other limit will be tested or swept. The baseline will be
recomputed from the retained frame records using G267's exact analysis before
any post-hoc reassociation result is reported.

## Deterministic post-hoc algorithm

Process retained finite detector-box footpoints in ascending source-frame order.
Maintain each reassociated track's most recent box. At a frame, construct one
candidate edge from each current box to each prior reassociated track whose
last box is earlier and whose court-space speed, using the actual frame gap,
is at most 40.0 ft/s. Choose a one-to-one assignment that first maximizes the
number of feasible candidate edges and then minimizes the sum of each chosen
edge's distance divided by its permitted distance. Resolve an exactly equal
assignment deterministically by ascending prior track id and detector-box
index. Each unmatched current box starts one new reassociated track; no
detection is dropped or left without a reassociated id. Tracks have no
appearance, team, image, detector-confidence, original-id, or future-frame
input, and no track is retired by a second unstated distance or time limit.

The full report will give, before and after, the strict-over-40-ft/s step
fraction, emitted/reassociated ID count, track-length median/p90/maximum, and
unassociated detector-box count. A lower fraction accompanied by an increased
ID count or collapsed track lengths is fragmentation, not improvement.

## Limits fixed before scoring

There is no identity ground truth. A physically plausible reassociation can
still connect the wrong person or non-person box. This is one clip, one shot,
one arena, one G233d map, and one non-deterministic detector draw; the map is
only certified to about 20 px. Results will be reported to three decimals.

SHA256 (LF bytes above this line): 5391eeb4838a5f57897c3af002b0e407e48dc7cb6f34990af64ab0e4ee78220f
