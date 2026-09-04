**CONTROL GATE: PASS (n=1 WNBA frame, 1 labeller).** The lines-only control reproduces the known G233d court on unused near three-point and sideline geometry; its shared-in-frame projected-court discrepancy from the published map is 2.849 px median, 3.992 px p90, and 4.344 px max.

**AMATEUR GATE: PASS (n=1 amateur frame, 1 labeller).** With the far sideline, centre line, and centre circle fitted, the unused left-end three-point arc and painted-end geometry visibly agree with the projected assumed high-school-style court; this is one-frame eye evidence only.

# G253: Line and Conic Calibration

This measurement-only landing follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It changes no production code, existing label, threshold, court-model key, coordinate contract, matcher, corpus source, `src/`, or `domains/` file. The manually fitted residual is an optimisation diagnostic, not gate evidence. As G242, G244, G247, and G248 established, matches, inliers, ratio, RMS, quadrilateral shape, and a line/conic residual do not establish a correct court: only the independent-geometry renders above are used for the gates.

## Lane check and disk guard

At the start of the pod measurement on 2026-09-04 America/Chicago, the exact executable-and-argument lane check excluded G253 and its checker. G252 on `C:/Users/neelj/nba-track-a5` was the permitted other lane and was not interrupted; its process had exited before the corrected check completed. An earlier broad check caught the G253 launcher itself and is expressly not relied upon as lane evidence.

`df` was not used. Before writing any G253 evidence, the binding pod guard recorded `du -sm /workspace/nba-ai-system/data` as 33,108 MB, wrote the 1,048,576-byte `/workspace/nba-ai-system/data/footage_bridge/.g253_disk_probe.bin` with `dd ... conv=fsync`, and removed it successfully. All frame decodes were streamed from `ffmpeg` into memory. No corpus source, and neither abandoned `footage_bridge` partial, was deleted or changed. The only freed temporary bytes are the 1,048,576-byte probe; retained JPEGs, crops, JSON, and renders are committed evidence.

## Binding WNBA lines-only positive control

| Input | Measured identity |
|---|---|
| Source | `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4` |
| Bytes / resolution / decoded frames | 2,931,985,407 / 1920x1080 / 174,430 |
| Source SHA-256 | `f361ad7a32ccc6d98ae8e98eee0b090f5e121f9425182e24a31c282ca226c678` |
| Frame | zero-based 19599, exact no-input-seek decode, scale 1.0 |
| Native BGR SHA-256 | `686c94a7738c3e1ede2b39ea98cb09f096eead96826ff543baf4585d4c8f4270` (matches G233d) |

The control used four newly recorded named line correspondences: near baseline, both lane boundaries, and near free-throw line. Their endpoints lie along the marks rather than at G233d's published corners; the complete pre-fit input is [control_line_inputs.json](g253_line_and_conic_calibration_2026-09-04_artifact/control_line_inputs.json). The centre circle is outside this hoop-end crop and was not used. The normalised line design condition number is 2.930; the singular values are retained in [control_measurement.json](g253_line_and_conic_calibration_2026-09-04_artifact/control_measurement.json).

The [lines-only render](g253_line_and_conic_calibration_2026-09-04_artifact/control_lines_only_render.jpg) and [published-G233d render](g253_line_and_conic_calibration_2026-09-04_artifact/control_published_render.jpg) are rendered on the same exact [seed frame](g253_line_and_conic_calibration_2026-09-04_artifact/control_seed_frame_19599.jpg). The court-model discrepancy is reported in image pixels, not as a raw matrix difference: all 634 projected samples have median 12.616 px, p90 280.218 px, max 12,807.051 px because most of that full-court model lies outside this hoop-end image. The 231 samples that both maps project inside the 1920x1080 frame have median 2.849 px, p90 3.992 px, max 4.344 px. That shared-in-frame quantity describes the visible render comparison; it is not a new bar.

The gate uses geometry withheld from the line fit: the near three-point curve and visible sideline. Both visibly follow their painted marks in the two control renders. The fitted baseline/lane/free-throw lines are inputs and are not gate evidence. This passing control permits, but does not validate, the conditional amateur experiment.

## Conditional amateur line-plus-conic fit

| Input | Measured identity |
|---|---|
| Source | `/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4` |
| Bytes / SHA-256 / resolution | 24,523,745 / `773e77669a8876c0c8807baa8f733530ed00413f989cdec49ca078229b9e1bea` / 1280x720 |
| Frame | zero-based 540, selected from G250's best set |
| Native BGR SHA-256 | `2fabad9a2d8e17e851446ae3bef98d9c4fc138ac7b9d80988a1086dfaeb2d31a` |

`ffprobe` container metadata reports 3,729 frames, whereas a complete no-seek `ffmpeg` decoded-frame pass reports 3,601. The latter matches G249/G250 and is the count used here; the source identity is fixed by the matching byte size and SHA-256.

Before fitting, the identity record and three required enlarged crops were committed: [far sideline](g253_line_and_conic_calibration_2026-09-04_artifact/amateur_identity_crops/far_sideline_zoom.jpg), [centre line](g253_line_and_conic_calibration_2026-09-04_artifact/amateur_identity_crops/centre_line_zoom.jpg), and [centre circle](g253_line_and_conic_calibration_2026-09-04_artifact/amateur_identity_crops/centre_circle_zoom.jpg). Their named markings and occlusion caveat are stated in [amateur_pre_fit_identity.json](g253_line_and_conic_calibration_2026-09-04_artifact/amateur_pre_fit_identity.json), before the fit inputs in [amateur_fit_inputs.json](g253_line_and_conic_calibration_2026-09-04_artifact/amateur_fit_inputs.json).

The row-local assumed model is an 84x50-ft, 12-ft-lane high-school-style court, with centre line `y=42 ft` and centre circle radius 6 ft. It is an assumption for this one render, not a physical measurement and not a new `court_points_for_sport` key. The fixed, seeded 64-start solver uses exactly two normalised line correspondences plus one conic correspondence. It is not automatic calibration.

## Degeneracy check and independent render gate

The image-space angle between the fitted far sideline and centre line is 87.600 degrees, so they are not near-parallel in this frame. The single-labeller visible circumference estimate is 0.58: the left and lower arcs and short upper/right segments are visible, while the logo and players obscure the rest. The final objective Jacobian condition number is 40.369. These diagnostics do not cross a newly invented threshold; together they show a finite, non-singular configuration rather than a line-parallel or wholly unobserved-conic degeneracy. The fitted residual is 0.004510 and has no validation meaning. All values and the fitted map are in [amateur_fit_measurement.json](g253_line_and_conic_calibration_2026-09-04_artifact/amateur_fit_measurement.json).

The [amateur render](g253_line_and_conic_calibration_2026-09-04_artifact/amateur_line_conic_render.jpg) is judged on geometry not used in the fit: the left-end three-point arc and painted-end markings. They visibly agree with the projection. The far sideline, centre line, and centre circle are fitted inputs and are not evidence. No label was adjusted, no alternative model was tried after this gate, and no propagation, detector projection, or production change follows.

## Verifier self-check and NOT VERIFIED

A7: every memo-linked evidence path exists in this commit. B1: both denominators are fully named one-frame eye gates; no failed frame was excluded. B2-B6: no schema, lifecycle, deployment, production module, or move changed. B7 is inapplicable to the explicitly one-frame control and one-frame conditional test, not a sampled head slice. B8: neither fitted line/conic residual nor fitted inputs are presented as independent evidence. B9: no recycled metric denominator is claimed. B10: no bar, threshold, matcher setting, coordinate contract, label, or court-model key changed. Q does not apply to this tracking measurement row. The focused test is `python -m pytest scripts/platformkit/tracking/test_g253_line_conic_calibration.py -q -p no:cacheprovider` and passed `3 passed`; both new Python files are below 300 LOC, so A12 requires no allowlist change.

NOT VERIFIED: automatic calibration (still 0/17; hand-fitted lines and conic are no more automatic than hand-fitted points); physical 84-versus-94-ft dimensions, lane width, circle radius, or camera model; any population claim beyond one control and one amateur frame; repeatability or blind-agreement of this one labeller (the programme has not cleared 80 percent on its measured criteria); player/detector/tracking accuracy; propagation across frames; or correctness of the assumed amateur court model. G246 remains controlling: repeatable manual geometry can be uniformly wrong. Plausibility is necessary, never sufficient.
