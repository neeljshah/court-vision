**GATE: FAIL BEFORE FIT (n=1 pod clip, 1,195 chronological five-second samples, 0 four-edge, 0 three-edge, and 2 two-edge cases; 0 fitted frames; 1 labeller).** No sampled frame supplies all four identity-safe painted penalty-box edges, so no homography, self-fit residual, degeneracy value, withheld-geometry render, or offset is presented.

# G261: Soccer Penalty-Box Edge Re-screen

This measurement-only landing executes [G261](specs/G261_spec.md) and follows [the verifier contract](VERIFIER_CONTRACT.md). It changes no production module, `IMAGE_SPACE`, coordinate contract, label, threshold, pitch model, corpus source, daemon, `src/`, or `domains/` file. It retains G259's corner-survey negative: it changes the screen from complete rectangle corners to visible painted edges, not the source, cadence, or coordinate model.

## Lane, source, and disk guard

Before the pod measurement, I used an executable-and-complete-argument process check that excluded this checker, its parent, and the launching shell. It found only resident daemons and the foundry runner; no G260/G261 measurement command was active, and no process was interrupted. The named source was opened only over SSH on the pod; the local corpus was not opened or compared.

| Field | Measured value |
|---|---|
| Source | `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4` |
| Bytes / SHA-256 | 2,341,768,743 / `7e4c123f91eb7e096ae2a018482818929b000c9bc2b8b9ca47b542b61ba8c55e` |
| Video stream | 1920x1080, 30/1 fps, 179,250 declared frames, 5,975.000000 s |
| Pod data usage before probe | `du -sm /workspace/nba-ai-system/data` = 33,170 MB |
| Binding probe | `dd if=/dev/zero ... bs=1M count=1 conv=fsync` created 1,048,576 bytes, verified it, then removed it |

`df` was not used. All decodes were streamed: one initial foreground attempt was discarded when its command wait ended before a reusable payload, then one bounded hidden SSH stream returned only 62 preselected JPEGs to the local evidence tree. No corpus source or either abandoned `footage_bridge` partial was deleted or changed. Temporary bytes freed: 1,048,576 on the pod (probe), 6,291,475 local (selected-frame raw stream), and 5 local process-metadata bytes, for 7,340,056 total. The raw stream was split into retained evidence images before removal.

## Reused G259 survey and edge count

The denominator is every one of G259's 1,195 chronological samples at five-second stride, represented by its committed [manifest](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_manifest.json) and twelve chronological panels. This is a re-screen of that committed survey, not a new survey. A usable edge is an actual painted penalty-box segment visible at native 1920x1080 resolution whose identity does not rely on a player occlusion, goal/net edge, or extension beyond paint. It can be short; a visible corner is not required.

| Usable penalty-box edges in a sample | Count | Native-confirmed sample IDs |
|---|---:|---|
| 4 | 0 | none |
| 3 | 0 | none |
| 2 | 2 | 111 (frame 16,650, 555 s); 746 (frame 111,900, 3,730 s) |
| 0 or 1 | 1,193 | every other sample ID from 0 through 1,194 |

The machine-recomputable count and explicit complement are in [rescreen_measurement.json](g261_soccer_penalty_box_lines_2026-09-04_artifact/rescreen_measurement.json). Its [native-confirmation boards](g261_soccer_penalty_box_lines_2026-09-04_artifact/native_confirmation_board_1.jpg) and [second board](g261_soccer_penalty_box_lines_2026-09-04_artifact/native_confirmation_board_2.jpg) index the panel-triaged native checks. Those boards are not an alternative denominator and never promote a low-resolution panel line directly into a fit.

Native frame 16,650 has actual partial penalty-box paint and an arc, but no identity-safe goal line; native frame 111,900 has goal-end paint and an arc but its goal-line identity is obscured by the goal/players. The visible goal/net strokes in both are excluded rather than extended into a painted goal line. Thus neither frame has four fitted inputs, and there are deliberately no per-line identity crops: G246 requires those crops for every *fitted* line, and no line was fitted.

## Four-line model, fit stop, and degeneracy

The only admissible four-line world model would have been goal line `y=0`, penalty-area front `y=16.5 m`, and side edges `x=-20.16 m` and `x=+20.16 m`. Those dimensions are fixed by rule and do not depend on pitch length or width. They were recorded but not fitted: no touchline, pitch length, or pitch width was assumed.

The local, un-deployed helper [g261_soccer_penalty_box_lines.py](../../../scripts/platformkit/tracking/g261_soccer_penalty_box_lines.py), SHA-256 `35cec254c8176e772f08fb4dd5cb3e219f20202f39b0d6dcf93de5d98e62291a`, supports an exact four-line dual-homography solve, image-line angles, and the two parallel-pair vanishing points. It was not invoked on a substitute or incomplete configuration.

| Required degeneracy item | Result |
|---|---|
| Goal-line/front-edge image vanishing point | NOT MEASURED: goal line is not an admissible fitted input. |
| Side-edge image vanishing point | NOT MEASURED: no four-edge configuration exists. |
| Angles between fitted lines | NOT MEASURED: no fitted lines. |
| Any three near-concurrent | NOT MEASURED: no four-line system. |
| Four-line design condition number | NOT MEASURED: no system was solved. |

This is an explicit pre-fit degeneracy/configuration stop, not a silent fit of an edge-on or incomplete box. A short observed segment would extrapolate across the image, where small angular error grows with distance; because no four observed segments exist in one sample, no such extrapolation is claimed.

## Independent gate and withheld measurement

The leading FAIL is pre-fit. A withheld penalty arc, goal-area line, centre circle, or halfway-line render requires a legal map first; generating one from only two edges would fabricate independent evidence. Consequently no fit residual is offered, G252's normal-search offset method was not run, and soccer median/p90 values are NOT MEASURED. G252's WNBA reference remains median 5 px and p90 19 px, but there is no soccer PASS to compare. Had there been a PASS, it would bound error only at roughly G257's 20-pixel eye-gate resolution, not certify correctness.

## Verification and limitations

Focused tests run:

```text
python -m pytest scripts/platformkit/tracking/test_g261_soccer_penalty_box_lines.py -q -p no:cacheprovider
5 passed in 3.55s
```

The helper is 140 lines and its test is 58 lines, below the 300-line rail; A12 needs no allowlist change. A7: every evidence path linked above exists. B1: the denominator is all 1,195 G259 survey samples and the 1,193 complement is named. B2-B6: no schema, lifecycle, deployment, production module, or move changed. B7: all twelve chronological panels, not a head slice, remain the survey evidence. B8: no self-fit residual or fitted element is presented as independent evidence. B9: the unit is an unrecycled source sample. B10: no bar, threshold, coordinate contract, `IMAGE_SPACE`, pitch model, or G259 survey setting changed. Q does not apply to this tracking measurement row.

**NOT VERIFIED:** a soccer homography; per-line identity crops (none fitted); vanishing points, angles, concurrence, or condition number for a legal configuration; a withheld-geometry render; G252 offsets; propagation; coverage; detection; tracking; coordinate output; pitch length or width; manual-label reliability; or any production change. This is one clip, the re-screened 1,195-sample grid, and one labeller. It consumes manual geometry only when a legal input exists and is not automatic calibration, which remains 0/17. Hand-fitting lines is no more automatic than hand-fitting points.
