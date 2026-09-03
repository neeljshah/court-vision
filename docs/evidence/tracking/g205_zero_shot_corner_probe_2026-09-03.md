# G205 zero-shot paint-corner probe

## Verdict

**The single locally obtainable zero-shot candidate fails the acceptance bar:**
`g134_stable_lsd_intersections` produced **0 / 17** frames with all four named
paint corners within 12 native pixels. It therefore does not establish the
required `>= 1 / 17` result. It did make 22 / 68 individual target roles
available, but never all four together on a frame.

This is an **AT LIMIT result for the tested G134-seeded classical primitive**.
It is not a global closure of every named zero-shot route: ELSED, DeepLSD,
HAWP, M-LSD, and KpSFR were not run and remain explicitly NOT VERIFIED below.
It does not close labelling. G196 still shows that labelled corners recover
the geometry; this row measures detection only.

## Fixed construct and coordinate contract

- Input: the unchanged 68-row, 17-frame G140 target CSV. Every source JPEG
  was opened through its `source_decode` path and checked against that row's
  declared native width and height. The actual construct includes 12 images at
  1920x1080, four at 1280x720, and one at 640x360; no resize or 1080p
  assumption was made.
- Every target remained in the denominator. Proposals are generic native-pixel
  points, not role-labelled. A target role is available when any proposal on
  its own frame is within the frozen 12.0 px Euclidean tolerance. A proposal
  is precise when it is within that tolerance of any of the four targets on
  its own frame. This is G141's protocol, including counting each proposal
  once and retaining all nearby proposals.
- The primary event requires each of the four separately named roles to be
  available on the same frame. The denominator is the exhaustive construct,
  17, without exclusions.

### The 12 px limitation

G140's blind relabelling p90 was **11.39 px**. The fixed 12 px tolerance is
therefore essentially at the label-noise floor: it is a **generous feasibility
bar**, not an accuracy standard. Failure at 12 px is comfortably a failure;
success at 12 px would only show that a primitive proposes something in the
right place, not that it is production accurate.

## Candidate availability and licences

| Candidate | Code licence | Status | Reason |
|---|---|---|---|
| `g134_stable_lsd_intersections` | OpenCV: Apache-2.0; grouping uses in-repository G134 reference code | **Run** | All required components were present locally. |
| ELSED | Apache-2.0 | Excluded, not measured | No local source/binding was present; official use requires a source/package fetch and build. |
| DeepLSD | MIT | Excluded, not measured | No local source, inference dependencies, or Wireframe-trained checkpoint was present. Official use requires clone/install plus checkpoint fetch. Weight licence was not independently verified. |
| HAWP | MIT | Excluded, not measured | No local source, dependencies, or official checkpoint was present. The official setup calls for clone/install and checkpoint download. Weight licence was not independently verified. |
| M-LSD | Apache-2.0 | Excluded, not measured | No local TensorFlow/TFLite runtime, source, or supplied model was present. Weight licence was not independently verified. |
| KpSFR | MIT | Excluded, not measured | No local source, CUDA-era dependency stack, or soccer checkpoint was present. Its released inference is soccer-specific; weight licence was not independently verified. |

No network fetch, package installation, training, GPU operation, pod use, or
`run_clip.py` invocation occurred. The exclusions are availability statements,
not negative results, and no GPL material was added to the repository. The
official project pages used for the licence/availability check are
[ELSED](https://github.com/iago-suarez/ELSED),
[DeepLSD](https://github.com/cvg/DeepLSD),
[HAWP](https://github.com/cherubicXN/hawp),
[M-LSD](https://github.com/navervision/mlsd), and
[KpSFR](https://github.com/ericsujw/KpSFR).

## Executed candidate and fixed configuration

The configuration was committed in
[`protocol.json`](g205_zero_shot_corner_probe/protocol.json) before output
generation and was applied identically to every source image:

1. Detect raw and contrast-enhanced OpenCV LSD segments at native image scale,
   each with G134's `min_length=28.0` px.
2. Form G134 stable line groups: baseline groups are frozen and enhanced-only
   additions are grouped separately, with `angle=5.0` degrees and
   `offset=10.0` px.
3. Intersect every pair of stable groups only when their acute separation is at
   least 35 degrees, the intersection lies inside the native image, and it is
   within both observed group supports extended by the existing 45 px endpoint
   allowance. Deduplicate only points within 2 native px.

Those values are fixed for the entire construct. There is no target-derived
detection, role assignment, per-frame threshold choice, line calibration,
homography, or production integration.

## Results

| Candidate | All four roles, frames | Per-corner recall | Proposal precision |
|---|---:|---:|---:|
| `g134_stable_lsd_intersections` | **0 / 17 (0.00%)** | **22 / 68 (32.35%)** | **80 / 32,777 (0.24%)** |

The individual-role availability is 3 / 17 baseline-left, 3 / 17
baseline-right, 6 / 17 free-throw-left, and 10 / 17 free-throw-right. It is
not enough that some corners are available: no frame satisfies all four.

### Per-candidate, per-frame table

| Candidate | Audit ID | Native dimensions | Proposals | Matched roles | All four within 12 px |
|---|---|---:|---:|---:|---|
| stable LSD | `ncaa...IB-_u4gW3ds_1080p__s03__f003973` | 1920x1080 | 2,621 | 2 | no |
| stable LSD | `ncaa...IB-_u4gW3ds_1080p__s13__f015785` | 1920x1080 | 2,255 | 0 | no |
| stable LSD | `ncaa...IB-_u4gW3ds__s14__f028171` | 640x360 | 83 | 2 | no |
| stable LSD | `ncaa...mRkuGgeECak__s08__f016871` | 1920x1080 | 4,684 | 2 | no |
| stable LSD | `ncaa...sRtHQbywiTE__s03__f006925` | 1280x720 | 949 | 3 | no |
| stable LSD | `ncaa...tiUvyvWOCxo__s01__f002920` | 1280x720 | 804 | 1 | no |
| stable LSD | `ncaa...zqBCKovJCQU__s02__f005760` | 1920x1080 | 3,220 | 1 | no |
| stable LSD | `ncaa...zqBCKovJCQU__s10__f020340` | 1920x1080 | 1,612 | 1 | no |
| stable LSD | `wnba...01_1080p__s01__f001600` | 1920x1080 | 3,122 | 3 | no |
| stable LSD | `wnba...01_1080p__s03__f004062` | 1920x1080 | 2,264 | 1 | no |
| stable LSD | `wnba...01_1080p__s06__f007539` | 1920x1080 | 1,763 | 2 | no |
| stable LSD | `wnba...02__s11__f021983` | 1280x720 | 379 | 0 | no |
| stable LSD | `wnba...04__s06__f012223` | 1280x720 | 1,390 | 1 | no |
| stable LSD | `wnba...06__s03__f007237` | 1920x1080 | 1,857 | 0 | no |
| stable LSD | `wnba...06__s07__f014099` | 1920x1080 | 1,320 | 1 | no |
| stable LSD | `wnba...06__s09__f018997` | 1920x1080 | 1,645 | 1 | no |
| stable LSD | `wnba...07__s08__f016801` | 1920x1080 | 2,809 | 1 | no |

The complete, unabridged audit IDs and numeric measurements are in
[`per_frame.csv`](g205_zero_shot_corner_probe/per_frame.csv), with one
row for every proposal and target score in
[`proposal_scores.csv`](g205_zero_shot_corner_probe/proposal_scores.csv) and
[`target_scores.csv`](g205_zero_shot_corner_probe/target_scores.csv).

## Eye check

The sole and therefore closest candidate was rendered on the predeclared,
evenly spaced lexical positions 0, 4, 8, 12, and 16:

- [00 NCAA 1920x1080](g205_zero_shot_corner_probe/renders/00_ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg)
- [04 NCAA 1280x720](g205_zero_shot_corner_probe/renders/04_ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg)
- [08 WNBA 1920x1080](g205_zero_shot_corner_probe/renders/08_wnba__wnba_01_1080p__s01__f001600.jpg)
- [12 WNBA 1280x720](g205_zero_shot_corner_probe/renders/12_wnba__wnba_04__s06__f012223.jpg)
- [16 WNBA 1920x1080](g205_zero_shot_corner_probe/renders/16_wnba__wnba_07__s08__f016801.jpg)

Human inspection agrees with the arithmetic. Grey crosses are extremely dense
at intersections of crowd texture, players, basket apparatus, broadcast
graphics, signage, and unrelated court markings. Some labelled corners have a
nearby cross, especially on the wider court views, but every inspected frame
has at least one labelled paint corner without one. The 640x360 frame produces
far fewer points but still only two roles. The proposal volume (32,777) makes
the 0.24% precision failure visually unsurprising.

## Reproduction and verification

```text
python -m pytest tests/platformkit/test_g205_zero_shot_corner_probe.py -q
python -m scripts.platformkit.tracking.g205_zero_shot_corner_probe
```

The focused harness test passed: `1 passed in 0.84s`. An independent readback
of written artifacts reproduced 68 targets, 22 available roles, 32,777
proposals, 80 proposal hits, and 0 all-four frames. The harness is 167 LOC,
below the 300-LOC rail; no allowlisted file grew. The separately run global
PlatformKit LOC-rail test currently fails on pre-existing allowlisted
`scripts/platformkit/tracking_harness.py` (424 LOC against its 416 limit).
G205 neither edits nor adds that allowlisted module, so its unrelated limit is
not changed in this commit.

## NOT VERIFIED

- ELSED, DeepLSD, HAWP, M-LSD, and KpSFR inference, including their released
  weights and any basketball-domain behaviour.
- Any claim that all possible zero-shot corner routes are closed. Only the
  tested G134-seeded classical route is at limit.
- Homography, court-coordinate accuracy, calibration, tracking, deployment,
  or production integration.
- Accuracy beyond the generous 12 px label-floor threshold, external
  generalisation, or a solution to the labelling requirement.
