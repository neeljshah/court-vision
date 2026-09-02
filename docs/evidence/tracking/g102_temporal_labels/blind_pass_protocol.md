# G102 blind-pass protocol

1. The 109 candidate identities were derived using only the `clip` and `source_frame` columns from the G65 resolved CSVs; no `ball_visible` value was read before this file was created.
2. Seed `10220260902` selected 40 identities from the 62 candidates whose local source video was available. The 47 unavailable `tennis__tennis_10.mp4` candidates were excluded before rendering for source availability only.
3. For each selected identity, the labeller viewed only the clean predecessor/current/successor strips and their review cards in `strips_blind_retry/` and `review_cards_blind_retry/`.
4. `strip_labels_blind_retry.csv` was written before opening any prior row-level label value. `ball_visible` means visible in the labelled current frame, using the adjacent frames only to confirm the temporal trajectory.
