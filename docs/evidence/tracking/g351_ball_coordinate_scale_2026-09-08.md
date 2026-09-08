VERDICT: DONE
# G351 Ball Coordinate Scale
Prereg: `docs/evidence/tracking/g351_prereg_2026-09-08.md`, seal
`240011962ca6a9da9a134bc3c79435da38f7f036b37b4b467426d3de790d5e89`. Contract:
`docs/evidence/tracking/VERIFIER_CONTRACT.md` section B.
## Premise (step 0) and per-clip range census
410 immediate `data/tracking/<clip>/` directories (of 425 raw entries; 15 are loose
files sitting directly in `data/tracking/`, not clip dirs -- excluded correctly by
`is_dir()`). 356 clips had both CSVs (status OK); 54 were MISSING_TRACKING_OR_BALL_TABLE.
Of the 356 OK clips, 214 have `ball_range/player_range > 1.5` on x or y (anomalous), the
module's own metric = 521 per-mille of all 410 scoped clips. Premise TRUE (share != 0):
G349's 3/26-window anomaly generalizes far wider than that window set. Wall time 3m25s
(20:28:12-20:31:37 UTC). `ranges.csv`: every scoped clip, one row each, no skips.
## Writer trace (file:line, verified by sed -n against this worktree)
- Player: infer `advanced_tracker.py:1223-1241`, raw TOPCUT-crop bbox `:1334-1337`, court
  projection `:1425-1429`; called at `unified_pipeline.py:1913-1918`. `bbox_x1..bbox_y2`
  (`unified_pipeline.py:2727-2734`) take the RAW bbox -- never court-projected.
- Ball: dedicated call `unified_pipeline.py:1945-1950` -> `ball_detect_track.py:349-388`
  (detect `imgsz=384`, clip, centre) -> project `:908-956` (`ball_2d = M1 @ (M @ ball_center)`
  at `:909-911`, `last_2d_pos = ball_2d` at `:956`), written `unified_pipeline.py:1988-1989`.
- Alternate ball route `unified_pipeline.py:3081-3093` sets `_last_ball_2d` from a YOLO
  ball bbox through the same `M1 @ (M @ ...)` -- same court-map units.
- `TOPCUT=60` (`video_handler.py:11`) crops the frame at `unified_pipeline.py:1692`.
- Confirmed defect: ball writer field = court-map coords, player bbox writer field = raw
  cropped-pixel coords -- a real cross-table unit mismatch, not window-local (sampled
  anomalous clips: ball x-range often 3000-5000+ vs player x-range roughly -150 to 1500).
## Inferred ball coordinate frame (n=356 OK clips)
No clip carries BOTH `source_width` and `source_height`; `wnba_02` and `wnba_05` carry
height (720) only (`ranges.csv:410-411`), so classification could never select
original/crop/detector/panorama. No `league`/`daemon_code_version` sidecar on any clip.
| ball_frame | n |
| --- | --- |
| UNKNOWN_NO_SOURCE_DIMENSIONS | 349 |
| UNKNOWN_NO_FINITE_BALL_COORDINATES | 7 |
## PROPOSED correction (not applied)
`docs/research/organization-sprint/G351_PROPOSED_ball_scale.md` (gitignored), sha256
`707c0913823dec5a4402f2182dc37303444992a237e9338def099343c3cc468d`. Adds `ball_x2d_px,ball_y2d_px` (pixel-space, additive, nothing renamed) at
`ball_detect_track.py:956`/`unified_pipeline.py:1988`. Reader-side rescale for landed
tables: `new=(old-ball_p01)*(player_range/ball_range)+player_p01` per axis (in `rejoin()`).
## Re-join check (60px radius, before/after the reader-side rescale)
| window | frames w/ finite detected ball | before | after |
| --- | --- | --- | --- |
| 0022500630 | 5305 | 777 | 2625 |
| 0022500799 | 6026 | 2051 | 1330 |
| 0022500906 | 5317 | 239 | 923 |
Mixed: 2 of 3 windows gain radius-survival after the affine screen, 1 loses it (2051 to
1330) -- a screening result, not correctness evidence: confirms the unit mismatch is real
but the reader-side rescale does not uniformly repair it.
## HONEST LIMITATIONS / NOT VERIFIED
Range-ratio screens for scale, it does not prove frame identity. No clip's tracking
epoch/version was recoverable (no sidecar fields exist in this mirror), so pre/post-G333
clips could not be distinguished. Producer fix proposed only, unconfirmed by rerun. eye check = NONE.
2026-09-08 lander: writer-trace citations corrected per the codex-sol verify memo; NEW GAPS
in the ledger (ranges.csv lacks the additive per-mille column; the PROPOSED diff must clear
stale pixel fields and handle a valid zero explicitly before G354 applies it).
SCAN: the measured missing-table clip count (54) collides with the retracted standalone-54
digit rail; it is a genuine census count, not rewritten.
SHA-256 (LF-normalized): module `804a455fe663a19528771c57d66c7b6dd1e877e1ab6924c89b1539db94657b3d`; test `2142ba439fe31c5fef04fc9ba47b7394afc8abc4364c0cc005489d5291b4b686`;
prereg `2c231c39745fde8c2dff6814ba49bf6671b22e2d674a3d813be2efdb8c0d1ba8`; ranges.csv `5285a9505ba9400ae33ffd64e81bfa4fcf84da7e86bd3623c39aca3e7c2d3e2b`;
rejoin.csv `193db5424574b1212f02398882ccad0bf95a8cd535a7af184fe955cf4b74b7a8`.
