VERDICT: PARTIAL -- clause "PARTIAL for missing/ambiguous evidence": the audit ran end to end and both extraction processes are byte-identical, but the blind painted-marking reference is AMBIGUOUS (the two raters name the same physical marking 57 times and those traces overlap at median IoU 0.000000), so the two specificity shares are reported as a bracket and never as a point.

# G382 Court Stroke Specificity Audit

## Premise (step 0, re-measured first)
PREMISE HOLDS. `docs/evidence/tracking/g379_broadcast_geometry_2026-09-10/summary.json` (LF-normalised sha256 a61b9190343cb6a5303545d355e3670a9738a7e3f7b02d28b6fabd114a0fe4cb, 6196 bytes; the CRLF checkout is 6396 bytes) reproduces `sections_meeting_all_three` = 0 and `raw_state_totals.REFUSED` = 352. No prior quantitative painted-marking specificity receipt exists in the tracking evidence tree (G264/G291/G295 use the word only to disclaim it). The prereg SEAL recomputed over the LF-normalised bytes above its seal line MATCHES.

## Where it ran
Census, decode and scoring on the pod CPU (213.192.2.120, 6 cores via taskset, threads 1, nice 10, Python 3.12.3, cv2 4.14.0, numpy 2.1.2); blind rating and adjudication on the PC. Pod tip 55be53e2. Route identity: `g362_strokes.py` 37e066086fb288d95b8ea9548d6b7ae6796702368d729ef32a373ed1be12db78, `g334_court_line_calibration.py` bf48bf9f5020c807085233f873c614d6ff3c0700fdf3f2da0bc5f95094e9ce4c, `domains/basketball/tracking/line_calibration.py` 228b6d52216d8f16246848cc2e7f532c6fdb87084b7e6983d181e5d9bef71266. No G362/G365/G371/G374 constant, the 0.30 threshold, or any producer field moved; no fit ran.

The live rotating corpus was EMPTY at capture, so the census covered the 33 preserved sections in `/workspace/g364_scratch/val` and `/workspace/g380_scratch/sources` (18 video ids, all 1920x1080, 2424 MB) at CENSUS_UTC 2026-09-11T01:58:36Z. Sources were pinned by sha256 before AND after decode instead of copied, because they are preserved lane scratch rather than the rotating queue; all 12 pins are byte-stable (`pins.json`), so no copy remained to delete.

## Draw and completeness
12 sections from 12 video ids, five strictly interior even ticks each = 60 planned native frames; `selection_sha256` 302b2592dc8caec61cbb28a9391fbce94303f0ad83fdfc6eb71ff15f3a609ef0. 49 RETAINED, 11 DECODE_FAILED -- every failure is the rank-5 tick, because container `nb_frames` overcounts the real decodable frames (measured 8080 vs 7853, 8102 vs 7973, 4007 vs 3957). Recorded draw failures, never replaced. All 60 planned frames are accounted for in `frames.csv`.

## Every bar with its measured value
| bar | measured |
|---|---|
| all 60 planned frames accounted for | MET: 49 RETAINED + 11 DECODE_FAILED = 60 |
| >= 30 decoded and rated frames | MET: 49 sheeted, 49 rated by both raters |
| every emitted stroke classified incl. UNKNOWN | MET: 6,860 strokes, all 460,484 supports labelled |
| both extraction runs identical | MET: receipt 94086ddeee142acf621f47d7927f4a8a732d124fb428ca8af06680d6fcf5a423 from two fresh processes, in both reference modes |
| no fitting | MET: no fit, no flag flipped, no registry write |
| minimum purity | none required by the spec |

Share 1, on-marking strokes / all strokes: 0 / 6,860 = 0.000000 under the conservative both-raters reference; 20 / 6,860 = 0.002915 under the union bound. Share 2, painted supports / all supports: 163 / 460,484 = 0.000354 conservative; 4,861 / 460,484 = 0.010556 union. Per-frame macro mean over the 49 frames carrying strokes: 0.000000 conservative, 0.003221 union (best single frame 0.026316). No-stroke frames: 0 of 60 planned.

Union support attribution: OTHER 76,078; STANDS 70,211; SCORE_BUG 45,470; LED 22,819; UNREADABLE 0; PAINTED 4,861; UNKNOWN 241,045. Conservative attribution: OTHER 47,496; STANDS 38,761; SCORE_BUG 35,200; LED 7,095; UNREADABLE 0; PAINTED 163; UNKNOWN 331,769. At least 27.9 percent of all supports sit inside regions BOTH blind raters independently masked as non-court broadcast content, against at most 1.06 percent on painted markings.

## Reference quality, adjudicated from source pixels before any result was revealed

175 painted identifier rows: 57 AGREED, 118 UNRESOLVED. Of the 57 same-identifier pairs, 34 have ZERO pixel overlap; IoU p50 0.000000, p90 0.033608, max 0.472406. Agreed painted area is 9,931 px over 49 frames (0.0098 percent of 101,606,400 px) and only 17 of 49 frames carry any. On the four evenly drawn dispute cards (`renders/adjudication/`) I ruled from the pixels that NEITHER trace lies on the painted marking: both raters place the lane box and sidelines off the visible paint, and one follows an advertising-board boundary. Regions agreed far better (149 AGREED, 26 one-rater-only), which is why the clutter attribution is the durable half of this audit.

## Eye check (30 cards, even indices 0..59 over all 60 planned frames)

`renders/` holds 30 cards. The evenly spaced set includes five decode failures (4, 24, 39, 49, 59); those are explicit missing-frame cards, and 25 cards carry pixels. The cards show the frozen extractor emitting a dense thicket of strokes across the whole frame -- crowd, stanchion, advertising boards, score graphic, and a radial burst off a painted centre-court logo -- at angles no court marking has. That evidence needs no reference and is the strongest result in this row.

## NOT VERIFIED
- That the extractor is non-specific as a PROPERTY: a low share against a reference whose own median same-identifier IoU is 0.000000 cannot separate extractor behaviour from reference error.
- Any pixel-precise painted-marking reference; this rating protocol did not produce one.
- Generalisation beyond these 12 sections / 12 video ids / 49 frames, or to another sport, arena, camera or rater pair. Frames are the sampling units; the 6,860 strokes are nested, not independent trials.
- Anything about G383, registration, a candidate fitter, or any production change.

## Deviations from the sealed protocol
1. `g382_masks.read` now accepts an annotation with zero painted markings, so a broadcast close-up is scored with every support labelled rather than refused and dropped from the support denominator. 2. Sources were pinned in place rather than copied to scratch (reason above). 3. Two reference modes are reported, because one point estimate would overstate what this reference supports.

Wall time 2h40m (01:56Z census to 04:36Z memo).

## Receipts
Full SHA-256 for every artifact: `g382_court_stroke_specificity_2026-09-10/SHA256SUMS.txt`. Contract Q6 scan `q6_scan.json`: 0 prose findings over the memo, this row's modules, the per-file test, the ledger row and every evidence file, with the two support tables scanned DECOMPRESSED (a gzip stream yields byte coincidences, not prose).
252ca46be4e8f8648283dfdb6f4056bdf3de8e83ff61729d6601087798f45ed8  docs/evidence/tracking/g382_court_stroke_specificity_2026-09-10/g382_prereg_2026-09-10.md (SEAL, LF-normalised above the seal line)
79975c5917af6a175be97032035e6a7b8cdeb05fcdbde3060db9053b016a7ee0  docs/evidence/tracking/g382_court_stroke_specificity_2026-09-10/summary.json
502e46e5243cdcf276e46e3ae7774f47e9c7d846a1ef27299cf3c20280bce8a5  docs/evidence/tracking/g382_court_stroke_specificity_2026-09-10/summary_union.json
da16ff4e432b432f56ae843fef1d52f397bd2417e655e3fa66b4a64aec128e8b  docs/evidence/tracking/g382_court_stroke_specificity_2026-09-10/strokes.csv
e79ebbcfc06ae0a40306517eeefd2fe2d614b1dd6011b55f84bb37ed716848dc  docs/evidence/tracking/g382_court_stroke_specificity_2026-09-10/support_labels.csv.gz
886e4b48f539079c448f0cd3fff3ed4e6fe7b7dccaab0237060500759671128c  docs/evidence/tracking/g382_court_stroke_specificity_2026-09-10/repeats.json
7308ab5a3bb66fabb69f66f8016ef47e4d7a19e3d1d4cb46dcd11c471ba195a3  docs/evidence/tracking/g382_court_stroke_specificity_2026-09-10/reference_agreement.json
9bc53aa82046834770436c51d7f0823f34a747b21fac288b86a0f3072e9602a2  docs/evidence/tracking/g382_court_stroke_specificity_2026-09-10/marking_only.json
