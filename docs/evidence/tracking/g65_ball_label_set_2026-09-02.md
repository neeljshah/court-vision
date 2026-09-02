# G65 tennis ball label set -- attempt 2

Date: 2026-09-02. Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`,
including A7 and section B.

## Outcome

This is a durable, detector-independent hand-label set. It reuses the 150
seeded, evenly spaced frames from attempt 1, but replaces its whole-frame-only
review with court-band and tiled review. There are 150 unique
`(clip, source_frame)` rows across three clips: 41 eye-confirmed visible
balls and 109 explicitly uncertain rows. Coordinates and radii are in
**image_px** only; they are not court_feet.

## Sampling

Seed: `650913`. The same preselected continuous wide-court rally windows
were retained:

| Clip | Source resolution | Rally window | Evenly spaced source frames | n |
|---|---:|---|---|---:|
| `tennis__tennis_09.mp4` | 1920x1080 | [6962, 7257) | `6962 + 6*i`, i=0..49 | 50 |
| `tennis__tennis_nyYk2nPZAwY_720p.mp4` | 1280x720 | [33857, 34152) | `33857 + 6*i`, i=0..49 | 50 |
| `tennis__tennis_10.mp4` | 1920x1080 | [4043, 4289) | `4043 + 5*i`, i=0..49 | 50 |

These are continuous rally-view windows rather than clip heads. The original
150 source-frame renders remain in `renders/`; sampling is reproducible from
the table and seed.

## Eye-review method

First pass: I cropped the court band in every source frame and upscaled it
1.3x with Lanczos interpolation. The 150 renders are in
`renders/courtband_13x/`. This pass resolved 33 visible-ball calls and left
117 rows uncertain.

Required re-check: I selected deterministic in-window ordinals
`1, 6, 11, 16, 21, 26, 31, 36, 41, 46` from each clip (30 rows total).
Every court band was split into overlapping horizontal tiles: two tiles for
the 1280-wide clip and three for each 1920-wide clip, each at 2x. All 400
tiles are retained in `renders/courtband_tiles_2x/`. The tiled pass flipped
**8 / 30** first-pass uncertain calls to visible:

- `tennis_nyYk2nPZAwY_720p`: ordinals 1, 6, 11, 16 (4);
- `tennis_09`: ordinals 6, 16, 31 (3);
- `tennis_10`: ordinal 1 (1).

The final CSV is the post-recheck version. I inspected rendered pixels and did
not run `MotionDiffDetector` or use its output as a label. Bright court
lines, net texture, player/racket occlusion, motion trails, and out-of-frame
flight were left uncertain rather than forced into a binary false-negative.

## Final labels and remeasurement

The durable label file is
`docs/evidence/tracking/g65_ball_labels/labels.csv`. It has the required
per-frame fields. A visible row carries `ball_visible=true`, a centre and
approximate radius; an unresolved row carries `uncertain=true` and a
one-clause reason, with coordinate/radius fields blank by design.

- Visible ball: **41 / 150** (27.3%; Wilson 95% CI 20.8%--35.0%).
- Visible balls inside `y < 2/3 * height`: **32 / 41** (78.0%; Wilson 95%
  CI 63.3%--88.0%).
- Uncertain: **109 / 150** (72.7%; Wilson 95% CI 65.0%--79.2%).

The visible fraction is lower and the inside-window fraction higher than
G44's single-clip summary (64% and 52%). That disagreement is a finding, not
a correction to G44: this three-clip set has high explicit uncertainty, and
neither aggregate is detector recall or precision.

## A7 and B self-check

At write time, every evidence path named here exists:

- `docs/evidence/tracking/g65_ball_label_set_2026-09-02.md`
- `docs/evidence/tracking/g65_ball_labels/labels.csv`
- `docs/evidence/tracking/g65_ball_labels/renders/`
- `docs/evidence/tracking/g65_ball_labels/renders/courtband_13x/`
- `docs/evidence/tracking/g65_ball_labels/renders/courtband_tiles_2x/`

- B1: every fraction names its complete denominator; uncertain rows are
  reported, not silently excluded.
- B2--B4: no production schema, reader, gate, or claim path changed.
- B5: no pod file was deployed, copied, restarted, or killed.
- B6: no module, import, or test was moved or retired.
- B7: the set is seeded and evenly spaced within preselected rally windows,
  not a head slice.
- B8: visual labels are independent of the detector under evaluation; no rule
  was fit to these rows.
- B9: there are 150 unique frame decisions, not recycled identifiers.
- B10: no harness threshold, detector, solver, or coordinate contract moved.

No code was added, so no test was required or run.

## NOT VERIFIED

- The 109 uncertain rows are not false labels; many may contain balls that
  remain ambiguous under the retained review views.
- These data do not establish recall, precision, a new spatial rule, or a
  detector change.
- Approximate radii are hand estimates, not subpixel measurements.
