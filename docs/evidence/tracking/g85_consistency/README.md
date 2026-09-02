# G85 blind consistency sample

This directory is the independently labelled sample required by `docs/evidence/tracking/specs/G85_spec.md`.

- One labeller made all calls in `blind_labels.csv` before opening any prior row-level `ball_visible` label.
- The fixed selection used PowerShell `System.Random(850917)`, selecting 20 rows without replacement from each of the three existing resolved chunks. Only clip/frame identities were exposed during selection and labelling.
- The 60 calls were judged from the files in `renders/`, which are G65 source-derived tiled 2x composites. `tennis_09` and `tennis_10` composites combine three 1600x1800 tiles (4800x1800); `nyYk_720p` composites combine its available two 1600x1800 tiles (3200x1800).
- The labels use the existing binary operational call: `ball_visible` only when the ball is individually identifiable in the 2x composite; otherwise `uncertain`.

The sample contains 60 unique `(clip, source_frame)` pairs: 20 from each clip. The existing 109 rows were neither relabelled nor edited.
