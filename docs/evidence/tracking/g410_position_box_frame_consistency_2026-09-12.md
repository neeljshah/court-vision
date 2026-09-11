VERDICT: PARTIAL + NOT VALIDATED -- court positions and stored boxes carry the SAME frame index and the SAME TOPCUT-cropped image frame, but the stored box is not the box that was projected (the projected foot sits exactly PAD = 15 px above the stored box bottom), and on CLAMP rows the court point is a PRIOR frame's point while the box advances; independent mismatch classification now exposed (fix 1b) but pre-launch identity is incomplete (31/39), so the row is NOT VALIDATED under ACCEPTANCE-3.
## Premise (reproduced before the draw)
G402 reproduces exactly: 19,087 rows, CLAMP 9,354, SUBPIXEL 1,399, DETECTION 3,075, PREDICTION
5,259, 0 blank route labels, 60 retained receipts. Correction to the sealed prereg wording: 59
launches are COMPLETE but only 58 sections carry bounded rows -- 1080p30 / 3eeaJz1PJTM_s6295
completed and emitted none. The draw over 3,504 CLAMP and 1,138 SUBPIXEL distinct ticks with
floor(j*(N-1)/29+0.5) gives 30 ticks per class, 241 selected rows and 238 retained same-window
predecessors; homography_valid is 1 on all 479; all 39 drawn sources rehash off-pod to G402's
digest and dimensions, 39/39.
## (a) Transform chain and frame consistency
`video_handler.py:11` TOPCUT = 60 and `unified_pipeline.py:1693`
`frame = frame[TOPCUT:]`: the detector never sees native pixels.
`advanced_tracker.py:1336` stores `(y1-PAD, x1-PAD, y2+PAD, x2+PAD)`, PAD = 15
(`player_detection.py:20`), while line 1410 projects `((x1c+x2c)//2, y2c)` from the CLIPPED,
UNPADDED detector box -- or the ankle mean above 0.5 confidence (line 1421); line 1427 applies `M1
@ (M @ kpt)` then int32 truncation. Measured: on every unclipped selected row the stored box
bottom is exactly PAD above the projected point (min 15.0, median 15.0, max 15.99 px), 6 of 241
rows clipped at a frame boundary. Of 279 same-invocation checks over 39 observer replays (M, M1,
stored box and stored court point captured inside ONE call), 133/133 DETECTION_FRESH_BOX and 13/13
SUBPIXEL_UNMOVED_FRESH_WRITE rows reproduce the serialized court point EXACTLY from the stored
box, back-projecting within a median 0.5 px of the archived foot: the chain is exact and
same-frame, the stored box is simply not its own projection source. The matrices consume the
cropped frame (1920x1020 / 1280x660 observed), so a stored box drawn on the NATIVE frame sits 60
px too high -- the 78 eye cards show the raw box, the box translated by the (0, 60) crop origin,
the predecessor box and the projected foot. That is the frame G406 measured against, and it
accounts for its -58.2 px offset without moving any court coordinate.
## (b) Staleness
CLAMP: 118/118 selected rows carry the predecessor's exact court point, 97/118 with a box that
moved; box-foot motion median 18.0 / p90 492.9 / max 1836.0 native px; the point had already been
held a median of 11 and up to 54 consecutive emitted ticks. SUBPIXEL: 37/38 retain the point but
only 12/38 boxes moved at all (median 0.0 / p90 6.7 / max 32.3 px) -- a rounding hold, not a stale
box. DETECTION 0/24 and PREDICTION 0/58 retain. Inside ONE observed run, 245 of 469 emitted rows
at the drawn ticks carry a court point differing from the one the detector wrote in that same
call. Corrected independent classification: 2/279 consistent, 107/279 frame mismatch, 36/279
stale, 124/279 branch mismatch, and 10/279 UNKNOWN (NO_PRE_CALL_STORED_BOX); exact-match-named
subgroups are descriptive, not independent validation.
## Implication, reproduction and digests
G380's labels stand and need no relabelling: CLAMP is a genuine retained-point branch, SUBPIXEL a
sub-pixel rounding hold; the G402 mask stays as landed, no geometric reference is promoted and no
localisation error is claimed. Two fresh processes rebuilt every delivered table and card from
delivered bytes (`repeats.json`); traces are bounded to the sealed ticks plus one predecessor
tick, full-trace digests in `runtime_receipts/`.
31/39 nonblank route digests matched; 8/39 pre-launch digests are absent; aggregate false.
q6_scan.json: new-path hits 0; historical-context index 3 count 24 (permitted retraction context in the inherited results log), listed in the manifest.
`docs/evidence/tracking/g410_position_box_frame_consistency_2026-09-12/prereg.md` SHA-256 c9a860838eb3f3cf801761d3dad8ddaa131a6b93f7997d77ac33da6ac9b038c4
`docs/evidence/tracking/g410_position_box_frame_consistency_2026-09-12/summary.json` SHA-256 16e779c520ad2ac41dc2e4f79012cabbf23143107c74afde53f09b7a6103573d
`docs/evidence/tracking/g410_position_box_frame_consistency_2026-09-12/contract_checks.csv` SHA-256 96e7f5a0c0210320b0fb0efbb8aca57306ca771cf8dfe697a9aa5cb5aead1cbb
`docs/evidence/tracking/g410_position_box_frame_consistency_2026-09-12/launch_receipts.json` SHA-256 cab792a652729deca803b6c9f5d6515421d8d072cec20c042c7daa3c16dfb765
`docs/evidence/tracking/g410_position_box_frame_consistency_2026-09-12/repeats.json` SHA-256 f31d7ead5bd3d87dddae2295f094e17770e3b171b9915e7657f10ca91069846d
`docs/evidence/tracking/g410_position_box_frame_consistency_2026-09-12/q6_scan.json` SHA-256 0facd1313ed9bbec6b6a84399bb66ede9274dca3a9e573bffd39c38a50fa613e
## Fix 1b (2026-09-12): classification moved from 146 consistent / 89 frame mismatch / 44 stale to 2 / 107 / 36; 124 branch mismatches and 10 UNKNOWN rows are exposed; 31/39 pre-launch identity keeps NOT VALIDATED, while measurements, draw membership, traces, matrices, and retained-output numbers did not move.
## Fix 1c (2026-09-12)
The whole-parent order recomputation gives lexical prereg overlap 3/30 CLAMP and 2/30 SUBPIXEL; the executed draw follows spec draw_order/frame. The class table now displays all 279 checks without changing measurements.
## NOT VERIFIED
- Physical court registration and any localisation-quality claim.
- Cross-run identity: G380 measured 0/30 row identity; 2 of 60 drawn ticks have no same-invocation binding (28/30 CLAMP ticks, 29/30 SUBPIXEL ticks covered).
- Model identity was hashed during, not before, the first 8 launches; route digests were captured before each launch.
- Whether the PAD offset or the crop origin is a defect: that is cause, not this row.
- stray pytest temp artifact committed by fix 1b; scanned, zero hits; not evidence.
- lexical prereg overlap is 3/30 CLAMP and 2/30 SUBPIXEL; executed draw follows spec draw_order/frame.
