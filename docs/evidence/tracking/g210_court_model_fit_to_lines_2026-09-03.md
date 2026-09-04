# G210 court-model fit to lines

## Verdict

**Global classical court-model fitting gives 0 / 17 frames with all four held-out paint-corner roles within 12 native pixels.** This is a full-success negative result under G210's prespecified acceptance rule. It joins G141 (0 / 68 naive local corners), G205 (0 / 17 all-four, 22 / 68 corner recall at about 1,928 proposals/frame), and G208 (0 / 17 all-four, 2 / 68 at 15.59 proposals/frame): with G205's line set, a global fit cannot identify the basketball court from generic line groups.

All 17 fits were finite and passed the label-free geometric sanity guard, but their projected models did not land on the labelled paint geometry. The 68 held-out corner errors have min / median / p90 / max **59.873 / 468.820 / 991.952 / 1992.190 px**. Every error exceeds 12 px.

This was a local, CPU-only classical-geometry measurement. It made no change to `src/`, no learned-weight use, training, download, build, pod action, daemon action, or production integration.

## Court models and league declaration

Coordinates are `[x, y]` feet: x runs 0 to 50 from left to right sideline and y runs 0 to 94 from the labelled near baseline toward the far baseline. The source audit ID determines league without consulting corner coordinates: `ncaa_basketball__...` selects NCAA and `wnba__...` selects WNBA. Eight frames are NCAA and nine are WNBA.

| League | Near paint corners in model ft, role order baseline-left, baseline-right, free-throw-left, free-throw-right | Rationale |
|---|---|---|
| NCAA basketball | `[19,0]`, `[31,0]`, `[19,19]`, `[31,19]` | 12-ft lane, 94-by-50-ft court, 19-ft paint depth. |
| WNBA | `[17,0]`, `[33,0]`, `[17,19]`, `[33,19]` | 16-ft lane, with the same court length, width, and paint depth. |

The league-specific 12-ft NCAA and 16-ft WNBA outside lane widths are the official rule-book values already cited by G196: [NCAA rules and court diagram](https://ncaaorg.s3.amazonaws.com/championships/sports/basketball/rules/women/PRWBB_RulesBook.pdf) and [WNBA Rule 1 court diagram](https://cdn.wnba.com/sites/4/2026/05/2026-WNBA-Official-Rule-Book.pdf). A common lane model would silently move one league's line pair and corrupt its homography.

## Fixed detector and bounded global fit

The detector input is exactly G205's detector path, not a new primitive: native-scale OpenCV LSD on raw JPEG and CIELAB-CLAHE JPEG, each with `min_length=28 px`; G205's 1-px union guard; then G205's `stable_groups` with 5-degree angular and 10-px offset grouping. Thus the input is the same kind of stable line-group set that underlay G205's 22 / 68 recall result.

For each frame, the fitter keeps the 24 longest stable groups. A deterministic PRNG with seed 210 evaluates exactly 2,048 hypotheses using the same bounds for every frame. Each hypothesis samples four distinct groups, treats two as transverse and two as longitudinal, maps them to two sampled lines from each fixed model family, and solves the image-to-court homography from their four pairwise intersections. Model transverse lines are near baseline, near free-throw, far free-throw, and far baseline; longitudinal lines are left sideline, right sideline, left lane, and right lane.

A candidate is rejected only if its projected near-paint quadrilateral is nonfinite, has area below 0.25 percent of native image area, or lies outside the fixed one-image-width/height margin. This is an image/model sanity guard, not target filtering. A surviving hypothesis's line support is the summed observed span of its top-24 G205 groups for which one and the same projected named model line is both within 10 px of the group anchor and within 5 degrees of its orientation. Highest support wins; ties use the first deterministic sample. No frame-specific threshold, model, group count, search budget, or winner selection was changed.

The harness projects the winning model's four league-specific near-paint points back into native pixels, then calls G205's unchanged `score_frame` once per frame. The complete label-free homographies are in [fit records](g210_court_model_fit_to_lines_artifact/fit_records.json); held-out scorer rows are in [target scores](g210_court_model_fit_to_lines_artifact/target_scores.csv).

### Labels were held out of the fit

This is enforced structurally. `fit_image(image, sport)` takes only pixel data and a prefix-derived sport; it has no target, role, coordinate, distance-to-label, or label-selection argument. The source manifest reads only audit ID, source path, dimensions, and sport before fitting all 17 frames. Only after every fit is cached to `fit_records.json` does the harness read x/y/role fields, generate the four model projections, and call G205's unchanged scorer. Labels do not seed hypotheses, filter hypotheses, contribute to line support, reject a fit, select a winner, or appear in overlays. The source render overlays only the fitted yellow model.

## Results: exhaustive 17-frame construct

Error vector order is baseline-left, baseline-right, free-throw-left, free-throw-right. Line support is observed grouped-line span in native pixels; it is the fit selection score, not a calibration claim.

| Audit ID | League | Fit | Line support px | Supported groups / 24 | Held-out errors px | All four <=12 px |
|---|---|---|---:|---:|---|---|
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973` | NCAA | yes | 19813.869 | 14 | [115.083, 208.158, 84.704, 111.369] | no |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s13__f015785` | NCAA | yes | 24398.766 | 13 | [516.172, 813.269, 484.343, 851.343] | no |
| `ncaa_basketball__ncaa_basketball_IB-_u4gW3ds__s14__f028171` | NCAA | yes | 7286.148 | 17 | [59.873, 103.218, 181.467, 196.298] | no |
| `ncaa_basketball__ncaa_basketball_mRkuGgeECak__s08__f016871` | NCAA | yes | 21307.406 | 13 | [1992.190, 1430.545, 1944.225, 1384.378] | no |
| `ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925` | NCAA | yes | 12723.952 | 12 | [243.878, 88.270, 455.142, 430.713] | no |
| `ncaa_basketball__ncaa_basketball_tiUvyvWOCxo__s01__f002920` | NCAA | yes | 13451.416 | 14 | [403.603, 206.642, 201.977, 112.757] | no |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s02__f005760` | NCAA | yes | 25652.971 | 14 | [1333.362, 1198.626, 836.167, 762.522] | no |
| `ncaa_basketball__ncaa_basketball_zqBCKovJCQU__s10__f020340` | NCAA | yes | 21694.454 | 13 | [385.182, 567.183, 358.426, 502.835] | no |
| `wnba__wnba_01_1080p__s01__f001600` | WNBA | yes | 21061.733 | 12 | [424.937, 475.002, 166.214, 462.638] | no |
| `wnba__wnba_01_1080p__s03__f004062` | WNBA | yes | 20152.485 | 11 | [833.269, 712.517, 1004.045, 986.769] | no |
| `wnba__wnba_01_1080p__s06__f007539` | WNBA | yes | 17761.426 | 10 | [508.153, 575.045, 632.212, 676.220] | no |
| `wnba__wnba_02__s11__f021983` | WNBA | yes | 9281.098 | 13 | [456.895, 792.318, 95.014, 716.956] | no |
| `wnba__wnba_04__s06__f012223` | WNBA | yes | 16378.298 | 16 | [906.046, 606.784, 842.319, 431.616] | no |
| `wnba__wnba_06__s03__f007237` | WNBA | yes | 21427.192 | 13 | [308.107, 338.517, 347.498, 371.947] | no |
| `wnba__wnba_06__s07__f014099` | WNBA | yes | 17386.083 | 15 | [704.576, 767.684, 100.527, 290.986] | no |
| `wnba__wnba_06__s09__f018997` | WNBA | yes | 15391.294 | 13 | [266.039, 586.039, 210.674, 111.166] | no |
| `wnba__wnba_07__s08__f016801` | WNBA | yes | 13903.469 | 9 | [948.461, 816.196, 504.598, 258.192] | no |

Full audit IDs are retained in [per-frame records](g210_court_model_fit_to_lines_artifact/per_frame.csv). Per-role error distributions are below; the 17 values per role are the exhaustive construct, not an estimate of arbitrary broadcast footage.

| Role | Min px | Median px | p90 px | Max px |
|---|---:|---:|---:|---:|
| Baseline left | 59.873 | 456.895 | 948.461 | 1992.190 |
| Baseline right | 88.270 | 586.039 | 816.196 | 1430.545 |
| Free-throw left | 84.704 | 358.426 | 842.319 | 1944.225 |
| Free-throw right | 111.166 | 431.616 | 851.343 | 1384.378 |

## Five evenly spaced eye checks

The deterministic lexical positions are 0, 4, 8, 12, and 16. A human sees **no fitted model landing on painted court geometry (0 / 5 YES)**. In every render, the yellow court model follows a lower-third/score strip, stands, or arbitrary image structure rather than the painted court.

| Index | Frame | Result | Observation | Render |
|---:|---|---|---|---|
| 0 | NCAA `IB-_u4gW3ds_1080p__s03__f003973` | NO | Parallel yellow lines follow lower image structure and score graphics, not the near paint. | [render](g210_court_model_fit_to_lines_artifact/renders/00_ncaa_basketball__ncaa_basketball_IB-_u4gW3ds_1080p__s03__f003973.jpg) |
| 4 | NCAA `sRtHQbywiTE__s03__f006925` | NO | Model crosses stands and lower-third; it does not follow the visible court markings. | [render](g210_court_model_fit_to_lines_artifact/renders/04_ncaa_basketball__ncaa_basketball_sRtHQbywiTE__s03__f006925.jpg) |
| 8 | WNBA `01_1080p__s01__f001600` | NO | Lines collect in the lower score strip rather than the painted key and arc. | [render](g210_court_model_fit_to_lines_artifact/renders/08_wnba__wnba_01_1080p__s01__f001600.jpg) |
| 12 | WNBA `04__s06__f012223` | NO | Yellow lines trace the lower-third and unrelated border geometry, not paint. | [render](g210_court_model_fit_to_lines_artifact/renders/12_wnba__wnba_04__s06__f012223.jpg) |
| 16 | WNBA `07__s08__f016801` | NO | Overlay runs through the broadcast strip and misses the clearly visible key. | [render](g210_court_model_fit_to_lines_artifact/renders/16_wnba__wnba_07__s08__f016801.jpg) |

## Interpretation and limitation

The negative result is informative: even when all line evidence is consumed globally, line support selects non-court structure on this favourable, corner-visible construct. It does not contradict G196: four hand-labelled paint corners still recover the model and project independent arc geometry correctly. Together, the evidence says the bottleneck is identifying which observed line groups are court paint, not merely fitting a projective court once correspondences are valid.

G140's p90 label repeatability is **11.39 px**, so the frozen 12 px threshold is at the label-noise floor. A pass would have shown only rough landing, not production accuracy; this 0 / 17 failure is well beyond that floor. The 17 frames are small, non-random, and selected for corner visibility. Thus even a hypothetical success would be a lower bound on difficulty rather than evidence of robust arbitrary-footage performance.

## Reproduction and verification

```text
python -m pytest tests/platformkit/test_g210_court_model_fit_to_lines.py -q
python -m scripts.platformkit.tracking.g210_court_model_fit_to_lines
```

The focused test passed after the final support-predicate correction: `1 passed in 1.18s`. The harness has no production-path change and remains below the 300-LOC rail, so no LOC allowlist entry changed.

## NOT VERIFIED

- A court-specific learned model, any training route, or a justification to reopen G31's closed tennis training path.
- Any alternative line detector, detector threshold, line segmentation model, or image prefilter beyond the unchanged G205 path.
- A conclusion that every possible classical court-calibration method fails; this measures the specified bounded global line-support fit only.
- Court-coordinate accuracy, production integration, tracking accuracy, real-time performance, or robustness beyond the 17-frame visibility-selected construct.
- Whether additional labels or court-specific learned correspondence identification would succeed; those are different future work and are not implied by this result.
