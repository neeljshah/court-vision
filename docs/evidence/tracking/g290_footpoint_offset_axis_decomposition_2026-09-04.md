# G290: Signed footpoint offset axis decomposition

**Verdict: ACCEPT (measurement only), CONDITIONED on a located player being in the box: among 112 detector-box footpoint observations, the 79 in-box pairs are predominantly vertical (squared-offset shares y=0.648663, x=0.351337; median absolute dy=103.250 px versus dx=75.750 px) and biased downward (50/79=0.633 below, nominal two-sided p=0.023820), pointing toward footpoint derivation or box extent under the nearest-foot assumption; the 33/112=0.295 observations with no located player in the box are EXCLUDED, so this does not transfer to the unconditioned question, and the scope is 15 frames, 143 hand-located foot observations, ONE clip, ONE span, ONE labeller and ONE non-deterministic draw, not authenticated players or a clip-wide result.**

Machine: local CPU arithmetic in `C:/Users/neelj/nba-track-a3` on branch
`track-a3`, because both coordinate inputs and the verifier are committed here.
There is NO eye check and NO ground truth in this row. This is arithmetic on
two coordinate sets, not visual validation. The directional result is a
measurement success; it is not a verified causal diagnosis or a production
intervention.

The downward bias is moderate, not universal: 29/79 point upward and horizontal
error still contributes 35.1 percent of squared offset. Under the spec's
diagnostic interpretation the dominant component shifts the paired defect
toward the footpoint derivation/box extent. It does not establish that every
detection fired on the right person, or rule out a detector defect. Pairing
ambiguity below is material, and no classifier or pass bar was introduced to
force an axis verdict.

The spec is [G290_spec.md](specs/G290_spec.md), and the binding contract is
[VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md). G285b, G286, G287 and G288 memos
and their ledger rows were read; their coordinates, counts and verdicts are
unchanged. In particular, G287's correction to the generalisation of G286 is
why the conditioning and excluded population are in the verdict itself.

## Pairing reproduction, before component analysis

The reused `load_located()`, `load_detections()` and
`footpoint_player_split()` come from
`scripts/platformkit/tracking/verifier_footpoint_analyses.py`.
The reused `CROP_HALF_W` and `CROP_HALF_H` define the unchanged 512x640
neighbourhood. Inclusion is inclusive in each axis; pairing selects the
Euclidean-nearest located foot INSIDE that box, retaining input order on an
exact tie. Located feet are not consumed: several detector observations can
pair with one hand location. No G270 court-space filter is applied.

```text
python -m scripts.platformkit.tracking.g290_footpoint_offset_axis_decomposition
REPRODUCED n=112, in_box=79 (0.705), no_player=0.295, median=172.36 px
```

The unrounded distance median is 172.35954426720906 px. The harness stops on
a reproduction mismatch before computing the component summary. All 112
eligible observations have distinct `(source_frame, detection_index)` keys;
79 are paired and 33 are retained in a separate excluded-observation CSV.

**Sign convention: dx = detection_x - located_x; dy = detection_y - located_y,
in image pixels, with image y increasing DOWNWARD. Positive dy means the
detector footpoint is BELOW the located foot; negative dy means ABOVE.
Positive dx means RIGHT; negative dx means LEFT.**

## Absolute components

Every row uses the same eligible denominator: all 79 in-box pairs. Quartiles
use linear interpolation at `(79-1)*p` (inclusive/type-7 quantiles); IQR is
Q3 minus Q1. Each squared share is `sum(axis_offset**2) / sum(dx**2+dy**2)`.

| Axis | Median absolute offset (px) | Q1 (px) | Q3 (px) | IQR width (px) | Squared-offset share |
| --- | ---: | ---: | ---: | ---: | ---: |
| dx | 75.750 | 38.750 | 147.875 | 109.125 | 0.351337 |
| dy | 103.250 | 42.59375 | 214.250 | 171.65625 | 0.648663 |
| Share SUM | | | | | **1.000** |

Median of the 79 individual `abs(dy)/abs(dx)` ratios is **1.408257**.
This is a median of pairwise ratios, not a ratio of axis medians. There are
zero zero-dx pairs and zero undefined zero/zero pairs.

## Signed components and horizontal control

| Axis | Positive count / eligible in-box pairs | Negative count / eligible in-box pairs | Zeros | Eligible nonzero sign-test denominator | Nominal two-sided binomial p |
| --- | --- | --- | ---: | ---: | ---: |
| dy | BELOW: 50/79 = 0.632911 | ABOVE: 29/79 = 0.367089 | 0 | 79 | 0.023819792858 |
| dx | RIGHT: 40/79 = 0.506329 | LEFT: 39/79 = 0.493671 | 0 | 79 | 1.000000000000 |

Both tests use null positive-sign probability 0.5. P-values are **nominal,
two-sided, with no multiplicity correction**. They also have no adjustment
for within-frame or repeated-track dependence; 79 observations are not 79
independent players. Zeros would be separately reported and omitted only
from the sign-test denominator; here there are none.

Horizontal control: **no horizontal sign bias is observed (40 right versus
39 left, p=1.0)**. Thus there is no surprising horizontal bias to flag in
this draw. This is not proof of horizontal correctness: median absolute dx
remains 75.750 px.

## Image-height comparison

Terciles use DETECTOR `foot_y_px` among all 79 eligible in-box pairs, not
located-foot y and not all 112 observations. Type-7 cutpoints are 537.0 and
734.25 px; low includes the first cutpoint, middle includes the second.

| Detector foot_y_px tercile | Observed foot_y_px range | Median absolute dy (px), with named eligible denominator |
| --- | --- | --- |
| Low: y <= 537.0 | 164.625 to 537.0 | **64.000 px; eligible in-box pairs in this cell = 27** |
| Middle: 537.0 < y <= 734.25 | 555.375 to 734.25 | **58.125 px; eligible in-box pairs in this cell = 26** |
| High: y > 734.25 | 744.75 to 975.0 | **215.625 px; eligible in-box pairs in this cell = 26** |

Eligible denominators sum to 27+26+26=79. The high-y cell has a much larger
median than either lower-y cell; the measured medians are not constant in
pixels. Smaller offsets toward small y are coarsely compatible with the
body-scale expectation, but the low-to-middle ordering is not monotonic.
These 27/26/26-pair cells do not establish a camera-distance or body-size
trend. In addition, detector y itself contains dy, so this stratification
does not independently measure distance or player height.

**No dy was converted into feet.** `local_pixel_to_feet` maps the GROUND
PLANE. A vertical image offset from a player's feet toward the head is not
a ground-plane displacement; passing it through the homography would give
a meaningless number. All reported offsets remain in PIXELS.

## Pairing ambiguity and limits

**57/79 = 0.721519 eligible in-box pairs have a SECOND located foot inside
the same box** (at least two candidates total); 22/79 have exactly one.
Nearest-foot pairing is an ASSUMPTION: when players stand close, the nearest
located foot may not belong to the person the detector fired on. Candidate
multiplicity measures ambiguity, not the number of incorrect assignments.
No pair was dropped, re-assigned after analysis, or visually authenticated.

- The located feet are ONE labeller's hand locations, NOT ground truth; the
  same labeller produced the verdicts underlying the programme's other rows.
- This is ONE clip, ONE span and ONE draw of a non-deterministic route.
  G241 reported 808 of 1,201 records differing. Repeating coordinate
  arithmetic is not evidence of route repeatability.
- Per G278, this span is measurably friendlier than the clip: 0.836 versus
  0.656, p=0.0078. Nothing here may be quoted clip-wide.
- The population is detector-box observations, not authenticated players.
  Conditioning on a located player in the box excludes 33/112=0.295 and
  does not answer the unconditioned question. The unchanged rectangular
  box also permits a larger vertical than horizontal offset; the shares
  describe that fixed conditioned population.

NOT VERIFIED: ground-truth localisation; authenticated detector-to-person
assignment; an independently established footpoint-rule or box-extent cause;
inter-labeller reliability; a body-scale trend; replication beyond this
span, clip, labeller or draw; route determinism; and unconditioned or
clip-wide error. There is NO new eye check. No filter, threshold, gate,
footpoint rule change, re-projection, retrain or production change is proposed.

## Exact opened coordinate inputs and evidence

- `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv`:
  **5,694 bytes**, SHA-256 `ed52cd937f19a2c344ac700491738d49823cb8e8f31df90a9d84db8bc98ee8b3`;
  CSV coordinates refer to **1920x1080** source pixels, 143 hand locations
  in 15 frames. This is the local checkout byte size, not a copied historical
  memo size.
- `C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json`:
  **12,446,681 bytes**, SHA-256 `0903d4ee8afac9999e37ca07d14ec81ea59e66ca485a99c21fd27ed959cee2b5`;
  JSON coordinate resolution **1920x1080**.

The JSON's video provenance names
`/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407
bytes, 1920x1080, source span 19599..23399 inclusive at 30 fps. **That video
was NOT opened and is not an input required to reproduce this row.** No pod,
GPU, decode or rendering was used. Both coordinate inputs and the imported
verifier remain unchanged.

All outputs are under
`docs/evidence/tracking/g290_footpoint_offset_axis_decomposition_artifact/`:

- `paired_offsets.csv`: every one of the 79 pairs, source/detection indices,
  both coordinates, signed dx/dy, Euclidean distance and in-box candidate count.
- `excluded_footpoints.csv`: all 33 excluded observations and their coordinates.
- `measurement_summary.json`: complete precision statistics, exact input
  paths/bytes/hashes/resolution, local route identity and source-frame selection.
- `measurement_stdout.txt`: pasted arithmetic output, including the 1.000 sum.
- `test_stdout.txt`: the two per-file test commands and captured results below.

## Per-file tests and contract self-check

```text
python -m pytest scripts/platformkit/tracking/test_g290_footpoint_offset_axis_decomposition.py -q -p no:cacheprovider
...                                                                      [100%]
3 passed in 1.17s
python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
.                                                                        [100%]
1 passed in 0.61s
```

The focused test pins 112/79/33 and the 172.35954426720906 px median, verifies
unique observation keys, and checks that a detector 25 px BELOW a located
foot produces **dy=+25 px**. It also checks negative dy, the inclusive box,
nearest-candidate selection, zero handling in sign tests, and STOP on a
changed reproduction population. No full pytest was run.

Section B self-check: B1 exclusions and conditioning are named in the verdict;
B2-B6 only additive local evidence/code/test and ledger/register rows, with no
schema, lifecycle, production, deployment or module-move changes; B7 every
eligible observation from the sealed frames is retained, with no head slice;
B8 no fitted residual or independent correctness claim; B9 all 112 observation
keys are unique and the population is explicitly detector-box observations;
B10 the existing crop constants, definitions, counts and bars are unchanged;
B11 one non-deterministic draw is explicit and no system-wide property is claimed.
A7 output and coordinate-input paths exist; A9 exact input identity is above;
A12 no allowlisted file grew, and the LOC rail passed. Section Q does not apply
to this G-row. The memo, outputs, RESULTS_LEDGER row and result-register row
are committed together with explicit pathspecs and no push.
