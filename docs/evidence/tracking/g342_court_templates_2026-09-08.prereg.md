# G342 Preregistration: court-template synthetic validation

Date: 2026-09-08

This preregistration controls the later finisher-only synthetic measurement. It is sealed before any scored comparison.

- Seed: `34220260908` for NumPy `default_rng`.
- Population: exactly 200 independently sampled camera-like homographies for each of NBA, WNBA, FIBA, and NCAA in each arm.
- Image: 1280 x 720 pixels. Court-space camera target pan is uniformly sampled from x=[0.35L,0.65L], y=[0.35W,0.65W]; tilt is uniformly sampled from -18 to 18 degrees; focal proxy is uniformly sampled from 900 to 1600 pixels; projective terms are sampled symmetrically in [-0.00035,0.00035]. Reject and redraw a homography unless all four court corners are finite and at least two-thirds of their convex hull is within the image.
- Observations: sample every rendered stroke, add independent Gaussian coordinate noise with sigma uniformly sampled in [1,3] pixels, then remove one independently selected contiguous 30 percent interval of each stroke's arc-length parameterization.
- Arm A: score the true template with its generating homography. For each non-true template, use the best cost from 50 seeded random re-fits drawn from the same camera distribution, with the full observed segment set and equal 50-candidate budget per wrong hypothesis.
- Arm B: apply independent uniform corner jitter in [-2,2] pixels to the Arm A candidate homography before scoring; it is reported but is not gated.
- Selector rule: compatible-family median symmetric distance normalized by visible supported stroke length plus a missing-support penalty for predicted-visible strokes with no observed support within 4 pixels. Return a named winner only when its cost is at most 0.8 times runner-up on at least 5 frames from at least 2 shots, at least 2 of arc radius, lane width, court length, and corner straight favor it, and the same winner appears in at least 90 of 100 frame bootstraps. Otherwise return UNKNOWN with the plausible set. A quadrilateral-only input must assert rather than identify a template.
- Arm A bar: per true template, outright true winner rate >= 0.95 and wrong-winner share <= 0.02; n=200. Arm B has no pass bar.
- Reporting: write 4 by 5 confusion matrices with zero-padded integer cells and pairwise outright-win counts for NBA-WNBA, NBA-FIBA, and NBA-NCAA. No score or comparison will be computed before this seal is committed.

SEAL sha256 f7699cf7f70b9869aac74f47da74bc84dae8ec7eef0b0a9689c322e61c7d3482
