# G224 top-hat line-evidence transfer

## Verdict

**CLOSED AT LIMIT: the tennis top-hat line-evidence transfer does not improve
basketball line geometry on this construct.** With one declared, fixed,
resolution-aware configuration, the real search remained 0 / 17 and the
detected-line oracle worsened from 1 / 17 to 0 / 17. Median selected-line
distance rose from 10.234791905916 px to 19.066442533166 px, and its maximum
rose from 59.693249497295 px to 93.543804852054 px.

Top-hat reduced G205 generic-corner proposals from 1,928.06 to 367.53 per
frame, so it did not create the feared unconsumable proposal explosion. That
reduction is not a win: it came with worse labelled paint-line geometry and no
real-search or oracle frame at the fixed 12 px protocol.

## Machine, fixed inputs, and source identity

This was a local Windows measurement in
`C:/Users/neelj/nba-track-a3`; no pod, SSH, service, daemon, production module,
corpus file, `src/`, or `domains/` file was changed. The complete source audit,
including SHA-256, is [per_frame.csv](g224_tophat_line_evidence_transfer_artifact/per_frame.csv).
Every input opened is named here with its full local path, byte size, and native
resolution:

| Audit ID | Full source path | Bytes | Resolution |
|---|---|---:|---:|
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg | 605623 | 1920x1080 |
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785.jpg | 584472 | 1920x1080 |
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171.jpg | 106044 | 640x360 |
| ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871.jpg | 689352 | 1920x1080 |
| ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg | 297020 | 1280x720 |
| ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920.jpg | 308901 | 1280x720 |
| ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760.jpg | 679804 | 1920x1080 |
| ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340.jpg | 531457 | 1920x1080 |
| wnba__wnba_01_1080p__s01__f001600 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_01_1080p__s01__f001600.jpg | 621798 | 1920x1080 |
| wnba__wnba_01_1080p__s03__f004062 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_01_1080p__s03__f004062.jpg | 629254 | 1920x1080 |
| wnba__wnba_01_1080p__s06__f007539 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_01_1080p__s06__f007539.jpg | 535379 | 1920x1080 |
| wnba__wnba_02__s11__f021983 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_02__s11__f021983.jpg | 251244 | 1280x720 |
| wnba__wnba_04__s06__f012223 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_04__s06__f012223.jpg | 238301 | 1280x720 |
| wnba__wnba_06__s03__f007237 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_06__s03__f007237.jpg | 598645 | 1920x1080 |
| wnba__wnba_06__s07__f014099 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_06__s07__f014099.jpg | 530179 | 1920x1080 |
| wnba__wnba_06__s09__f018997 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_06__s09__f018997.jpg | 622191 | 1920x1080 |
| wnba__wnba_07__s08__f016801 | C:/Users/neelj/nba-track-a3/docs/evidence/tracking/g130_recensus/source_decodes/wnba__wnba_07__s08__f016801.jpg | 504523 | 1920x1080 |

## Declared configuration and unchanged route

Before top-hat results were run or inspected, the one configuration was
declared as: white top-hat over grayscale; tennis's 11-px 720p kernel scaled
by `round(11 * native_height / 720)`, forced odd with a minimum of 3; contrast
45; and LSD minimum length 28 px. It is a fixed rule, not per-frame tuning.
It produces kernels 17 px on the twelve 1920x1080 inputs, 11 px on the four
1280x720 inputs, and 7 px on the 640x360 input. Kernel 11 and contrast 45
come from the imported tennis route
`domains/tennis/tracking/court_lines.py`; the scale rule is necessary because
the construct has mixed native resolutions.

The raw arm first reran G217 unchanged and reproduced its 0 / 17 real search,
1 / 17 oracle, 28.841315992648475 px median oracle maximum, 10.2347919059155
px selected-line median, and 59.693249497295 px selected-line maximum.

The treatment replaced only each raw grayscale LSD input with that top-hat
mask in the local G224 harness. The existing raw-plus-CLAHE evidence topology,
additive union, stable grouping, G210b `fit_image`, G210b `oracle_fit`,
`solve_line_pairs`, court model, deterministic search, and G205 `score_frame`
at `TOLERANCE_PX = 12.0` were otherwise unchanged. G205's unchanged generic
proposal construction supplies the proposals-per-frame measure. Labels were
used only by the unchanged scorer and the explicitly label-assisted oracle.

## Two-arm result on the exhaustive construct

| Arm | Real-search all four <= 12 px | Oracle all four <= 12 px | Selected-line median px, n=68 | Selected-line max px, n=68 | Proposals per frame |
|---|---:|---:|---:|---:|---:|
| Raw LSD baseline | 0 / 17 | 1 / 17 | 10.234792 | 59.693249 | 1928.06 |
| Fixed top-hat LSD | 0 / 17 | 0 / 17 | 19.066443 | 93.543805 | 367.53 |

The full 17-frame paired outcomes and source identity are in
[per_frame.csv](g224_tophat_line_evidence_transfer_artifact/per_frame.csv),
and all 136 labelled oracle selections (68 per arm) are in
[selected_line_distances.csv](g224_tophat_line_evidence_transfer_artifact/selected_line_distances.csv).
Those files recompute every table numerator and denominator without excluding a
frame or role.

## Evenly distributed line-evidence render check

The three panels are the predeclared lexical indices 0, 8, and 16 of the
17-frame construct. Each puts raw-LSD evidence at left and top-hat-LSD evidence
at right, with the same labelled paint-corner overlays. The top-hat panels have
less clutter, but do not visibly restore the missing paint boundaries at the
labels; the scored geometry agrees.

- [Index 0 NCAA 1920x1080](g224_tophat_line_evidence_transfer_artifact/renders/00_ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg)
- [Index 8 WNBA 1920x1080](g224_tophat_line_evidence_transfer_artifact/renders/08_wnba__wnba_01_1080p__s01__f001600.jpg)
- [Index 16 WNBA 1920x1080](g224_tophat_line_evidence_transfer_artifact/renders/16_wnba__wnba_07__s08__f016801.jpg)

## Limits and NOT VERIFIED

- This is the exhaustive 17-frame construct, not a rate for games, broadcasts,
  cameras, or future basketball footage.
- G140's p90 label repeatability is 11.39 px. The fixed 12 px threshold is at
  that label-noise floor, so even a modest improvement would not be separable
  from label noise. This result is a deterioration larger than that concern,
  not a small claimed win.
- Tennis measured its parameters on different 720p tennis footage, with a
  uniform surface and high-contrast white lines. Basketball wood, paint, logos,
  players, broadcast graphics, and non-court bright markings are materially
  different. This negative transfer does not disprove top-hat for tennis or
  every possible basketball preprocessing design.
- Learned detectors, alternative top-hat kernels or contrasts, role assignment,
  cross ratios, temporal reuse, a different search, calibration, tracking,
  production integration, and performance outside this construct are NOT
  VERIFIED.

## Verifier-contract self-check

This memo follows `docs/evidence/tracking/VERIFIER_CONTRACT.md` section B.
A1 is verifier-owned. A2 was independently recomputed from the two committed
CSVs: 17 unique audit IDs, 68 selected roles per arm, and the table values
above. A3/B7 use evenly spaced 0/8/16 renders; A4 found 17 unique source
paths and 68 distinct role rows per arm. A5/B2 found no pre-existing reader of
the new G224 artifact schema. A7 was checked: this memo, all three CSV/JSON
artifacts, and all three linked renders exist.

B1 has no exclusions; B3-B6 have no gate, deployment, schema change, claim
loop, or moved module; B8 labels the oracle as label-assisted rather than
independent; B9 names the fixed 17-frame and 68-role denominators; and B10
keeps the G205 12 px scorer and G210b route values unchanged. This is a
tracking measurement row, not an S-row, so section Q does not apply.

Focused verification in this worktree:

```text
python -m pytest tests/platformkit/test_g224_tophat_line_evidence_transfer.py -q
1 passed in 2.54s

python -m pytest tests/platformkit/test_loc_rail_scope.py -q
1 passed in 1.74s
```
