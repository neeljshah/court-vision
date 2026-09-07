# G296A Pass A: independent located-player input

## Verdict

NOT VALIDATED: the local artifact is complete and passes its focused checks. Pre-join commit SHA 6212cb3ba; no join or comparison preceded it. Denominator: 24 deterministic clip-wide frames, one MODEL locator (Pass A), not a human.

## Independence and machine

This is Pass A. I did not read Pass B, its artifact, any prior located-feet file, detector output, join, comparison, or recall result before creating this artifact. All work was local on this worktree. The pod was not used, no network route was used, and no source under `data/` was written.

## Source identity

Opened source: `data/videos/bridge/wnba_01.f137.mp4`, 2,841,750,689 bytes, 1920x1080 native video. Binding local `ffprobe` output was:

```text
width=1920
height=1080
avg_frame_rate=30/1
duration=5814.333333
```

The source sha256 reported by the spec is `f2421bc24e5cbb28f41fa79f9ea755b2eeff4daebd48dc5496cc97e5617cf9d3`. The original pod source named by the spec has a sha256 beginning `f361ad7a32ccc6d98ae8e98e`; it does not match the local source. The most likely explanation, stated as a hypothesis only, is that the local file is a video-only DASH stream and the pod file was muxed. Whether frame index N is the same picture in both files is NOT VERIFIED here and requires the verifier's independent merge.

## Fixed frame set and extraction

Formula: `round(i * 174429 / 23)` for `i = 0..23`.

```text
0, 7584, 15168, 22752, 30335, 37919, 45503, 53087,
60671, 68255, 75839, 83423, 91006, 98590, 106174, 113758,
121342, 128926, 136510, 144094, 151677, 159261, 166845, 174429
```

The extracted list matches the formula exactly. The local command executed was:

```text
ffmpeg -hide_banner -nostdin -i data/videos/bridge/wnba_01.f137.mp4 -vf select='eq(n\,0)+eq(n\,7584)+eq(n\,15168)+eq(n\,22752)+eq(n\,30335)+eq(n\,37919)+eq(n\,45503)+eq(n\,53087)+eq(n\,60671)+eq(n\,68255)+eq(n\,75839)+eq(n\,83423)+eq(n\,91006)+eq(n\,98590)+eq(n\,106174)+eq(n\,113758)+eq(n\,121342)+eq(n\,128926)+eq(n\,136510)+eq(n\,144094)+eq(n\,151677)+eq(n\,159261)+eq(n\,166845)+eq(n\,174429)' -vsync 0 -q:v 2 docs/evidence/tracking/g296a_located_players_artifact/frames/frame_%02d.jpg
```

It emitted exactly 24 JPEGs. Each was checked with `ffprobe` and is full native 1920x1080, with no crop or resize.

## Per-frame record

| Source frame | Court visible | Description | Players located |
|---:|---|---|---:|
| 0 | true | wide opening-tip court view | 6 |
| 7584 | true | low-angle live-play court view | 7 |
| 15168 | true | wide free-throw-side live-play view | 9 |
| 22752 | false | player huddle close-up | 0 |
| 30335 | true | wide half-court live-play view | 8 |
| 37919 | true | wide half-court live-play view | 9 |
| 45503 | true | half-court live-play view with frame-boundary crop | 7 |
| 53087 | true | half-court live-play view with frame-boundary crop | 8 |
| 60671 | false | player facial close-up | 0 |
| 68255 | true | wide half-court live-play view | 8 |
| 75839 | true | wide half-court live-play view | 8 |
| 83423 | true | wide half-court live-play view | 8 |
| 91006 | true | wide half-court live-play view | 9 |
| 98590 | true | wide half-court transition view | 9 |
| 106174 | true | wide half-court live-play view | 10 |
| 113758 | false | player close-up | 0 |
| 121342 | true | wide transition live-play view | 9 |
| 128926 | true | close stoppage view with player feet out of crop | 0 |
| 136510 | false | bench timeout view | 0 |
| 144094 | true | overtime free-throw setup | 8 |
| 151677 | true | overtime wide live-play view | 8 |
| 159261 | false | bench close-up | 0 |
| 166845 | false | player close-up | 0 |
| 174429 | false | post-game player close-up | 0 |

## Artifact and confidence

`docs/evidence/tracking/g296a_located_players_artifact/located_players.csv` has the exact header `source_frame,person_index,role,feet_visible,foot_x_px,foot_y_px,confidence,note`. `docs/evidence/tracking/g296a_located_players_artifact/frames.csv` has the exact header `source_frame,court_visible,shot_description,players_located`. Every row has all schema fields. The relevant non-player people visible on court are recorded as `official`; bench and spectator background was not relabelled as on-court players. Players with feet outside the crop retain `feet_visible=false` and empty coordinate fields.

Located-coordinate confidence counts, by scope: on-court 0 confident / 131 approximate / 0 guess; all visible coordinates (players plus officials) 0 confident / 146 approximate / 0 guess; all 149 rows carry approximate labels (146 coordinate rows plus 3 no-coordinate rows; 15 of the 146 are officials). The location itself is the measurement; broadcast scale, motion, overlap, and perspective bound many foot locations at tens of pixels, so no point is marked confident.

Pre-join commit SHA: 6212cb3ba; no join or comparison preceded it.

## Limitations and verifier self-check

I am a MODEL, not a human, and this is not ground truth in the strict sense. Two model locators agreeing measures REPRODUCIBILITY, never CORRECTNESS, and both can be wrong in the same way. No human has checked these frames. Twenty-four frames spread across one clip are a thin, wide sample: this addresses span coverage and does not address the one-clip limitation. The deterministic frame indices were fixed before either pass ran, so neither locator selected its own frames.

There is no recall or other comparison in this pass. B1 through B10 self-check: there is no computed metric or excluded decision set; this is an additive new artifact; there is no gate, reclaim path, deploy, move, orphan, self-fit, recycled denominator, or changed threshold. Pre-join commit SHA: 6212cb3ba; no join or comparison preceded it.

## NOT VERIFIED

- The local and original pod source files have different sha256 values; frame-to-picture equivalence between them is not established here.
- Cross-pass agreement and any subsequent use of these coordinates are not established here.
- Human correctness of any location is not established here.
