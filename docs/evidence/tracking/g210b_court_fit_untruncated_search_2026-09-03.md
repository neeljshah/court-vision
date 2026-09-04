# G210b untruncated court-fit search

## Verdict

**The fixed untruncated full-pool sampler scores 0 / 17 frames with all four
held-out paint corners within 12 native pixels.** Its per-corner native-pixel
error is min / median / p90 / max **12.794 / 409.726 / 874.007 / 1091.839**.
The same invocation's label-only oracle control is **1 / 17**, with median
per-frame maximum corner error **28.841 px**, reproducing the reviewer's
reported 1 / 17 and about-27-px ceiling.

This settles the narrow, important point that G210's `MAX_GROUPS=24` cap was
not defensible: the full detector set contains the oracle-selected paint
groups on all 17 frames. It does **not** vindicate the classical route. The
oracle ceiling is still only 1 / 17. It also does not establish that removing
the cap alone reaches the oracle: although every oracle quartet is in the
real fit's group pool, none of the 16,384 uniform real-search draws contained
its four groups. Thus the 0 / 17 result is a valid measurement of this fixed
untruncated sampler, and specifically attributes its remaining limitation to
search coverage rather than a group cap. It must not be read as an exhaustive
global-classical-fit verdict.

This was a local CPU-only measurement over 17 existing JPEGs. There were no
downloads, weights, training, build activity, pod activity, daemon activity,
production-code edits, or corpus changes.

## Fixed pieces and held-out boundary

Nothing in the accepted court contract moved. Coordinates remain 94 by 50 ft
with 19-ft paint depth, NCAA 12-ft lanes, WNBA 16-ft lanes, and the same
near-paint corner model from G196/G210. The sport is derived before fitting
from the unchanged `wnba__` audit-ID prefix rule; the construct has eight NCAA
and nine WNBA frames. The image-to-court model is inverse-projected into each
source's native pixels and passed to G205's unchanged `score_frame` with its
unchanged 12-px protocol.

`fit_image(image, sport)` accepts only image pixels and declared sport. It
loads all detected stable groups with no `MAX_GROUPS` slice, samples only from
those pixels-derived groups, and ranks candidates by global support over that
same complete group list. It has no target, role, coordinate, or oracle
parameter. In `run`, all 17 real fits are completed and written to
[fit records](g210b_court_fit_untruncated_search_artifact/fit_records.json)
before target rows are read. Labels then reach only (1) the unchanged G205
scorer and (2) the separately named `oracle_fit` control. They never seed,
filter, reject, rank, or render a real-fit hypothesis.

## Full-set search accounting

The detector path is G205/G210 unchanged: raw and CIELAB-CLAHE LSD at a 28-px
minimum segment length; additive 1-px union; and stable grouping at 5 degrees
and 10 px. No group-length, position, orientation, color, court-shape, or
label-derived prefilter is applied. The actual full group counts range from
82 to 900.

For a frame with `n` groups, the distinguishable configuration count is
`C(n,4) * 6 * 12 * 12`: choose four groups, partition them into ordered
transverse/longitudinal image pairs (six ways), then choose an ordered pair
from the four transverse and four longitudinal model lines (12 each). This is
the same 9,180,864 configurations at `n=24` cited in the retraction. G210b
draws 16,384 deterministic, uniform configurations per frame (seed 210),
eight times G210's 2,048 budget, but from the complete detected group set.

The resulting per-frame spaces span 1,511,187,840 to 23,462,456,565,600;
their total is 131,677,907,436,576. The real sampled fraction spans
`6.983e-10` to `1.084e-5` (median `2.348e-9`). This is deliberately reported
because it is decisive: full-pool membership fixes the G210 truncation defect,
but uniform sampling cannot provide material coverage of the untruncated
combinatorial space. It is not called exhaustive or adequate coverage.

The labels-only oracle chooses, for each true boundary, the full-set group
whose fitted line has the smallest mean absolute residual at the boundary's
two labelled endpoints. Its selected group indices and residuals are in the
per-frame artifact. All four selected groups are in the uncapped real pool in
all **17 / 17** frames, as required by the absence of a cap. A post-run,
label-only replay of the real deterministic draws found that **0 / 17** draws
contained all four selected oracle group indices; that confirms the remaining
search-coverage limitation without altering the real fit.

## Results on the exhaustive 17-frame construct

Error order is baseline-left, baseline-right, free-throw-left,
free-throw-right. All errors are G205 scorer nearest-proposal distances in
native pixels. The full machine-readable audit is
[per-frame CSV](g210b_court_fit_untruncated_search_artifact/per_frame.csv),
with real and oracle target rows kept separately in
[real scores](g210b_court_fit_untruncated_search_artifact/target_scores.csv)
and [oracle scores](g210b_court_fit_untruncated_search_artifact/oracle_target_scores.csv).

| Audit ID | League | Groups | Sampled fraction | Held-out errors px | All four <=12 px |
|---|---|---:|---:|---|---|
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973` | NCAA | 832 | 9.567e-10 | [67.152, 611.144, 32.111, 664.813] | no |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785` | NCAA | 657 | 2.465e-9 | [578.029, 730.598, 702.788, 864.085] | no |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171` | NCAA | 82 | 1.084e-5 | [16.539, 54.864, 33.806, 44.186] | no |
| `ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871` | NCAA | 900 | 6.983e-10 | [633.677, 264.687, 547.423, 18.479] | no |
| `ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925` | NCAA | 336 | 3.635e-8 | [479.307, 409.785, 187.159, 121.302] | no |
| `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920` | NCAA | 334 | 3.724e-8 | [337.664, 432.809, 128.970, 206.050] | no |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760` | NCAA | 726 | 1.652e-9 | [914.653, 849.231, 770.325, 923.365] | no |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340` | NCAA | 617 | 3.171e-9 | [1082.362, 1091.839, 342.472, 374.378] | no |
| `wnba__wnba_01_1080p__s01__f001600` | WNBA | 729 | 1.625e-9 | [95.721, 153.413, 384.681, 468.294] | no |
| `wnba__wnba_01_1080p__s03__f004062` | WNBA | 647 | 2.621e-9 | [12.794, 153.130, 409.667, 394.168] | no |
| `wnba__wnba_01_1080p__s06__f007539` | WNBA | 665 | 2.348e-9 | [904.829, 872.985, 246.665, 157.250] | no |
| `wnba__wnba_02__s11__f021983` | WNBA | 374 | 2.364e-8 | [115.956, 773.174, 251.333, 860.833] | no |
| `wnba__wnba_04__s06__f012223` | WNBA | 499 | 7.429e-9 | [421.908, 227.739, 362.113, 228.621] | no |
| `wnba__wnba_06__s03__f007237` | WNBA | 681 | 2.135e-9 | [897.457, 876.392, 168.153, 151.379] | no |
| `wnba__wnba_06__s07__f014099` | WNBA | 727 | 1.643e-9 | [788.752, 626.309, 525.640, 340.898] | no |
| `wnba__wnba_06__s09__f018997` | WNBA | 671 | 2.265e-9 | [840.715, 703.424, 510.381, 390.763] | no |
| `wnba__wnba_07__s08__f016801` | WNBA | 835 | 9.430e-10 | [729.768, 581.865, 500.961, 301.032] | no |

| Role | Min px | Median px | p90 px | Max px |
|---|---:|---:|---:|---:|
| Baseline left | 12.794 | 578.029 | 908.759 | 1082.362 |
| Baseline right | 54.864 | 611.144 | 874.348 | 1091.839 |
| Free-throw left | 32.111 | 362.113 | 609.569 | 770.325 |
| Free-throw right | 18.479 | 340.898 | 862.134 | 923.365 |

## Oracle control

The oracle is not a real-fit result and is never used to pick a real model.
It fixes the court correspondence to near baseline, near free throw, left
lane, and right lane, then supplies the nearest labelled-line group from the
untruncated detector set. It scores **1 / 17** at the same 12-px all-four
rule. Its four-corner distribution is min / median / p90 / max **2.234 /
18.126 / 33.230 / 92.774 px** and its per-frame maximum-error median is
**28.841 px**. The small difference from the reviewer's about-27-px value is
expected from reporting the exact regenerated fixed detector output and the
explicit two-endpoint line-residual selector.

The control is the detector ceiling, not a win. Even perfect identification of
these detector lines would only reach 1 / 17 on this construct, so neither the
real 0 / 17 nor a hypothetical near-oracle outcome could support reopening the
classical route.

## Five evenly spaced visual checks

Every yellow overlay misses the visible painted key; these renders are
included despite the 0 / 17 numerical score.

| Index | Frame | Result | Observation | Render |
|---:|---|---|---|---|
| 0 | NCAA `IB-_u4gW3ds_1080p__s03__f003973` | NO | The projected court is dominated by crowd, hoop, and lower score-strip structure rather than the paint. | [render](g210b_court_fit_untruncated_search_artifact/renders/00_ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg) |
| 4 | NCAA `sRtHQbywiTE__s03__f006925` | NO | Vertical yellow geometry lands through the broadcast score graphic and midcourt, not the visible key. | [render](g210b_court_fit_untruncated_search_artifact/renders/04_ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg) |
| 8 | WNBA `01_1080p__s01__f001600` | NO | The model follows stands and the bottom broadcast strip while missing the lane. | [render](g210b_court_fit_untruncated_search_artifact/renders/08_wnba__wnba_01_1080p__s01__f001600.jpg) |
| 12 | WNBA `04__s06__f012223` | NO | Yellow lines key on hoop/stanchion and border geometry rather than the painted rectangle. | [render](g210b_court_fit_untruncated_search_artifact/renders/12_wnba__wnba_04__s06__f012223.jpg) |
| 16 | WNBA `07__s08__f016801` | NO | The fitted quadrilateral sits on baseline lettering and broadcast graphics, not the actual key. | [render](g210b_court_fit_untruncated_search_artifact/renders/16_wnba__wnba_07__s08__f016801.jpg) |

## Reproduction and verification

```text
python -m pytest tests/platformkit/test_g210b_court_fit_untruncated_search.py -q
python -m scripts.platformkit.tracking.g210b_court_fit_untruncated_search
```

The focused test verifies the exact `C(n,4) * 864` accounting and confirms
that real fitting has precisely `(image, sport)` parameters while the oracle
is the only function taking targets. The measurement module is 194 LOC, so
the 300-LOC rail does not require an allowlist change.

## NOT VERIFIED

- Exhaustive coverage of the untruncated configuration spaces, or the score
  of a genuinely adequate/exhaustive global classical search. The disclosed
  sampling fractions and zero oracle-quartet draws prevent that claim.
- Any learned correspondence model, detector replacement, threshold change,
  image prefilter, color cue, or production integration.
- Any conclusion that all possible classical calibration methods fail. This
  only measures the fixed global-support uniform sampler and its oracle
  detector ceiling.
- Court-coordinate precision, tracking quality, real-time latency, or
  robustness outside the 17-frame visibility-selected construct.
