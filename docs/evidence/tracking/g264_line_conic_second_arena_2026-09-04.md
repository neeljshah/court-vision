**COMBINED GATE: NOT RUN / CLOSED AT LIMIT (n=1 clip, 300 chronological survey frames, 0 legal G253 fit frames, 0 ladder boards, 1 labeller).** The required visible centre-circle conic is absent as an identifiable court marking in every sampled frame, so a two-lines-plus-one-conic fit, blind ladder, and withheld-offset measurement would be fabricated rather than a replication.

# G264: NCAA second-arena line-and-conic screen

This measurement-only replication follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It changes no production code, label, threshold, court-model key, coordinate contract, source, `src/`, or `domains/` file. It uses the existing `court_points_for_sport("ncaa_basketball")` contract (`(19,0)`, `(31,0)`, `(19,19)`, `(31,19)`), which is the 94x50-ft court with a 12-ft lane and 19-ft paint depth. No WNBA 16-ft lane was used or added.

## Source, lane, and disk guard

The pod-only source was read over `ssh config.pod` before any decode:

| Field | Measured value |
|---|---|
| Path | `/workspace/nba-ai-system/data/footage_corpus/ncaa_basketball__ncaa_basketball_IB-_u4gW3ds.mp4` |
| Bytes / SHA-256 | 3,580,059,573 / `9b35bd59d8b5b0e04737389b6661d7f8d37fac07a348056b081a6815ff5eea40` |
| Resolution / declared frames / FPS / duration | 1920x1080 / 205,444 / 30000/1001 / 6855.014 s |

The byte count and SHA-256 both match the G264 specification. The exact executable-and-argument process census excluded this G264 process, its checker, and the checker's parent. It found G260 as the permitted other pod lane and did not interrupt it; this is the stated two-lane state.

`df` was not used. Before the streaming survey, `du -sm /workspace/nba-ai-system/data` reported **33,222 MB**. The binding `dd if=/dev/zero .../.g264_disk_probe.bin bs=1M count=1 conv=fsync` probe wrote and then removed **1,048,576 bytes**. No corpus source or abandoned `footage_bridge` partial was changed. The source survey and exact frame extraction streamed over SSH and wrote no pod decode. Pod temporary bytes freed: **1,048,576**.

## Chronological configuration survey

One no-input-seek sequential decode selected every 685th frame, yielding the complete fixed set `0, 685, ..., 204815`: **300 distinct chronological frames**, paginated as 15 320x180-tile contact sheets. I reviewed every tile, not a head slice. A usable configuration required all of these independently identifiable physical markings: far sideline, centre line, a painted centre-circle conic, and far-end lane lines. Curves belonging to the Final Four logo were explicitly not admitted as a court conic.

**Result: 0 / 300 sampled frames offer the required configuration.** Wide broadcast views commonly show the far sideline, centre line, and a far-end key, but the permanent centre logo obscures or replaces the identifiable centre-circle circumference. The full survey inventory and near-miss identity record are [survey_manifest.json](g264_line_conic_second_arena_2026-09-04_artifact/survey_manifest.json); its 15 named sheets are in [survey](g264_line_conic_second_arena_2026-09-04_artifact/survey/).

## Identity-first near-miss check

I extracted the clearest wide surveyed near miss, zero-based frame 129465, through an exact no-input-seek decode. Its retained [source JPEG](g264_line_conic_second_arena_2026-09-04_artifact/candidate_frame_129465.jpg) is 455,153 bytes, 1920x1080, SHA-256 `794a331404ce0607ad26d9062c9efdee371296c1d65d4567357ea57ec2934794`; decoded native BGR SHA-256 is `3d320252581566d5e415604ec8a12a41e565c1efb3b2d372658d704aa6180fd6`.

The pre-fit identity crops are retained even though no fit was permitted:

| Crop | What is visible | Observed portion / consequence |
|---|---|---|
| [far sideline](g264_line_conic_second_arena_2026-09-04_artifact/identity_crops/far_sideline_zoom.jpg) | Physical far court boundary | Broad visible extent, but no endpoint was recorded because the fit prerequisite fails. |
| [centre line](g264_line_conic_second_arena_2026-09-04_artifact/identity_crops/centre_line_zoom.jpg) | Red centre line through the logo | Visible above and below the logo; not used as a fit input. |
| [centre region](g264_line_conic_second_arena_2026-09-04_artifact/identity_crops/centre_circle_zoom.jpg) | Final Four logo artwork | **0.00 identifiable painted centre-circle circumference**. Logo curves are not relabelled as a conic. |

G253's unchanged solver legally requires exactly two line correspondences plus one conic. With no identifiable image conic, its input is absent. Therefore there is no homography, residual, line angle, observed conic fraction for a fit, Jacobian condition number, candidate overlay, blind order, blind verdict, unblind key, discrimination threshold, or G252 normal-offset result. The G264 evidence-only driver was prepared but intentionally not called to fit: `g264_line_conic_second_arena.py` SHA-256 `adb0449d9dd8031073e53436b4751547b455fea03e9928b2a0a228ea592ae27e`.

## Gate interpretation and limits

This is a configuration failure, not a method failure or a negative calibration verdict. It establishes only that this one broadcast/court cannot supply the legal G253 line-plus-conic input under identity-first rules. No bare visual PASS is claimed, and the G257 blind ladder cannot repair an absent candidate. G257's 20-px eye-gate resolution and G252's 5-px median / 19-px p90 WNBA figures are therefore comparison context only; G264 has no discrimination threshold or withheld-geometry offsets to place beside them.

One clip is a replication opportunity, not a population. The NCAA model is assumed from its existing key, not measured from the footage. Hand fitting is not automatic calibration, which remains 0/17. A uniform synthetic displacement is not a real calibration error, which can vary non-uniformly by location and perspective. No second labeller or reliability result is supplied; G246's warning that repeatable labels can be uniformly wrong remains controlling.

## Verifier self-check and NOT VERIFIED

A7: the memo-linked source JPEG, three identity crops, manifest, and survey directory exist in this commit; the manifest names all 15 survey sheets. B1: the `0/300` denominator retains every fixed-stride sampled frame; none is excluded. B2-B6: no schema, lifecycle, deployment, production module, or move changed. B7: the full fixed chronological 300-frame decision set is retained, not a head slice. B8: no self-fit residual is offered. B9: clip, survey-frame, fit-frame, board, and labeller denominators are stated. B10: no threshold, model, coordinate contract, label, or existing harness setting moved. Q does not apply to this tracking measurement. The focused test was `python -m pytest scripts/platformkit/tracking/test_g264_line_conic_second_arena.py -q -p no:cacheprovider` and passed `5 passed`; the driver is 225 lines, so no LOC allowlist change is needed.

NOT VERIFIED: a legal fit on this clip; any candidate map; a blind ladder or its discrimination threshold; withheld image-edge offsets; physical NCAA court dimensions; automatic calibration; a generalisation or arena-specificity conclusion; player or tracking accuracy; any production change; or performance on another frame, camera, arena, or labeller.
