# G258: Synthetic ground-truth projection-displacement resolution

## Verdict

**ACCEPT (measurement only): on one G233d/G247 WNBA seed frame, the fixed G248 edge-response contrast first met the pre-committed sensitivity declaration at a known 10 px projected-court translation. This is below G257's 20 px eye-gate resolution on its different amateur footage.** G252's pooled found-distance p90 first met the same declaration at 40 px without its p90 reaching the 24 px censoring limit. G247 quad shape was invariant at every 0-100 px rung. No production gate, threshold, tuning, refit, relabeling, or automatic-calibration claim follows. Automatic calibration remains 0/17.

This is a different question from G242, G244, G247, and G248. Those closed rows asked whether their signals separated inherited human VALID from INVALID labels, and their negatives stand. G257 then established that the relevant eye instrument resolved only 20 px while G252 measured 5 px median and 19 px p90 detector-conditioned offset. G258 replaces those labels with a known synthetic perturbation; it does not revisit a label-based verdict.

Denominator: 1 G233d seed, 1 source frame, 1 WNBA clip, 1 arena, 7 fully enumerated ladder rungs, and 5 independently streamed decodes per rung. The five decodes had the same BGR-byte SHA-256 `686c94a7738c3e1ede2b39ea98cb09f096eead96826ff543baf4585d4c8f4270`; their control spread is therefore zero for every reported scalar. This is repeatability of this decode/measurement route, not a repeat over different frames or cameras.

## Lane, source identity, and disk guard

This ran on the pod because the named 1920x1080 full-resolution source is read-only there. Before writing G258 evidence, a raw `ps -eo pid,ppid,comm,args` pod census was collected and filtered locally for tagged measurement processes. It excluded the checker mechanism by not putting its matching pattern into the remote process command, found no G256/G256b/G258 row, and did not interrupt any process. Permanent service processes were left alone.

`df` was not used. Two authoritative `dd conv=fsync` probes ran before the worker output existed: first, `du -sm /workspace/nba-ai-system/data` was 33151 MB and a 1,048,576-byte `g258_disk_probe.bin` was removed; immediately before the worker, the baseline was 33155 MB and a 1,048,576-byte `g258_worker_probe.bin` was removed. The worker wrote one 51,477-byte temporary JSON under `/tmp/g258_ladder_*`, copied it into this artifact, then removed the remote directory. Total temporary bytes freed were 2,148,629. No corpus source, G247/G248/G252 artifact, or either abandoned `footage_bridge` partial was deleted.

| Input or route | Full path | Bytes / resolution | SHA-256 / role |
|---|---|---:|---|
| Source video | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` | 2,931,985,407 bytes; 1920x1080 | Read-only source, frame 19599, scale 1.0 |
| Persisted maps | `docs/evidence/tracking/g247_projected_quad_validity_artifact/g247_measurement.json` | 142,822 bytes | `05be8b9d4b71c2f865683c4cf6d498b0997ad6108681414ae2e29f88ad37b87b`; sole frame-19599 image-to-court map |
| Sealed preregistration | `docs/evidence/tracking/g258_synthetic_truth_validity_artifact/g258_preregistration.json` | 4,198 bytes | `08caf0c869c62583b7c55afdf7b5ed250644eaf9351d3f9ca28ecd4387537b41`; committed before scoring in `15e123bddb7651c78e45cb2f243dbe0130db9854` |
| G247 route exercised | `scripts/platformkit/tracking/g247_projected_quad_validity.py` | 17,235 bytes | `369312e8315a787c68aacd081c88fada66c66653ac462023eef46808e3faaa3a` |
| G248 route exercised | `scripts/platformkit/tracking/g248_projected_line_image_agreement.py` | 15,369 bytes | `3774ea0c1bf881e77f9c85b843dd22c2bb1a679e3489718643d6f6721829d29a` |
| G252 route exercised | `scripts/platformkit/tracking/g252_projection_accuracy_in_pixels.py` | 14,196 bytes | `df16ab790d863b35989460f80e06f134de03864e38a4e55d8d50a655439ce866` |
| G258 route exercised | `scripts/platformkit/tracking/g258_synthetic_truth_validity.py` | 14,818 bytes | `d8c9ef8fa9b739b88714446e75963ea4a3f41145a93c04d8ae8f3615f42fa91d` |

The route was streamed to `python3 -` on the pod; no code was deployed there. The committed [measurement artifact](g258_synthetic_truth_validity_artifact/g258_measurement.json) is 78,738 bytes with SHA-256 `eae1b67bb151893a3b5aaf6595c33a04d74f0b3e3070e3c589d1e3ce8fa05dd5`.

## Sealed ladder and detection declaration

The full declaration is [g258_preregistration.json](g258_synthetic_truth_validity_artifact/g258_preregistration.json), sealed in the commit above before any G258 ladder metric was run. Let `H` be the persisted G247 frame-19599 image-to-court matrix and `P = inverse(H)` be its court-to-image projection. For rung `N`, G258 uses G257's projected-court displacement definition:

```text
P_N = T(N, 0) P
H_N = inverse(P_N)
```

`T(N, 0)` translates image coordinates `N` pixels camera-right. Thus every finite projected court point moves exactly `N` horizontal image pixels. The fully enumerated ladder is 0, 2, 5, 10, 20, 40, and 100 px; 0 px is the unperturbed control. This is a defined uniform image-plane overlay/matrix stimulus, not an assertion that real calibration error is uniform or horizontal.

Before scoring, G258 declared a signal detected only when its five-repeat median is farther from the 0-px median than `max(3 * control range, practical floor)` and all five rung values lie strictly outside the control min-to-max interval in one direction. Floors are 1.0 px for offset p90, 1.0 gradient unit for edge contrast, 1.0 grayscale unit for marking contrast, 0.01 for agreement/coverage/shape fractions and ratios. This is a fixed sensitivity declaration, not a production threshold; no ladder accuracy is calculated or reported.

The following match-derived values are **mathematically inapplicable** and were not measured: match count, inlier count, inlier ratio, and match RMS reprojection error. The image feature matches and their fitted correspondence residual do not change when only the already-persisted matrix is perturbed after matching. This structural invariance explains why a matrix-only error cannot be detected by G244's match diagnostics; it is not merely another empirical negative.

## Every-rung projection measurement

G252 offset uses its unchanged Canny definition: low/high 50/150, 3x3 aperture, L2 gradient, 4-px projected sampling, and integer local-normal search from -24 through +24 px. `Found` is conditional on a candidate within that bound; `No candidate` is retained, never imputed. G248 uses its unchanged 3-px and 9-px two-sided perpendicular controls, `LSD_REFINE_STD`, 4-px distance, and 15-degree unoriented tangent tolerance.

| Rung px | Offset median / p90 / max px | Found / no candidate / at 24 px | Edge response | LSD agreement | Marking contrast | Coverage |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 5.0 / 18.0 / 24.0 | 1775 / 13874 / 34 | -51.244564 | 0.047662 | -112.497407 | 0.304319 |
| 2 | 5.0 / 18.0 / 24.0 | 1759 / 13890 / 31 | -51.263184 | 0.047821 | -112.469308 | 0.304329 |
| 5 | 5.0 / 18.0 / 24.0 | 1763 / 13886 / 35 | -51.106544 | 0.048106 | -112.318314 | 0.304343 |
| 10 | 5.0 / 18.0 / 24.0 | 1770 / 13885 / 30 | -50.086266 | 0.048664 | -112.177901 | 0.304425 |
| 20 | 5.0 / 19.0 / 24.0 | 1765 / 13896 / 43 | -49.170048 | 0.049570 | -111.967198 | 0.304532 |
| 40 | 5.0 / 19.9 / 24.0 | 1762 / 13914 / 41 | -48.369915 | 0.049777 | -111.749456 | 0.304808 |
| 100 | 5.0 / 18.0 / 24.0 | 1652 / 14112 / 18 | -50.397621 | 0.048469 | -107.622308 | 0.306374 |

G247 quad checks, with the fixed role order and `[0,1,3,2]` perimeter convention, are below. `convex`, `winding`, and `order` are respectively True/False/True at every rung. The same 31,388 to 31,608 G248 on-curve samples and 6,946 LSD segments were used at every rung; its control sample count rises from 21,023 at 0 px to 21,757 at 100 px through in-bounds clipping.

| Rung px | Signed area px2 | Area ratio | Bbox aspect | Outside fraction | Matrix condition |
|---:|---:|---:|---:|---:|---:|
| 0 | 161745.000 | 1.000000 | 1.939394 | 0.000000 | 12713.866 |
| 2 | 161745.000 | 1.000000 | 1.939394 | 0.000000 | 12688.098 |
| 5 | 161745.000 | 1.000000 | 1.939394 | 0.000000 | 12650.106 |
| 10 | 161745.000 | 1.000000 | 1.939394 | 0.000000 | 12588.556 |
| 20 | 161745.000 | 1.000000 | 1.939394 | 0.000000 | 12472.142 |
| 40 | 161745.000 | 1.000000 | 1.939394 | 0.000000 | 12266.428 |
| 100 | 161745.000 | 1.000000 | 1.939394 | 0.000000 | 11872.942 |

The invariant shape result is expected: rigid image translation preserves signed area, aspect, convexity, winding, corner order, and corner in/out status for this seed. The condition number decreases monotonically because a translated homogeneous matrix has a different numeric representation; it is reported as G247 retained context, not a shape-resolution claim.

## Resolution, monotonicity, and censoring

| Predeclared scalar | Spearman rho over rung medians | Nondecreasing | Smallest detected px | Saturation / result |
|---|---:|---|---:|---|
| G252 pooled found-distance p90 | 0.490 | No | 40 | P90 is 19.9 at 40, a 1.9-px change above the 1.0-px floor. Its p90 never reaches 24, so the 40-px detection is not a saturated p90. |
| G248 edge-response contrast | 0.750 | No | 10 | -50.086266 at 10 differs from -51.244564 control by 1.158298 gradient units. No fixed measurement ceiling. It reverses by 100 px, so it is not globally monotone. |
| G248 marking contrast | 1.000 | Yes | 100 | The first change beyond its 1.0 grayscale-unit floor is at 100 px. No fixed measurement ceiling. |
| G248 LSD agreement | 0.786 | No | none | All changes are below the 0.01-fraction floor. No fixed measurement ceiling. |
| G248 coverage | 1.000 | Yes | none | The 0.002055 total change is below the 0.01-fraction floor. No fixed measurement ceiling. |
| G247 area ratio, aspect, outside fraction | undefined, undefined, undefined | invariant | none | Exactly invariant; not saturated, simply insensitive to this translation. |

The 24-px censoring constraint is material. At every rung, offset `max` is 24 px and 18 to 43 found samples sit at that bound, so individual maximum-distance observations are right-censored from the start and cannot be used as a detection signal. The method cannot distinguish a true 24-px normal miss from any larger miss. The selected pooled p90 stays below 24 at every rung, so it does not saturate in this experiment; its 40-px result is therefore an unsaturated, detector-conditioned p90 separation, not a statement about uncensored error. A 100-px horizontal matrix displacement does not imply every local normal offset is 100 px, and nearest Canny edges need not be the semantic painted marking.

**Machine versus eye:** the earliest G258 signal result is 10 px for edge-response contrast, versus G257's 20-px eye-gate resolution on its one amateur frame. On these different one-frame instruments, the machine signal resolves a known uniform displacement at half the eye stimulus. It did not resolve 5 px here. This is not a production validity gate and cannot be transferred to an unknown map, another frame, or a real calibration error.

## Verification and limits

Focused test run after the final source:

```text
python -m pytest scripts/platformkit/tracking/test_g258_synthetic_truth_validity.py -q -p no:cacheprovider
2 passed in 2.09s
```

No full test suite ran. A7: the preregistration and measurement artifact named here exist. B1: all 7 predeclared rungs and all 5 repeats per rung are retained; no rung, no-candidate record, censored maximum, or failed scalar is removed. B2-B6: no production schema, lifecycle, deployment, reader field, or module move changed. B7: this is the complete pre-enumerated seven-rung decision set, not a head slice. B8: no residual against the four seed labels is offered as evidence; the matrix is held fixed and signals read independent source-image structure. B9: every denominator is named. B10: G247/G248/G252 definitions and the sealed ladder/declaration are unchanged. Q does not apply to this tracking measurement. A12 does not apply: G258 adds new 211-line and 25-line files and does not grow an allowlisted file.

**NOT VERIFIED:** a known-correct 0-px map; any different seed, frame, clip, arena, camera, sport, or real calibration-error field; semantic identity of a nearest Canny edge; uncensored normal offsets above 24 px; a trained validity model; any production threshold or gate; automatic calibration, tracking accuracy, or player accuracy; and population-level machine or eye resolution. The 0-px control is only as good as the G233d seed, whose eye certification is itself limited to roughly 20 px by G257. A synthetic uniform translation is not a real calibration error, which can distort non-uniformly across the image. Detecting a known displacement from a known start is strictly easier than validating an unknown map.
