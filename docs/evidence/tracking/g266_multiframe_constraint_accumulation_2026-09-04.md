# G266: Multi-frame constraint accumulation

**CONTROL VERDICT FIRST: FAIL / CLOSED AT LIMIT (n=1 WNBA shot, 4 transported line constraints, 8 endpoints, 7 shared-in-frame projected-court probe points, 1 labeller).** The accumulated WNBA fit does not reproduce the published G233d map stably enough to authorize the NCAA experiment. Its shared-point median discrepancy is 2.476 px, but p90 is 216.219 px and maximum is 234.542 px. G253's one-frame control reported 2.849 px median, 3.992 px p90, and 4.344 px maximum over 231 shared points of 634. No new numeric pass bar was introduced: the large upper-tail nonreproduction is the control failure. Per G266's binding stop rule, no NCAA frame was opened or fitted, no blind ladder was created, and no withheld-geometry offsets were measured.

This measurement-only closure follows `docs/evidence/tracking/VERIFIER_CONTRACT.md`. It changes no production code, label file, court-model key, coordinate contract, matcher setting, threshold, corpus source, `src/`, or `domains/` file.

## Inputs, machine, disk, and code identity

The only video opened was the read-only pod corpus `/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4`, 2,931,985,407 bytes, SHA-256 `f361ad7a32ccc6d98ae8e98eee0b090f5e121f9425182e24a31c282ca226c678`, 1920x1080, 174,430 frames, 30 fps. Exact no-input-seek frame extractions were retained locally for source frames 19569, 19584, 19599, 19614, and 19629; all are 1920x1080 and their JPEG and decoded-BGR hashes are in [prepare.json](g266_multiframe_constraint_accumulation_artifact/control/prepare.json).

The pod guard was run before writing: `du -sm /workspace` was **36,914 MB**. A 1 MiB `/workspace` `dd conv=fsync` probe passed and was removed. No corpus source, bridge partial, or temporary measurement directory was deleted; known bytes freed are the 1,048,576-byte probe only.

The local measurement route was [g266_multiframe_constraint_accumulation.py](../../../scripts/platformkit/tracking/g266_multiframe_constraint_accumulation.py), SHA-256 `88a295bc247abe44371c61a50cd56a89576ecd93b8c208b968e29df63989fd17`. Its input declaration is [g266_multiframe_constraint_accumulation_inputs.json](g266_multiframe_constraint_accumulation_inputs.json), SHA-256 `215080867532890347cc8672600a409ee54abbe60f60794a3650eea6988f86ad`. It imports G222's matcher unchanged: ORB 2,000 features, `fastThreshold=12`, BF/Hamming, 0.75 ratio test, and `cv2.findHomography` RANSAC at 3 px.

## Identity first, then transport

Every primitive was manually observed in its own source frame and cropped before the valid line-correspondence fit. The observed segment endpoints and the transport matrix/diagnostic are retained in [control_measurement.json](g266_multiframe_constraint_accumulation_artifact/control/control_measurement.json).

| Source frame | Primitive and observed portion | Own-frame crop | G222 matches / inliers / RMS px | Transport assessment |
|---:|---|---|---:|---|
| 19569 | Near baseline: continuous white near-baseline segment between the two visible lane corners. | [crop](g266_multiframe_constraint_accumulation_artifact/control/identity_crops/frame_019569_near_baseline.jpg) | 1174 / 1015 / 0.519 | Strong same-shot transport, but transported rather than direct reference-frame evidence. |
| 19584 | Left lane boundary: continuous left white boundary from baseline toward the free-throw line. | [crop](g266_multiframe_constraint_accumulation_artifact/control/identity_crops/frame_019584_left_lane_boundary.jpg) | 1456 / 1328 / 0.606 | Strong match count/inlier count; RMS is the largest of the four and remains inherited uncertainty. |
| 19614 | Right lane boundary: continuous right white boundary from baseline toward the free-throw line. | [crop](g266_multiframe_constraint_accumulation_artifact/control/identity_crops/frame_019614_right_lane_boundary.jpg) | 1458 / 1334 / 0.380 | Strongest RMS diagnostic, still not an observation in the reference frame. |
| 19629 | Near free-throw line: visible straight horizontal segment across the near key. | [crop](g266_multiframe_constraint_accumulation_artifact/control/identity_crops/frame_019629_near_free_throw_line.jpg) | 1342 / 1191 / 0.435 | Strong transport, but it inherits direct matcher and endpoint-placement error. |

The reference is source frame 19599. The contributing span is frames 19569 through 19629: 60 frames, or 2.0 seconds at 30 fps. There is no observed cut: all five retained frames keep the same wide hoop-end camera view, and direct match counts remain 1174-1458 rather than showing G241b's abrupt cut-style collapse. This verifies continuity only over this short control span, not a general shot detector.

## Accumulated fit and degeneracy

The four observed image lines were transported through the direct seed-to-frame maps into frame 19599 and fitted jointly as four line correspondences by a dual-homography solve. This is a line fit; the endpoint point-correspondence exploratory result was discarded before the valid fit because it was not G253's line-constraint method. The fit residual is deliberately not reported as evidence.

Transport-to-reference image line angles are 2.241, 82.184, 63.660, and 3.024 degrees for baseline, left lane, right lane, and free-throw line respectively. The baseline/free-throw pair is near parallel as expected; their image intersection is about (-21108, -440), while baseline-lane and free-throw-lane intersections land near the four visible paint corners. The normalized endpoint design condition number is 2.786. These finite diagnostics do not prove correctness. They also do not explain away the control failure.

The projected-court discrepancy is computed in image pixels against G233d's published map, on 12 fixed court probe points (four court corners, midcourt endpoints, four near-key corners, and two near free-throw endpoints). **Seven of those 12 points project inside the native 1920x1080 reference frame under both maps**; that seven-point shared set is the named denominator. Results are median 2.476 px, p90 216.219 px, and maximum 234.542 px. The small median with a very large upper tail is not a stable reproduction of the known map. The retained [control measurement](g266_multiframe_constraint_accumulation_artifact/control/control_measurement.json) contains every constraint, transport diagnostic, map, and per-summary denominator.

## Stop, contract self-check, and NOT VERIFIED

The WNBA control fails, so the NCAA clip and G265 frame 129465 were not opened, re-surveyed, labelled, fit, or gated. Accordingly there is no NCAA constraint inventory, NCAA identity crop, NCAA cut check, blind-ladder order/verdict/unblind key, discrimination threshold, or G252 withheld-geometry offset. The 20 px G257 discrimination context and G252 WNBA 5 px median / 19 px p90 remain comparison context only.

The failure shows that this particular accumulated line implementation does not reproduce the published map under its named comparison. It does **not** isolate transport error as the cause: manual endpoint placement and line-only solve sensitivity are also possible contributors. It therefore does not establish that all multi-frame accumulation is impossible. It does cheaply stop this exact proposed NCAA application as required, without tuning, relabelling after a verdict, or a production proposal.

Focused verification was `python -m pytest scripts/platformkit/tracking/test_g266_multiframe_constraint_accumulation.py -q -p no:cacheprovider`, which passed `1 passed`. A7: every memo-linked artifact path exists. B1: all four accumulated constraints and all 7 shared points are named; no failed point was removed from that set. B2-B6: no schema, lifecycle, deployment, production module, or move changed. B7: the complete enumerated four-constraint set is retained. B8: neither a fit residual nor an input line is called independent evidence. B9: source-frame, constraint, endpoint, and shared-probe-point denominators are stated. B10: G222 settings, the G233d map, G253 comparison figures, court contract, and thresholds are unchanged. Q does not apply to this tracking measurement row. The new route is below 300 LOC, so A12 needs no LOC-allowlist change.

**NOT VERIFIED:** a passing accumulation control; an isolated transport-error cause; any NCAA fit or cross-arena finding; a blind gate or real calibration error; withheld-edge offsets; automatic calibration (still 0/17); another shot, camera, sport, or labeller; label repeatability; any production change. A gate pass would bound error, not certify correctness; no gate was reached here.
