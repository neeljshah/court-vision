# CourtVision tracking demos

These are short, headless renders of real broadcast footage plus the corresponding observed rows from the POD tracking CSVs. They are training-only corpus evidence, not product performance claims. A coloured marker and ID denotes an observed tracker centroid; trails join only consecutive observed render samples and are cleared across a gap. No box dimensions, interpolation, or continuity repair is added because the source CSVs do not contain them.

All clips are H.264, 1280x720, 15 seconds, and under 8 MB. Captions state the coordinate provenance visible in each render.

## Tennis

[tennis.mp4](tennis.mp4) uses `tennis_nyYk2nPZAwY_720p.mp4` and 415 observed rows from 160 source frames (3 track IDs; 320 player and 95 ball rows). The supplied rows are `court_feet`, so player and ball positions appear in a labelled court-space inset rather than being falsely projected onto broadcast pixels.

It does not claim pixel alignment, player identity correctness, ball accuracy, or continuity. The POD contains the TrackNetV3 evaluation harness but not its checkpoint/detector assets, so this clip explicitly does not claim a TrackNetV3 ball overlay.

## NPB baseball

[npb_baseball.mp4](npb_baseball.mp4) uses the genuine `npb_3PwJwWdTMek` broadcast and its 46,809 observed `image_px` player rows: 9,398 tracked source frames, 2,062 track IDs, and 4.98 positions per tracked frame. These are output-coverage measurements from the tracking CSV, not ground-truth accuracy.

It does not claim identity persistence through cuts, player identity, a ball track, baseball events, or calibrated field coordinates.

## NCAA basketball

[ncaa_basketball.mp4](ncaa_basketball.mp4) uses the 1080p `ncaa_basketball_IB-_u4gW3ds` broadcast and 3,061 observed `image_px` player rows: 578 tracked source frames, 10 track IDs, and 5.30 positions per tracked frame. The original tracker geometry is not recorded; the render uses a disclosed 2x display scale inferred from the 4K-scale coordinate range.

It does not claim court-foot coordinates, player identity, detection-box dimensions, calibrated source geometry, or tracking accuracy against labels.

## Soccer

[soccer.mp4](soccer.mp4) uses `soccer_cKXZysISV4w` and 98,261 observed `image_px` player rows: 8,333 tracked source frames, 662 track IDs, and 11.79 positions per tracked frame. These are coverage counts only.

It does not claim player identity, possession, offside, pitch coordinates, or benchmarked tracking accuracy.

## Football

No football clip is published in this packet yet. The available explicit-`image_px` footage/CSV pair examined during rendering was a conference panel, not a football broadcast; the genuine-football candidate lacked coordinate provenance. Publishing either as a football tracking showcase would be misleading.

No field-line detection, yard-line calibration, field coordinates, player identity, or tracking accuracy is claimed.
