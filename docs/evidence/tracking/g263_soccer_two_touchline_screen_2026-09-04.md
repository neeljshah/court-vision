**SCREEN: 0 / 1,195 samples show a usable centre circle, halfway line, far touchline, and near touchline together; 2 / 1,195 show exactly three, both with the near touchline missing; 0 have the centre circle missing, 0 have the halfway line missing, and 0 have the far touchline missing (n=1 pod clip, 1 labeller).** No qualifying frame exists, so this is a full successful closure before a fit.

# G263: Soccer Two-Touchline Screen

**Verdict: CLOSED AT LIMIT (no two-touchline configuration; full success).** This measurement-only result executes [G263](specs/G263_spec.md) and follows [the verifier contract](VERIFIER_CONTRACT.md). It re-screens only G259's landed 1,195-sample survey. No production module, `IMAGE_SPACE`, coordinate contract, threshold, label, pitch model, corpus source, daemon, `src/`, or `domains/` file changed.

## Pod lane, source, and disk guard

The complete remote executable-and-argument listing was checked first. The checker `ps` (PID 3045969), its parent `sshd` (PID 3045958), and this lane's connection were excluded. An unrelated active `python3 -` lane (PID 3044075) and all resident daemons were left untouched; the specified two-lane capacity therefore left a slot for this bounded screen. No process, including any G260 work, was interrupted.

The source named by the committed survey was read-only identity-checked before the probe:

| Field | Measured value |
|---|---|
| Source | `/workspace/nba-ai-system/data/footage_corpus/soccer__soccer_Z6NTDyxcODs.mp4` |
| Bytes | 2,341,768,743 |
| SHA-256 | `7e4c123f91eb7e096ae2a018482818929b000c9bc2b8b9ca47b542b61ba8c55e` |
| Video stream | 1920x1080, 30/1 fps, 179,250 frames, 5,975.000000 s |

`df` was not used. `du -sm /workspace/nba-ai-system/data` was 33,201 MB. The required `dd if=/dev/zero of=/workspace/nba-ai-system/data/footage_bridge/.g263_disk_probe.bin bs=1M count=1 conv=fsync status=none` probe wrote and verified exactly 1,048,576 bytes, then removed that exact probe. No corpus source or either abandoned `footage_bridge` partial was touched. Bytes freed: 1,048,576 (the probe only).

## Committed-survey re-screen

The screen used all twelve chronological 192x108 G259 panels and their mapping in [survey_manifest.json](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_manifest.json), not a fresh decode or survey. The denominator is every one of the 1,195 five-second samples. A feature was counted only when visibly usable; a partially occluded line could qualify, but an absent line could not.

| Visible usable features | Samples |
|---|---:|
| Centre circle + halfway line + far touchline + near touchline | 0 |
| Halfway line + far touchline + near touchline; centre circle missing | 0 |
| Centre circle + far touchline + near touchline; halfway line missing | 0 |
| Centre circle + halfway line + near touchline; far touchline missing | 0 |
| Centre circle + halfway line + far touchline; near touchline missing | 2 |

The two three-of-four records are samples 36 and 37 (180 s and 185 s). Neither is a candidate for the two-touchline solve: both retain the far touchline but crop the near touchline. G256b's committed native [frame 5400](g256b_soccer_line_conic_calibration_2026-09-04_artifact/best_available_frame_5400.jpg), which is sample 36, confirms the panel reading at 1920x1080: the centre circle and halfway line are present, the far touchline is present at the top of the field, and the near touchline is out of frame. Thus a low-resolution panel impression did not admit any all-four candidate; there was no candidate requiring a new native-resolution acceptance check.

All remaining samples lack at least two of the four required features. The twelve retained panels are the full non-head-slice evidence set: [01](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_01.jpg), [02](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_02.jpg), [03](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_03.jpg), [04](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_04.jpg), [05](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_05.jpg), [06](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_06.jpg), [07](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_07.jpg), [08](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_08.jpg), [09](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_09.jpg), [10](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_10.jpg), [11](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_11.jpg), and [12](g259_soccer_penalty_area_seed_2026-09-04_artifact/survey_panels/survey_panel_12.jpg).

## Required stop and limitations

With zero qualifying samples, the two-touchline configuration named in G262's correction does not occur on this 1,195-sample grid. There is no legal input to verify the two-touchline DOF accounting on an image, and no identity crop, homography, width, Laws-range plausibility check, conic fraction, image angle, condition number, residual, independent penalty-box/goal-area/arc gate, or eye-gate verdict is claimed. No fit was run. A fit residual would not be independent evidence in any event, and a future eye PASS would bound error only at approximately the 20-pixel eye-gate resolution.

This closes hand-fitted standard-geometry calibration for this soccer clip across five independent screens: G256b's two-line-plus-conic configuration, G259's rectangles, G261's box edges, G262's one-touchline gauge, and this two-touchline screen. The conclusion is about this broadcast's camera plan, not soccer generally: the corpus contains one soccer clip. It consumes manual geometry if a legal configuration is ever present and is not automatic calibration (still 0/17). A future width inside the Laws' 64-75 m range would be only a plausibility check, not a measurement of the pitch.

## Contract self-check

A7: every on-tree path named above exists. B1: all 1,195 chronological samples remain in the named denominator; the 1,193 with fewer than three visible features are not excluded. B2-B6: no schema, reader, lifecycle, deployment, production module, or module move changed. B7: all twelve chronological panels are retained, not a head slice. B8: no self-fit quantity is presented as independent evidence. B9: the denominator is source survey samples, not recycled identities. B10: no threshold, bar, coordinate contract, `IMAGE_SPACE`, label, pitch model, or G253 harness setting moved. Q does not apply to this tracking measurement row. No harness was added, so no per-file test or A12 allowlist adjustment applies.

**NOT VERIFIED:** an unsampled instant between G259's five-second samples; a two-touchline DOF derivation on a usable image; fitted line or conic identity; a soccer homography; pitch width, length, or coordinates; a Laws-range plausibility check; conditioning; residual; withheld-geometry render or eye gate; G252 offsets; propagation; detection; tracking; manual-label reliability; automatic calibration (still 0/17); or production behavior.
