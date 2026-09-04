**GATE: FAIL BEFORE FIT (n=1 pod clip, 1,195 chronological 5-second samples, 0 complete penalty-area rectangles, 0 complete goal-area rectangles, 0 legal two-line-plus-conic fallbacks, 1 labeller).** No sampled image supplies four safely identifiable, unoccluded corners of either standard rectangle, so no homography or withheld-geometry projection exists to render; the retained near-miss is not fitted geometry and does not pass the independent-geometry gate.

# G259: Soccer Penalty-Area Seed Survey

This measurement-only landing follows [the verifier contract](VERIFIER_CONTRACT.md) and executes [G259](specs/G259_spec.md). It changes no production module, `IMAGE_SPACE`, coordinate contract, label, threshold, pitch model, corpus source, daemon, `src/`, or `domains/` file. The source was accessed only over SSH on the pod; the local Windows corpus was not opened.

## Pod lane check, source identity, and disk guard

Before the measurement, the exact remote `ps -eo pid=,ppid=,comm=,args=` listing was reviewed. The checker process (`ps`, PID 3026376) and its parent remote `sshd` process (PID 3026350) were excluded, as was this lane before its helper was launched. The remaining Python processes were named resident daemons or the foundry runner; no G258/G259 measurement command was present. No resident process was interrupted.

The source identity was checked before any decode and matched the spec exactly:

| Field | Measured value |
|---|---|
| Source opened | `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4` |
| Bytes | 2,341,768,743 |
| SHA-256 | `7e4c123f91eb7e096ae2a018482818929b000c9bc2b8b9ca47b542b61ba8c55e` |
| Video stream | 1920x1080, 30/1 fps, 179,250 declared frames, 5,975.014 seconds |

`df` was not used. Before streaming, `du -sm /workspace/nba-ai-system/data` reported 33,158 MB. The pod guard wrote `/workspace/nba-ai-system/data/footage_bridge/.g259_disk_probe.bin` with `dd if=/dev/zero ... bs=1M count=1 conv=fsync`, verified 1,048,576 bytes, and removed it. No corpus source or abandoned `footage_bridge` partial was changed. The only temporary bytes freed were the 1,048,576-byte probe; retained local JPEG evidence was not deleted.

## Five-second survey and configuration counts

The route helper [g259_soccer_penalty_area_seed.py](../../../scripts/platformkit/tracking/g259_soccer_penalty_area_seed.py), SHA-256 `06bf703481498012ff7069e22ac671ee32fce4e38cd5372b06f676b4c5f88524`, ran a whole-clip no-input-seek FFmpeg stream at one sample per 5 seconds. Five seconds was selected because the target views occur in attack/set-piece bursts measured in seconds; the prior 60-second survey could miss an entire burst. The stream produced 1,195 chronological samples at 192x108, assembled as twelve 10x10 low-resolution panels (the final panel has 95 samples). No full decode was written to disk on the pod.

The complete panel/time mapping is committed in [survey_manifest.json](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_manifest.json), with all panels retained: [01](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_01.jpg), [02](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_02.jpg), [03](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_03.jpg), [04](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_04.jpg), [05](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_05.jpg), [06](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_06.jpg), [07](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_07.jpg), [08](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_08.jpg), [09](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_09.jpg), [10](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_10.jpg), [11](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_11.jpg), and [12](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_12.jpg).

For this screening count, a rectangle required all four physical paint-line intersections to be within the image, individually distinguishable, and not occluded at the native-frame confirmation step. A partial box, a goal, a line inferred through a player, or a low-resolution panel impression did not count. The screen was ordered penalty area, goal area, then legal fallback.

| Configuration screened in all 1,195 samples | Count |
|---|---:|
| Full penalty area: four identifiable 16.5 m by 40.32 m rectangle corners | 0 |
| Full goal area: four identifiable 5.5 m by 18.32 m rectangle corners | 0 |
| Legal two-line-plus-conic fallback | 0 |

The panels contain many goal-end and centre-field near-misses, but none clears the stated four-corner identity condition. The exact no-seek native [frame 16650](g259_soccer_penalty_area_seed_2026-09-04_artifact/candidate_frame_16650.jpg), selected from the survey's goal-end near-miss class, and its [zoom](g259_soccer_penalty_area_seed_2026-09-04_artifact/closest_penalty_area_near_miss_zoom.jpg) show a goal, partial penalty markings, and an incomplete/out-of-frame rectangle. No corner pixel is labelled: the crop is a rejected selection record, not an input crop. The exact no-seek [frame 17700](g259_soccer_penalty_area_seed_2026-09-04_artifact/candidate_frame_17700.jpg) is the other retained native confirmation and contains no candidate rectangle. Thus there are no fitted elements and no G246 identity crops to claim; no label was invented from a line extension, goal-net edge, player boundary, or inferred corner.

The eligible dimensions were used only to define the configuration screen, not to fit anything: penalty area 16.5 m depth by 40.32 m width; goal area 5.5 m depth by 18.32 m width; penalty mark 11 m from goal line; and centre-circle radius 9.15 m. No touchline length, pitch width, pitch length, or other non-standard dimension was assumed. Centre-circle/halfway-line views occur, but they provide no legal second line without the prohibited pitch-width assumption.

## Fit, conditioning, and independent-geometry gate

No quadrilateral was admitted to a fit. Consequently, quadrilateral area as an image fraction and the minimum corner-to-other-three-line perpendicular distance are NOT MEASURED rather than silently treating a foreshortened or partial box as non-degenerate. There is no self-fit residual.

The required independent geometry for a gate would have been centre circle, halfway line, penalty arc, or far touchline not used in a rectangle fit. Because no rectangle fit exists, no projected overlay can honestly be rendered against that withheld geometry. This is why the leading FAIL is a pre-fit gate result, not an adverse judgement of a fitted projection. G252's 24-px normal-search offsets are also NOT MEASURED; its WNBA references remain median 5 px and p90 19 px, but there is no soccer PASS to compare. A PASS would bound error at the approximately 20-px eye-gate resolution observed in G257, not certify correctness.

## Verification and limitations

Focused tests run:

```text
python -m pytest scripts/platformkit/tracking/test_g259_soccer_penalty_area_seed.py -q -p no:cacheprovider
4 passed in 1.91s

python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
1 passed
```

The helper is below 300 LOC, so A12 requires no allowlist adjustment. A7: every evidence path named above exists in this commit. B1: the denominator is all 1,195 chronological survey samples; no frame is excluded after a gate failure. B2-B6: no schema, lifecycle, deployment, production module, or move changed. B7: all twelve chronological panels are retained, not a head slice. B8: no residual or fitted element is presented as independent evidence. B9: the denominator is source survey samples, not reused identities. B10: no threshold, coordinate contract, `IMAGE_SPACE`, pitch model, label, or G253 harness value changed. Q does not apply to this tracking measurement row.

**NOT VERIFIED:** whether an unsampled instant between five-second samples has a complete standard rectangle; a soccer homography; any fitted-element identity, conditioning number, residual, or withheld-geometry render; any G252 offset; propagation; coverage; detection; tracking; coordinate output; pitch length or width; manual-label reliability; automatic calibration (still 0/17); or any production change. This is one clip, one 5-second sample grid, and one labeller. It consumes manual geometry only if a valid input appears and is not automatic calibration; G246's uniformly wrong repeatable labels and G257's 20-px eye resolution remain controlling constraints.
