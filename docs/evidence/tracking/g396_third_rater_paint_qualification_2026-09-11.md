VERDICT: DONE -- the ASTRA tier qualified on fresh sealed controls, sol re-qualified on the same controls, the joint bar was met, and real paint was scored and independently pixel-audited on all 30 retained contexts.

## Premise (step 0, recomputed before any packet)

All 60 rows of the landed G392 qualification table recompute: sol 30/30, terra 20/30, joint 20/30, `real_scored` false. No subsequently qualified pair exists anywhere under `docs/evidence/tracking` (explicit-flag scan, 0 hits). Identity rehash holds: 49 retained natives, 30 context identities and 180 tile identities all match their recorded digests, with the 11 parent decode failures retained and excluded from every denominator. All 60 parent states are accounted.

## The sealed gate (seed 396, fresh controls, no retry)

30 practice and 30 qualification controls were built on the same 30 retained contexts, six tile positions and the 0/30/60-degree cycle. Pixel digest and truth tuple are disjoint within G396 and against G392; context/tile disjointness holds only between the two G396 sets; each G396 set shares its 30 context/tile pairs with G392. The ASTRA image-open fixture passed before any scored dispatch (640x540 opened, correct offset, one output file). ASTRA practice: 30/30, perpendicular error p50 0.210 px, p90 0.427 px, max 0.794 px, angle error max 0.136 deg. The one permitted correction was offered after practice and DECLINED ("none requested"); the instruction was frozen before qualification. Sol received no feedback and carried its G392 frozen instruction verbatim.

Blind, feedback-free, one attempt each, on the SAME 30 fresh controls:

| rater | passed | bar | perpendicular p50 / p90 / max (px) | angle max (deg) | fail reasons |
|---|---|---|---|---|---|
| astra | 30/30 | 27 | 0.332 / 1.091 / 1.327 | 0.256 | none |
| sol | 27/30 | 27 | 0.673 / 2.312 / 23.896 | 5.727 | PERPENDICULAR x3 |
| joint | 27/30 | 27 | - | - | - |

Every bar is byte-identical to the spec: 27/30 per rater, 27/30 joint, 3 px point, 60 px span, finite band, strictly interior third point. Both raters answered all 30; no batch wrote nothing, so no fault was counted and nothing was re-run.

## Real paint (permitted only by the passed gate)

The unchanged even 30-of-49 retained contexts were issued once to both qualified raters under the G388 family set and three-point protocol. ASTRA: 25 VISIBLE, 5 ABSENT, 46 fragments. Sol: 25 VISIBLE, 5 ABSENT, 42 fragments. Pairing by tile/family with the stable smallest symmetric line distance and the sealed 6 px rule yields 6 candidate pairs. Finisher native visibility was recorded for all 30 contexts BEFORE any trace was opened: 22 YES, 8 NO.

Each candidate pair was independently audited against visible paint with nine evenly spaced native points per fragment at 6x-28x zoom, one non-reusable token per candidate: 3 of 6 pass (G396_020 sideline, G396_022 and G396_023 straight court lines, 9/9 on each fragment); 3 fail (G396_004 sol 4/9, on bare floor below the line; G396_013 sol 7/9, in the light stripe above the line with one occluded click; G396_017 sol 7/9, two clicks where players occlude the lane line).

Recovery on both denominators, conditional on the retained images: **3 of 30 states** and **3 of 22 finisher-visible states**. All 30 states are accounted for. Family disagreement on 17 of 30. ABSENT and UNKNOWN are retained on both sides and never dropped. No recovery minimum was assumed anywhere.

Scoring and tabulation were repeated in two fresh processes from the raw answers: scores, summaries, pairing and per-frame tables are byte-identical to each other and to the landed files (`repeats.json`, all_identical true) -- this checks arithmetic, not rater repeatability. Fresh render-tree digest triples (process_1/process_2/matches_landed) are audit_cards af60a6a629e39c5bf85457bcde2cb595f78696547a405e050522b12f92b7e65f/af60a6a629e39c5bf85457bcde2cb595f78696547a405e050522b12f92b7e65f/af60a6a629e39c5bf85457bcde2cb595f78696547a405e050522b12f92b7e65f; audit_clicks 4cb257cb2d45ff113d00637f97129e2493638eefb1c11e4f5b8e7885cb2a4efc/4cb257cb2d45ff113d00637f97129e2493638eefb1c11e4f5b8e7885cb2a4efc/4cb257cb2d45ff113d00637f97129e2493638eefb1c11e4f5b8e7885cb2a4efc; practice d79e2d0f7476c0af831b4cdd163e0bcde41d478c2103969607ec2a0d30f656c8/d79e2d0f7476c0af831b4cdd163e0bcde41d478c2103969607ec2a0d30f656c8/d79e2d0f7476c0af831b4cdd163e0bcde41d478c2103969607ec2a0d30f656c8; qualification 4861f5c52e4039928f5760143c14693e1b343633475d4fd3121e2c48a9c97fac/4861f5c52e4039928f5760143c14693e1b343633475d4fd3121e2c48a9c97fac/4861f5c52e4039928f5760143c14693e1b343633475d4fd3121e2c48a9c97fac; real 7be1a11207035786c66a7441719702a842e66fdfef4b74c7e4da9858d363b137/7be1a11207035786c66a7441719702a842e66fdfef4b74c7e4da9858d363b137/7be1a11207035786c66a7441719702a842e66fdfef4b74c7e4da9858d363b137; identity share 108/108. Fix 1b (2026-09-11): the codex rerun first pointed at the retired g392_work cache (0/108 MISSING); the orchestrator then re-ran every tree twice with the committed g396_render.py against the G387 native cache -- practice, qualification and audit_cards reproduce the landed bytes; the landed real traces and audit-click strips had been written by an uncommitted finisher helper, so they were REPLACED by the committed-code renders (originals retained under renders_pre_fix1b/, never deleted) and every current render is reproducible from the raw answers. Eye check: all 30 qualification overlays per rater reviewed in even order (sealed centreline plus both raters' points), plus all 30 real traces and all 6 audit cards with their per-click strips.

## NOT VERIFIED

- Both raters ran at `model_reasoning_effort=high`, the tier both homes configure; G392 dispatched at `medium`. Sol's G396 score is earned at this setting and no G392 score is carried across, but the two rows are not identically configured.
- Sol has prior exposure to these same 30 real contexts from G387 and G388; ASTRA has not. The spec requires the unchanged contexts, so this asymmetry is inherent and unmeasured.
- The audit is one finisher's pixel adjudication; its inter-adjudicator repeatability is unestablished, and family labels are not adjudicated (17 disagreements reported, not resolved).
- Nothing here is a registration or homography result; no production module, fitter or flag was touched and `data/registry/` was not written. 3 of 30 is a descriptive recovery count on one sample, not a property of the system.

Improvement means baseline loss minus candidate loss; positive means candidate better -- no such comparison exists in this row. Wall time 46 min (2026-09-11T11:02:07Z to 11:48Z); PC worktree `C:/Users/neelj/nba-track-a3`, no pod, no GPU, no fitter.

## Digests

Remaining artifact digests, including practice, the correction receipt, both frozen instructions and visibility, are in `SHA256SUMS`. Prereg sealed ALONE at commit 8ee65b437, path `docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/g396_prereg_2026-09-11.md`, SEAL sha256 18124321ca2b0daf315283e16ec79f06c5498cd2bb6948bd65f2893c2976dd12 (sha256 of every LF byte above the SEAL line). The seal predates every metric in this row.

```
d239d3ff8a46c2104c11049ff3a842323244013fd01172c75767f166a4027c4b  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/g396_prereg_2026-09-11.md
25fb9249760ef18e1ff069b71834b79e446925fe8eb00f4e4eaa41ffb6489a91  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/input/premise_receipt.json
34f7ac475106afd24c6b8cd2081a934afaf49e885df141f663a37b09734f14f1  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/input/runtime_receipt.json
02ebdeb2985635b3dd392ac2bd410140a03d8d5748904540949613999d82c17a  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/qualification/scores.csv
2a377d1960977515549c61568d077ebafec8fde192b8469d8e616309e0dc2154  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/qualification/summary.json
c7162adc369685b9d404450f7736938008c79bb8fbf1d724a3b4529601de8fe3  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/pairing.csv
3d9066e03261ac08bb8094126b954d7277afb4a2fbdc3b53a86459dc912d3a3c  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/per_frame.csv
391145832a379a1fd07b20f66da7da1ae486be624c34b8287db65aab78f3f934  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/audit_clicks.csv
d68d1a9cd19d9383f60204e8c1e823da564403c2e05e6e2b5a3d2129e23afb5c  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/real_summary.json
71a65d90445191f685463249c77a71fc8f0b0acbe4f054681187fe2cadf016cd  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/eligibility.json
19c8f71d6c1648121405b6d7fdc700cfea55953ed8f8855d9bba758a53a341c6  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/summary.json
68a5dc8edfc9a48d82179d33d0ebd3003665de44c7e702e7e355651d9ca925ae  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/repeats.json
8be7c9dd5b708d0a6d28f6662ab85fbb6356f5f36d746d3509c9fe110d31496c  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/renders_repeat_digests.csv
8edafdd13b3431716be2262308a3fa8db9567766a098a0caf0d939a43ade6580  docs/evidence/tracking/g396_third_rater_paint_qualification_2026-09-11/q6_fix1b_scan.json
```
`SHA256SUMS` carries all artifact digests and excludes its own entry. Per-file tests: `python -m pytest tests/platformkit/test_g396_third_rater_paint.py -q` (10 passed) and `tests/platformkit/test_loc_rail_scope.py -q` (1 passed). Vocabulary scan over every text artifact including the archived rater logs: `q6_scan.json` -- 217 files scanned, 0 non-opaque hits. One rater-written bare integer in a progress line of `rater_logs/cx_g396_rater_astra_real02.log.txt` was replaced with `calibration-only`; before and after digests are in `q6_redactions.json`; both files' digests are in `SHA256SUMS`.
