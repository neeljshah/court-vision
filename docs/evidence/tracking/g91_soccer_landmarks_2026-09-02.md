# G91 soccer canonical-landmark visibility census

**Verdict: CLOSED AT LIMIT (step 1 measurement).** This memo follows
[`VERIFIER_CONTRACT.md`](VERIFIER_CONTRACT.md), including A7 and the B1-B10
self-check below. The measured five-landmark precondition is absent in the
whole seeded decision set, so G91 stops before step 2. No detector, solver,
coordinate contract, threshold, or existing verdict changed.

## Premise reproduced before measurement

At worktree revision `e9f807b1c598e677eec5125b6bab6f2571c24cf3`,
`domains/soccer/tracking/keypoints.py` has one named provider output path:
`center_circle`. `domains/soccer/tracking/geometry.py` retains
`MIN_LANDMARKS = 5` and retains `MAX_HELDOUT_ERROR_M = 2.0`. Thus the stated
one-name versus five-name arithmetic blocker remains present. The one new
focused regression, `tests/domains/soccer/test_g91_keypoint_capacity.py`,
locks that baseline and passed: `1 passed in 1.13s`.

## Method and durable artifacts

The five source clips were read from the pod only. They were pulled without
writing to the pod or changing any pod process, then decoded locally with
Python 3.10.0 and OpenCV 4.11.0. The source-frame selection uses global seed
`9102026`: exactly one uniform pseudorandom draw from each of 20 equal-sized
temporal strata in every clip. This gives 20 frames per clip, 100 total,
without a head slice. The exact frame indices, decoded dimensions, and source
frame counts are in
[`g91_soccer_landmarks/sample_manifest.json`](g91_soccer_landmarks/sample_manifest.json).

Every selected frame was visually reviewed. A point counts only when its
marking intersection is visibly discernible inside the frame. A full centre
circle contributes its three canonical points; a penalty-box view whose two
front corners are visible contributes two. Goal-line endpoints outside the
frame or not discernible are not counted. The 100 per-frame judgments are in
[`g91_soccer_landmarks/frame_labels.csv`](g91_soccer_landmarks/frame_labels.csv)
and [`g91_soccer_landmarks/frame_labels.json`](g91_soccer_landmarks/frame_labels.json).
The 100 frame renders and five 20-frame contact sheets are under
[`g91_soccer_landmarks/renders/`](g91_soccer_landmarks/renders/). The contact
sheets cover every decision-set frame; the individual renders retain source
frame and stratum identifiers for re-checking.

## Recomputed result

| Clip | n | visible >=3 | visible >=4 | visible >=5 |
|---|---:|---:|---:|---:|
| `soccer__soccer_AgspyOj5BPk.mp4` | 20 | 7 | 0 | 0 |
| `soccer__soccer_DdnvC6-PGYY.mp4` | 20 | 6 | 0 | 0 |
| `soccer__soccer_EKhrdU9bVZA.mp4` | 20 | 3 | 0 | 0 |
| `soccer__soccer_cKXZysISV4w.mp4` | 20 | 6 | 0 | 0 |
| `soccer__soccer_kSgNjoaqCpI_1080p.mp4` | 20 | 12 | 0 | 0 |
| **Pooled** | **100** | **34 (0.340, Wilson 95% [0.255, 0.437])** | **0 (0.000, [0.000, 0.037])** | **0 (0.000, [0.000, 0.037])** |

The headline counts were independently recomputed from the label artifact:
100 unique `(clip, source_frame)` pairs; 34, 0, and 0 frames at the three
cutoffs respectively. The denominator is every sampled decoded frame. No
frame was excluded for shot type, detector result, or visibility outcome.

## Decision

Five visible canonical landmarks are not commonly available here: the observed
share is 0/100. Under the G91 instruction, that makes five the wrong currently
reachable gate for this broadcast framing measurement and requires stopping at
step 1. Accordingly, the penalty-box provider was not implemented, and the
existing homography path remains untouched.

`detect() >= 5 named landmarks` and the held-out real-world distance error are
**NOT APPLICABLE**: no step-2 detector was built or scored. No claim is made
about a court-feet promotion, a homography solve rate, or an external distance
accuracy. The expected real-pitch dimensional variation caveat therefore does
not arise in this step-1-only result.

## NOT VERIFIED

- A role-identified penalty-box detector has not been built or evaluated.
- The fraction of frames where a detector returns five named landmarks is not
  measured.
- No homography, leave-one-out check, temporal calibration update, or
  independent real-world-distance error was produced.
- No soccer clip may declare `court_feet` from this result.

## Verifier self-check

- **A7:** every evidence path named above exists in this worktree at memo time.
- **B1:** all 100 sampled decoded frames remain in every denominator.
- **B2:** no schema, field, or reader changed.
- **B3/B4:** no gate or claim path changed.
- **B5:** the pod was read-only; no file was deployed or copied to it.
- **B6:** no production module was moved or retired.
- **B7:** one seeded sample from each temporal twentieth of every clip was
  rendered and visually checked.
- **B8:** this is a human visibility census, not a fit residual or self-fit
  validation.
- **B9:** each unit is one unique `(clip, source_frame)` pair.
- **B10:** `MIN_LANDMARKS`, `MAX_HELDOUT_ERROR_M`, coordinate contract, and
  every harness threshold are unchanged.
