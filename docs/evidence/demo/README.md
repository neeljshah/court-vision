# CourtVision tracking demos

These are short, headless renders of real broadcast footage plus the corresponding observed rows from the POD tracking CSVs. They are training-only corpus evidence, not product performance claims. A coloured marker and ID denotes an observed tracker centroid; trails join only consecutive observed render samples and are cleared across a gap. No box dimensions, interpolation, or continuity repair is added because the source CSVs do not contain them.

All clips are H.264, 1280x720, 15 seconds, and under 8 MB. Captions state the coordinate provenance visible in each render. Review stills at t=3, 8, and 13 seconds use the matching `<clip>_t<second>.png` name.

## Selection rule

Each source-CSV segment is a full 15-second window that maximizes `distinct observed player track IDs * (player rows / source frames)` for its matching footage. The denominator is every source frame in the window, including frames with no row; it is not only tracker-emitted frames. This avoids rewarding a sparse or truncated tail.

## Tennis

[tennis.mp4](tennis.mp4) uses `tennis_nyYk2nPZAwY_720p.mp4`, source frames 3816-4565 (76.32-91.32 seconds): 2 distinct player tracks, 132 player rows / 750 source frames (0.1760 rows/frame), selection score 0.3520. The supplied rows are `court_feet`, so player positions appear in a labelled court-space inset rather than being falsely projected onto broadcast pixels.

It does not claim pixel alignment, player identity correctness, ball accuracy, or continuity. The pod checkpoint at `/tmp/tracknetv3-a1/ckpts/TrackNet_best.pt` was separately run by the supplied evaluator: 34 detections in 40 cut-free source frames at the selected start (0.85). [tennis_tracknet_overlay.png](tennis_tracknet_overlay.png) is one model-labelled output, not a ground-truth claim.

## NPB baseball

[npb.mp4](npb.mp4) uses `npb_3PwJwWdTMek`, source frames 25092-25541 (837.24-852.25 seconds): 120 distinct player tracks, 1,198 player rows / 450 source frames (2.6622 rows/frame), selection score 319.4667. These are output-coverage measurements from the tracking CSV, not ground-truth accuracy. A manual source contact-sheet review found that the unconstrained CSV maximum is a close-up sequence; no wide-game-shot qualifier is claimed for this evidence segment.

It does not claim identity persistence through cuts, player identity, a ball track, baseball events, or calibrated field coordinates.

## NCAA basketball

[ncaa_basketball.mp4](ncaa_basketball.mp4) uses `ncaa_basketball_zqBCKovJCQU`, source frames 144-593 (4.80-19.82 seconds): 10 distinct player tracks, 925 player rows / 450 source frames (2.0556 rows/frame), selection score 20.5556.

It does not claim court-foot coordinates, player identity, detection-box dimensions, calibrated source geometry, or tracking accuracy against labels.

## Soccer

[soccer.mp4](soccer.mp4) uses `soccer_cKXZysISV4w`, source frames 4776-5225 (159.20-174.20 seconds): 48 distinct player tracks, 2,003 player rows / 450 source frames (4.4511 rows/frame), selection score 213.6533. These are coverage counts only.

It does not claim player identity, possession, offside, pitch coordinates, or benchmarked tracking accuracy.

## Football

[football.mp4](football.mp4) is an attempted bridge-footage render from `football__giants_jets_format96_1080p.mp4`, source frames 0-449 (0-15 seconds). There was no matching tracking CSV, so 150 sampled frames were freshly observed with the local YOLOv8n person detector: 1,089 detections (7.26 per sampled frame). The caption says `image px | no coordinate provenance`; those detector rows are not source-CSV tracks, identities, or field coordinates.

No field-line detection, yard-line calibration, field coordinates, player identity, or tracking accuracy is claimed.

> ORCHESTRATOR REVIEW (2026-09-01): football.mp4 published (wide field view,
> honest caption). The tennis/NPB/NCAA/soccer clips from this render are held
> back: row-density window selection favored close-up/crowd segments where
> detectors over-fire. Review frames for all five are committed. A wide-shot-
> gated re-selection replaces the held clips before they publish.
