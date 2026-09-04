# G229 - Keypoint Gate Funnel

## Scope and method

This is a local-only, native-pixel measurement. No pod was contacted because
three tracking rows are running there. It cites and self-checks against
`docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections A and B. This is a
17-frame exhaustive construct, not a sampled metric.

The adapter is
`scripts/platformkit/tracking/g229_keypoint_gate_funnel.py`. It imports the
unchanged `scripts/platformkit/basketball_gate_funnel.inspect_frame` on every
image, and audits only its emitted quads with the imported `_line_support` to
retain the requested margins. It does not replace the detector, alter a gate,
or evaluate a relaxed configuration. Fixed values were Canny(50, 150),
perimeter 120.0 px, area 0.006 * W * H, shortest side 0.15 * H, and
`min_edge_support=0.16`. The G205 scorer and its 12 px protocol were used only
for the control check.

The exact inputs are all under
`C:\Users\neelj\nba-track-a5\docs\evidence\tracking\g130_recensus\source_decodes\`;
for every filename in the table, that directory joined to the listed filename
is its full opened path. Byte size and native resolution are recorded per input
below and in [per_frame.csv](g229_keypoint_gate_funnel/per_frame.csv).

## G227 abstention control

The unchanged provider reproduced G227 exactly: 17/17 abstentions, 0/17
all-four frames, and 0/68 G205-labelled corners available at 12 px. The run
raises before writing a result if that control is not exact.

## First rejecting gate distribution

| First rejecting gate | Frames |
|---|---:|
| 1. `_candidate_quads` | 1 |
| 2. `_paint`: area and shortest-side | 16 |
| 3. `_paint`: `_line_support` | 0 |
| 4. baseline adjacency naming | 0 |

Thus, no frame reached line support or baseline-adjacency naming. Landmark
co-occurrence is `none` on all 17 frames: there are no partial named paints,
so this route cannot furnish three corners, much less four, on this construct.

## Per-frame margins

`raw/P120/V4` is raw Canny contours / contours at or above the unchanged 120 px
perimeter / four-vertex approximations. `O/P/S` is valid ordered outline quads
/ physically valid quads / support-valid quads. `Amax` is largest outline area
divided by the area bar. `Lmax` is longest outline shortest-side divided by the
side bar. `Best` is one candidate's margin at its first rejecting gate: for
gate 2 it is `min(area/bar, shortest-side/bar)`. Amax and Lmax can belong to
different candidates; they are not a claim that one candidate met both tests.
`support` is N/A whenever no quad reached the physical gate, rather than a
measured zero.

| Source filename | Bytes; res | raw/P120/V4 | O/P/S | Amax | Lmax | support vs 0.16 | First gate; Best |
|---|---:|---:|---:|---:|---:|---:|---|
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg | 605623; 1920x1080 | 1970/594/45 | 2/0/0 | 0.187 | 0.243 | N/A | 2; 0.187 |
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785.jpg | 584472; 1920x1080 | 1955/570/34 | 6/0/0 | 9.059 | 0.469 | N/A | 2; 0.469 |
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171.jpg | 106044; 640x360 | 817/115/9 | 0/0/0 | N/A | N/A | N/A | 1; N/A |
| ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871.jpg | 689352; 1920x1080 | 2779/549/43 | 2/0/0 | 1.229 | 0.072 | N/A | 2; 0.072 |
| ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg | 297020; 1280x720 | 1291/277/15 | 5/0/0 | 1.440 | 0.534 | N/A | 2; 0.534 |
| ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920.jpg | 308901; 1280x720 | 1504/305/21 | 5/0/0 | 0.661 | 0.530 | N/A | 2; 0.415 |
| ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760.jpg | 679804; 1920x1080 | 3090/495/21 | 3/0/0 | 0.538 | 0.192 | N/A | 2; 0.192 |
| ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340.jpg | 531457; 1920x1080 | 1848/345/25 | 9/0/0 | 1.067 | 0.485 | N/A | 2; 0.485 |
| wnba__wnba_01_1080p__s01__f001600.jpg | 621798; 1920x1080 | 3254/651/35 | 4/0/0 | 0.384 | 0.272 | N/A | 2; 0.236 |
| wnba__wnba_01_1080p__s03__f004062.jpg | 629254; 1920x1080 | 3096/662/51 | 4/0/0 | 1.106 | 0.468 | N/A | 2; 0.468 |
| wnba__wnba_01_1080p__s06__f007539.jpg | 535379; 1920x1080 | 2132/517/50 | 1/0/0 | 0.037 | 0.053 | N/A | 2; 0.037 |
| wnba__wnba_02__s11__f021983.jpg | 251244; 1280x720 | 1060/277/20 | 2/0/0 | 1.171 | 0.390 | N/A | 2; 0.390 |
| wnba__wnba_04__s06__f012223.jpg | 238301; 1280x720 | 680/229/28 | 3/0/0 | 1.674 | 0.373 | N/A | 2; 0.373 |
| wnba__wnba_06__s03__f007237.jpg | 598645; 1920x1080 | 3041/520/30 | 7/0/0 | 0.493 | 0.286 | N/A | 2; 0.286 |
| wnba__wnba_06__s07__f014099.jpg | 530179; 1920x1080 | 2163/448/29 | 2/0/0 | 0.040 | 0.053 | N/A | 2; 0.040 |
| wnba__wnba_06__s09__f018997.jpg | 622191; 1920x1080 | 3220/538/33 | 3/0/0 | 1.775 | 0.142 | N/A | 2; 0.133 |
| wnba__wnba_07__s08__f016801.jpg | 504523; 1920x1080 | 1788/431/33 | 4/0/0 | 0.083 | 0.189 | N/A | 2; 0.062 |

The 640x360 input is reported separately because Canny and perimeter are
absolute while area and side bars are frame fractions. It had 817 raw contours,
115 at or above 120 px, and nine four-vertex approximations, but zero valid
ordered quads; its first rejection is therefore `_candidate_quads` and no
candidate margin exists. The other resolutions are 12 at 1920x1080 and four at
1280x720.

## Eye check: closest candidates

The three largest same-candidate physical-gate margins were 0.534, 0.485, and
0.469 of the required bar. They remain 46.6 percent, 51.5 percent, and 53.1
percent below the limiting area-or-side requirement, respectively. The
required renders are:

- [0.534 candidate overlay](g229_keypoint_gate_funnel/renders/closest_01_ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg)
- [0.485 candidate overlay](g229_keypoint_gate_funnel/renders/closest_02_ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340.jpg)
- [0.469 candidate overlay](g229_keypoint_gate_funnel/renders/closest_03_ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785.jpg)

The second and third overlays are broadcast graphics, including the scorebug;
the first is also not aligned with the labelled painted lane. These eye checks
reinforce the gate outcome. A margin on the best candidate does not establish
that candidate is a painted lane: a quad can clear every gate and still be the
wrong rectangle. In particular, no near-miss here is evidence that loosening a
gate would yield a correct paint.

## Verdict

**CLOSED AT LIMIT survives.** The failures are not a single threshold with a
small margin: one frame has no valid outline and the other 16 fail the combined
physical geometry gate, with the closest same-candidate margin only 0.534 of
its bar. No candidate reaches the support gate. The closest visual candidates
are non-court rectangles or graphics, which is the exclusion risk the area and
side gates are designed to control. No future relaxed-threshold proposal is
made from this row.

## Route identity and not verified

The local run recorded SHA-256 identities in
[summary.json](g229_keypoint_gate_funnel/summary.json) for the provider, the
imported funnel, G205 source route, and this adapter. No claim is made about
other broadcasts, temporal aggregation, another Canny configuration, or a
different court model. The construct is small but exhaustive for these 17
committed inputs.

Self-check: B1 no rows excluded; B2 no schema changed; B3-B6 no production
gate or deployment exists; B7 overlays are selected by measured closest margin,
not head order; B8-B9 no fit or recycled denominator; B10 all frozen bars are
stated and unchanged. The evidence paths named above exist in this landing.
