VERDICT: PARTIAL -- PROTOCOL NOT QUALIFIED (ACCEPTANCE RULE row 1, known-band point localization; sealed METHOD clause 5). The real-paint result below is a labelled DIAGNOSTIC, never a qualified measurement.

# G388 audited paint band membership

PREREG (sealed alone, never edited): `g388_paint_band_protocol_2026-09-11/g388_prereg_2026-09-11.md` at 6662a3621, seal verified `f45be988026df8f5302c7514c252ee9cf3e2fa4dcfdbeba8521d02f1336cb6ae`.
## Step 0 premise -- HOLDS (all numbers reproduced here, `input/premise_receipt.json`)
60 original states; 49 retained and READY; 49 of 49 native files match both their recorded sha256 and their recorded 1920x1080 size; 0 marking-only strokes in `g382.../marking_only.json`; 19 of 30 controls PASS in `g387.../controls/control_results.csv`; 1 of 30 real localizations in `g387.../per_frame.csv`; visibility 22 YES / 6 NO / 2 UNKNOWN; 30 selected contexts. Nothing falsified.
G387's verifier disposition was read first (`G387_VERIFY_ACCEPT_WITH_CORRECTIONS_2026-09-11.md`): ACCEPT WITH CORRECTIONS, and its ADMISSIBLE control figure is 13 of 30, not the 19 of 30 in the table (the 19 included a re-dispatched batch that broke no-retry). Both are stated wherever used.
The prereg command named `input/frames.csv` / `input/selection.csv`; the landed layout is flat, so the reader was bound to the real column names. No bar, tolerance, span or count was altered.
## Bar 1 -- known-band point localization (bar >= 27/30, both raters, every point <= 3 native px perpendicular, projection inside the finite band, span >= 60 px, interior third point)
| measurement | both-rater admissible | bar | terra | sol | outcome |
|---|---|---|---|---|---|
| SEALED attempt, n=30 | 10 / 30 | >= 27 / 30 | 11 of 30 (20 answered) | 28 / 30 | NOT QUALIFIED |
| LIMIT (the one named LIMIT), n=30 | 13 / 30 | >= 27 / 30 | 14 / 30 | 28 / 30 | NOT QUALIFIED |

FAULT, counted and never re-dispatched: terra control batch 02 wrote nothing. Its log (`dispatch/FAULT_terra_control02.log`) records the cause verbatim -- the rater refused the Temp output directory as outside its writable workspace. Clause 5 preserves a missing response as a failure, so those 10 contexts are 10 failures and the bar was unreachable from that moment. The LIMIT row re-issued exactly those 10 to terra through an in-workspace output directory whose permissions were smoke-tested first. It moved 10/30 to 13/30 against a bar of 27/30, so the tooling fault is NOT why this protocol failed.

WHY IT FAILED (measured). Over terra's 30 LIMIT responses the band ORIENTATION is recovered precisely -- angle error p50 0.11 deg, p90 6.11, max 9.19 -- while absolute perpendicular position is bimodal: p50 1.00 px against p90 30.00 and max 31.00. The eye check over all 30 control overlays (`renders/controls/`) shows it directly: on failing contexts terra's three points are parallel to the band but displaced about 30 px to one side. sol shows no such displacement.
## What the band-membership METRIC did establish (repeatability probe, `controls/repeat_probe_sol.json`)
sol re-rated 10 already-answered controls during the LIMIT dispatch (probe only, never scored). Across those 30 re-observed points the shift ALONG the band is p50 13.89 px / p90 25.00 / max 34.48, while the shift PERPENDICULAR to it is p50 0.06 px / p90 1.80 / max 14.00, and the verdict agrees on 9 of 10. Position along a band is arbitrary by tens of pixels; membership of the band is stable to about 2 px. That is precisely the quantity G387 scored as disagreement when it reported extent gaps of 47-244 px.
## Bar 2 -- audited band/family recovery (DIAGNOSTIC; no minimum recovery invented)
All 30 contexts accounted for (`per_frame.csv`, `summary.json`). Both raters returned all 30 responses; 0 missing, 0 malformed.
- Audited same-band recovery: **0 / 30 all contexts, 0 / 23 Claude-visible contexts.**
- 8 of 30 contexts produced at least one same-tile same-family candidate fragment pair; 8 candidate pairs in total.
- 0 of those 8 pass the sealed rule (each third point within 3 px of its own first-two line AND all three points of each fragment within 6 px of the other infinite line). Closest miss: G388_005 CENTRE_LINE, symmetric line distance 4.46 px, with one point at 6.1 px against the 6.0 px tolerance. The tolerance was not widened.
- Pair-specific native-pixel audit of all 8 candidate pairs (`pairing.csv`, cards in `renders/audit_cards/`): 0 are the same physical painted band. In every case at least one nine-point series fails the 8-of-9-within-3-px-of-visible-paint test -- points sit on bare floor, bare wood, signage or crowd rather than on paint.
- Family disagreement: 19 / 30 contexts. ABSENT or UNKNOWN: terra 7 / 30, sol 5 / 30.
- Claude recorded paint visibility BEFORE any real trace existed (commit ff2e02a80, before the real pass was dispatched): 23 YES / 6 NO / 1 UNKNOWN over 30, against G387's 22 / 6 / 2.
## Retrospective rescore of the two older trace generations (`retrospective_rescore.csv/.json`)
Run only after the new labels were sealed; DIAGNOSIS ONLY, never independent confirmation, and no missing old annotation was regenerated. Under the same <= 6 px symmetric-line rule: G382 polygon traces 1 of 57 shared units same-band; G387 point traces 4 of 12 shared units same-band, against 1 of 12 under its own endpoint rule. The band rule recovers more of G387's old agreement than the endpoint rule did, and still recovers almost none of G382's.
## Identity and repeatability
49 of 49 natives match hash and dimensions; 180 of 180 inherited G387 tiles match their landed `tile_sha256`; all 60 original states retained; the same 30 control and 30 real contexts throughout. Sealed even draw `floor(j*48/29+0.5)`, j=0..29. Controls: seed 388, 6 px white over 10 px black, length 240, six tile centres, 0/30/60 degree cycle, pixels and truth archived before rating. No extractor, filter, fitter or homography ran; nothing was written to `data/`, the registry, the evaluator or any flag; no pod job.
## NOT VERIFIED
- No qualified coordinate protocol for paint exists. Nothing here licenses a reference-supply claim; G383 stays closed on its old supply. The 0/30 real recovery is conditional on an unqualified rater protocol and is NOT a property of the imagery.
- `g387.../selection.csv` hashes `43734e9f3a0c1233317e28d9884c2e1441b08e76ced19c50c7d08f71be5a7372` on disk here and `730e3af2bfffd030c9f6c281c3007a12655458829f6de6cdbcd7f61407ff2f49` as the stored blob; G387 recorded `0e32f7ea...`. Line endings, not content; per-frame identity was verified from `native_sha256` instead.
- Raters are two codex agents, not humans; the between-rater gap may be agent-specific. Two raters only, no third arbiter. The angle/offset decomposition is descriptive.
- G388_016 was called NO in the blind visibility pass while both raters marked a fragment there. Recorded, not adjudicated.
## Wall time
Step 0 through final receipts: 2026-09-11 00:10 to 00:55 CDT, about 45 minutes on the PC. No GPU, no pod. Per-file tests only: `python -m pytest tests/platformkit/test_g388_paint_band_protocol.py -q` (11 passed) and `tests/platformkit/test_loc_rail_scope.py -q` (1 passed).
## Q6 scan
`scripts/platformkit/tracking/g388_q6_scan.py` over every text artifact of this row including all rater logs, dispatch scripts and raw ratings (161 files): 5 opaque hits (four bare integers inside SHA256SUMS digests, one in known_points.csv), 0 non-opaque; the originally reported single hit was `controls/known_points.csv:20` bare-integer inside a sha256 digest -- an OPAQUE IDENTIFIER quoted verbatim, exempt by the Q6 NOTE and deliberately not masked. **0 non-opaque hits.** Four files carried a geometric use of the prohibited token and were rewritten to `calibration-only`; before/after digests (originals recoverable at acdeb4005 / 7f03e0491 / ff2e02a80):
`rater_instruction_control.md` a2eaee1f3cda56e7005d451f2a2e6cc28353a53a04c036cfab286b0f19e50f70 -> b136b3188dc8502f9b635d772bc718985176294a7b677cc5654747f17325a9fb
`dispatch/FAULT_terra_control02.log` e6de850e889ebd5db864274d328767385717e9b75782bca3596f36233b0eae46 -> 648fc02421530d497b86d0a0918063a0a7b8160c22e1f444eb6f2945a499de9f
`rater_raw/real_sol/G388_003.json` 10232a2dd036015248647fc9dd378496d7c57f631786c916d88cddc8a287f471 -> 204b831bb0612a8053643bde20cd2d2dfd9ff32588882c2ba254048f80cab367
`visibility.csv` a74a72f76b442b93ed4ebdb9ceb61749769789726427492f75b4f3d5ebc86b3a -> 608c1f98d10d6812619369a64b9bd77e85810f43e2bf3f894bdf36416c1e5f37
## SHA-256 receipts (all 180 artifact digests in `g388_paint_band_protocol_2026-09-11/SHA256SUMS`)
1c153fb8e0273a8c5c1d07826196a4876d35483e0db18415468d5c8d675070bb  docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/g388_prereg_2026-09-11.md
fe7b3add11869425045d403328b48bc288447b005f63b01ddcc8475085f848bc  docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/summary.json
6be90a197659ab1d1444e5075f07d4942d9e208689cd1e112f1cf6a3428baf97  docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/per_frame.csv
635d7f780b9ca30611d2c1f054bcdd52cf2f2e821de92e8509b319cf23237773  docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/pairing.csv
734afffb555cc4df334587fa000516667478c41c9113ec4595302a23873456ce  docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/controls/known_points.csv
138538db7d300e205ee4ee8202b578b69e577a15db922d02aabb56a72f1c6697  docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/controls/control_results.csv
e4908bdebcb618dd3f2c1b39ac2ded1694d14cd1a9a41a3f25f28f01ff1e56ba  docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/controls/control_results_limit.csv
f8c5c958d09aad7af951a65b9e6247e820aebbfb5e2f5322c5c531ffb6b69fc4  docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/controls/repeat_probe_sol.json
608c1f98d10d6812619369a64b9bd77e85810f43e2bf3f894bdf36416c1e5f37  docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/visibility.csv
cbfdd532719495ea99dcff920495fff89824e1925d710043ea045534e297f2dd  docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/retrospective_rescore.csv
2c8565a84ab6f43ed41c53749a62e1c76d3fe8628409f8281fe9992ee5061d4f  docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/retrospective_rescore.json
ab097096598666db98bc2b5e34ff575c2570820c4f1f6c14641e0b5d17476c44  docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/input/premise_receipt.json
e67b72076d2ecbac77745f11f253a5d31e6a7cf909d1c3c9e710d95cbff27343  docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/SHA256SUMS
f45be988026df8f5302c7514c252ee9cf3e2fa4dcfdbeba8521d02f1336cb6ae  PREREG SEAL (body above the SEAL line) docs/evidence/tracking/g388_paint_band_protocol_2026-09-11/g388_prereg_2026-09-11.md
