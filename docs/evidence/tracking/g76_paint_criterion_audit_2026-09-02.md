# G76 Paint Criterion Audit

## Result

The criterion was frozen in commit `79be5f7d4cd98eb2a272ffb866cfc45308e796d2` before this audit's labels were opened. The blind relabel disagreed with 38 of 121 census calls (31.40%): 20 census-positive tiles were not solvable under the frozen rule, while 18 census-negative tiles were solvable. Applying those two directional rates to the G68 census changes the pooled share from 0.6236 to **0.5732**, with a plug-in Wilson 95% interval of **[0.5491, 0.5968]** on the 1,650-frame census-equivalent estimate. This remains well above the pre-registered 0.10 decision rule, so the criterion audit releases the held G68D verdict and G75 downstream work.

## Frozen definition

`PAINT_SOLVABLE` means that all four lane lines of one paint--the baseline, the free-throw line, and both lane side lines--are individually discernible in the tile, each with enough continuous visible extent to fit a line to it. A three-point arc alone, a centre-court logo, a visible basket whose lane lines are out of frame, or a paint whose far side is occluded by players so that no line can be fitted does not qualify.

The canonical pre-label definition is [G76_PAINT_SOLVABLE_DEFINITION.md](g68_criterion_audit/G76_PAINT_SOLVABLE_DEFINITION.md).

## Full-resolution examples

- Positive: [annotated WNBA 01 f11904](g68_criterion_audit/G76_positive_wnba_01_f11904_annotated.jpg). The green overlays identify the baseline, free-throw line, left lane side, and right lane side; each has continuous fittable extent.
- Negative: [annotated WNBA 02 f192](g68_criterion_audit/G76_negative_wnba_02_f192_annotated.jpg). I agree this is a negative: it is midcourt action with neither paint's four lane lines in frame. A three-point arc and court branding are not qualifying geometry.

Both images are native 640x384 tile renders. The f192 conclusion agrees with the earlier spot-check, but its earlier 0-flip rereads are not used as validity evidence here: they assessed repeatability of the old criterion, not whether that criterion was correctly bounded.

## Blind sample and labels

Seed: `76092026`, using Python `random.Random`, selecting 11 positions without replacement in each of the 11 clips (n=121). The selection renderer read only frame identities and row positions; it did not access the census `label` field. I viewed the label-free, original-resolution boards and wrote [G76_blind_relabels.csv](g68_criterion_audit/G76_blind_relabels.csv) before joining it to any census label. The separate [blind sample manifest](g68_criterion_audit/blind_sample/seeded_sample_manifest.csv), [method note](g68_criterion_audit/blind_sample/README.md), and 11 label-free native-tile boards are retained with the evidence.

| clip | n | census positive | G76 positive | census positive -> G76 not | census not -> G76 positive |
|---|---:|---:|---:|---:|---:|
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds | 11 | 6 | 4 | 2 | 0 |
| ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p | 11 | 8 | 6 | 2 | 0 |
| ncaa_basketball__ncaa_basketball_WFl3V7ZY4ss | 11 | 7 | 6 | 3 | 2 |
| ncaa_basketball__ncaa_basketball_sRtHQbywiTE | 11 | 9 | 6 | 5 | 2 |
| ncaa_basketball__ncaa_basketball_tiUvyvWOCxo | 11 | 4 | 8 | 1 | 5 |
| ncaa_basketball__ncaa_basketball_zqBCKovJCQU | 11 | 7 | 6 | 1 | 0 |
| wnba__wnba_01 | 11 | 5 | 6 | 0 | 1 |
| wnba__wnba_01_1080p | 11 | 4 | 7 | 0 | 3 |
| wnba__wnba_02 | 11 | 5 | 6 | 2 | 3 |
| wnba__wnba_04 | 11 | 7 | 6 | 2 | 1 |
| wnba__wnba_05 | 11 | 7 | 6 | 2 | 1 |
| **pooled** | **121** | **69** | **67** | **20** | **18** |

## Directional disagreement and correction

The direction that can inflate the original share is census `PAINT_SOLVABLE` -> G76 `NOT_PAINT_SOLVABLE`: **20/69 = 0.2899** conditional on census-positive sampled tiles (or 20/121 = 0.1653 of all sampled tiles; Wilson 95% conditional interval [0.1962, 0.4057]). The reverse direction is **18/52 = 0.3462** conditional on census-negative sampled tiles (or 18/121 = 0.1488 of all sampled tiles; Wilson 95% conditional interval [0.2315, 0.4820]). Total disagreement is 38/121 = 0.3140.

The correction is mechanical, not hand-adjusted. With G68's `p_census = 1,029/1,650 = 0.623636` and the two conditional disagreement rates:

```text
p_corrected = p_census * (1 - 20/69) + (1 - p_census) * (18/52)
            = 0.623636 * 0.710145 + 0.376364 * 0.346154
            = 0.573152
```

That is 945.70 positive frames on the 1,650-frame census-equivalent scale. Wilson's 95% interval for `945.70/1,650` is [0.5491, 0.5968]. This is a plug-in interval for the corrected census-equivalent share; it does not propagate the extra uncertainty from estimating the two directional rates on 121 tiles.

## Verifier self-check

- A7: every path linked or named above exists in this worktree: definition, two annotated renders, blind labels, manifest, method note, and all 11 blind boards.
- B1: no rows were excluded; all 121 seeded selections across all 11 clips are present.
- B2: no existing schema, labels, or reader was changed; G76 labels are a separate file.
- B3-B6: no gate, deploy, module movement, or reader behavior was changed.
- B7: the sample is seeded and clip-stratified, not a head slice; every tile was judged at native resolution.
- B8-B9: this is an independent relabel comparison over distinct sampled tiles; its denominator is 121 tile identities, not recycled identifiers.
- B10: no harness threshold, coordinate contract, or pre-registered 0.10 decision rule was altered.

## Not verified

- This audit does not establish inter-rater validity or an external adjudicator's error rate; it is one blinded relabel under the committed criterion.
- The plug-in Wilson interval does not include uncertainty from the finite relabel sample, as stated above.
- This row does not build or evaluate a paint solver, change G68's original labels, or make any performance claim about downstream calibration.
