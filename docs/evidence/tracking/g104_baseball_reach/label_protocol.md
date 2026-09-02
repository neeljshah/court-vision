# G104 visibility-label protocol

Each row in `frame_labels.csv` is one unique `(clip, slot)` from
`sample_manifest.json`; the manifest maps it to its decoded source frame and
render. A point is counted only if the physical feature is visibly discernible
in the frame, not merely inferable from the field layout. The permitted named
points are `home_plate`, `first_base`, `second_base`, `third_base`, and
`pitching_rubber`.

`baseball_gameplay` means the frame is from a live-game or game-replay camera.
`baseball_non_game_program` means the feeder-labelled clip is a studio,
commentary, or screen-capture program rather than game footage. Such rows are
retained in the 120-frame denominator, explicitly reported as non-game, have
no named point label, and have a zero visible-point count; they are never
silently excluded or treated as a baseball field view.

Straight-line directions count only visibly discernible foul-line directions.
The curved infield dirt boundary is recorded nowhere as a straight direction.
The two foul lines are two non-parallel directions, but duplicate segments in
one direction are one constraint family.
