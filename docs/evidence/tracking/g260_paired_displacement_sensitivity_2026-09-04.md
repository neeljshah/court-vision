# G260: Paired within-frame displacement sensitivity

## Verdict

**ACCEPT (measurement only): on 35 pre-enumerated WNBA broadcast frames, G248 coverage first meets the sealed paired criterion at 40 px. Every other measured signal has no reliably detected displacement.** Coverage is consistently positive and monotone, but this is only sensitivity to a known uniform stimulus, not a production gate. Edge response, LSD agreement, marking contrast, and offset p90 are non-monotone; none can be a one-sided gate. Quad quantities remain structurally insensitive.

This replaces G258's invalid zero-variance inference with a within-frame comparison: every frame was measured unperturbed and at each G257/G258 rung, so scene content cancels in each retained difference. Denominator: 35 named frames, one 1920x1080 WNBA clip, one arena, G247 persisted maps, seven rungs, and eight signals. No frames were excluded in the completed run.

## Sealed method, inputs, and disk guard

The [sealed preregistration](g260_paired_displacement_sensitivity_artifact/g260_preregistration.json) was committed before scoring in `41a26840de0a26e070d09bb8b42ef1e92e9fac0c`; SHA-256 `3897bb03c615ffd6f736e08ab74f11f362cc31a3d0dec7a594037f3977f22a40`. It fixes the 35 equally spaced G247 frame identities, `P_N=T(N,0)P`, rungs 0/2/5/10/20/40/100 px, G248/G252/G247 settings, and this criterion: n >= 30, positive finite scaled MAD, absolute median paired difference >= 3 scaled MAD, at least 80 percent strict same-sign pairs, and a same-direction monotone full ladder. No threshold was fit and no accuracy is reported.

The pod-only input was `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes and 1920x1080. It was sequentially decoded once; each named frame stayed in memory while all rungs were evaluated. `du -sm /workspace/nba-ai-system/data` was 33196 MB immediately before the binding 1,048,576-byte `dd conv=fsync` probe, which was removed. The worker temporary JSON was 212,297 bytes and was removed; total bytes freed were 1,260,873. No corpus source, abandoned `footage_bridge` partial, map, label, or production file changed.

The retained [measurement artifact](g260_paired_displacement_sensitivity_artifact/g260_measurement.json) is 610,703 bytes, SHA-256 `c679ada9eae8204d43cbe579ec5852844825d3fbd5aa5bbef6fb9c7f38033f9f`; it stores every per-frame paired series. Route hashes: G247 `369312e8315a787c68aacd081c88fada66c66653ac462023eef46808e3faaa3a`, G248 `3774ea0c1bf881e77f9c85b843dd22c2bb1a679e3489718643d6f6721829d29a`, G252 `df16ab790d863b35989460f80e06f134de03864e38a4e55d8d50a655439ce866`, and G260 `362016e98e4dae9165b27de816bd03b03b4c188a9b76cba33949e2d5953c4cce`.

An initial 18/35-frame partial hit OpenCV's 32767-row `remap` limit on 17 named frames. It is retained as [g260_first_attempt_remap_limit.json](g260_paired_displacement_sensitivity_artifact/g260_first_attempt_remap_limit.json), SHA-256 `d3fb4f200e689b64114ab52f5d820eec0f7b1e19f0154c2bf67ceb4f479ac3e8`. The sole repair chunks the identical interpolation at 30000 points; it changes no route setting, sample, rung, label, map, or criterion. The completed run has 35/35 records and zero errors.

## Paired results

`m` is median displaced-minus-unperturbed paired difference; `s` is scaled MAD; `k` is strict same-sign frames. Every row has n=35 and zero exclusions. `*` means the rung clears the paired effect portion; only the fully monotone coverage series is reliably detected.

| Signal | px | m | s | k | effect |
|---|---:|---:|---:|---:|---|
| Offset p90 px | 2/5/10/20/40/100 | 0/0/0/0/0.700/0 | 0/0/0/1.483/1.038/1.483 | 0/0/0/0/18/0 | none |
| Edge response | 2/5/10/20/40/100 | -0.139/-0.150/0.132/0.677/1.203/0.009 | 0.235/0.434/0.674/0.645/1.897/2.196 | 27/20/20/26/24/19 | none |
| LSD agreement | 2/5/10/20/40/100 | .000059/.000122/.000168/.000387/.000139/-.000011 | .000103/.000242/.000359/.000614/.001020/.001302 | 26/26/24/27/22/18 | none |
| Marking contrast | 2/5/10/20/40/100 | -.026/.045/-.074/.165/.386/2.600 | .116/.363/.588/1.249/2.130/4.660 | 20/18/20/20/19/25 | none |
| Coverage | 2/5/10/20/40/100 | .000009/.000057/.000105/.000216/.000505/.002019 | .000006/.000054/.000085/.000099/.000168/.000727 | 35/35/35/35/35/35 | 40 px * |
| Quad area ratio | 2/5/10/20/40/100 | 0/0/0/0/0/-.000000094 | .000000146/.000000143/.000000143/.000000143/.000000143/.000000147 | 0/0/0/0/0/19 | none |
| Quad bbox aspect | 2/5/10/20/40/100 | 0/0/0/0/0/0 | 0/0/0/0/0/0 | 0/0/0/0/0/0 | none |
| Quad outside fraction | 2/5/10/20/40/100 | 0/0/0/0/0/0 | 0/0/0/0/0/0 | 0/0/0/0/0/0 | none |

Coverage's full ladder is nondecreasing and strictly positive in all 35 frames; 40 px clears `0.000505 >= 3*0.000168`. Its 100-px rung is consistent but does not independently clear its larger spread. Offset, edge response, LSD agreement, and marking contrast reverse or change direction by the top rung. A non-monotone signal cannot be a one-sided gate at any threshold. Quad area/aspect/outside values are invariant up to numerical roundoff.

## Comparison and limits

The smallest paired detection is coverage at 40 px. G257's eye instrument resolved 20 px, but G257 used amateur footage whereas G260 uses WNBA broadcast; the comparison is across footage classes and indicative only. This finding does not show automatic calibration (still 0/17), a known-correct unperturbed map, real calibration-error detection, tracking accuracy, or a production gate. A synthetic uniform translation is not a real non-uniform calibration error. The unperturbed maps are only unperturbed: G257 constrains the eye instrument to roughly 20 px and G252 measured 5 px median / 19 px p90 detector-conditioned offsets.

Focused test: `python -m pytest scripts/platformkit/tracking/test_g260_paired_displacement_sensitivity.py -q -p no:cacheprovider` -> `2 passed`. A7 paths exist; B1 retains all 35 records and the named initial partial; B2-B6 introduce no production schema/deploy/move; B7 is the full pre-enumerated clip-wide sample; B8 has no self-fit residual; B9 names all denominators; B10 leaves methods and bars fixed; A12 does not apply (236-line new route, 41-line test).

**NOT VERIFIED:** a second clip, arena, seed, camera, sport, or real error field; semantic correctness of Canny candidates; uncensored offsets beyond 24 px; a correct 0-px map; a fitted gate or threshold; automatic calibration; tracking/player accuracy; or population-level resolution.
