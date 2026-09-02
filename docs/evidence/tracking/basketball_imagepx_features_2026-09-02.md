# Basketball image-pixel teacher features - 2026-09-02

## Scope

G04 has no court lock on broadcast basketball. This artifact therefore reports
only IMAGE_PX_DECLARED teacher proxies from the source-image bbox foot point.
Every output is stamped `coordinate_space=image_px`; it contains no court unit
or court-coordinate estimate.

`scripts/platformkit/tracking/basketball_imagepx_features.py` reads each
re-emitted table below `/tmp/t3b_reemit/` and writes one JSON file per game to
`/tmp/g04_features/<game>/imagepx_features.json`. The JSON retains the decoded
frame denominator, feature-specific `n_frames_used`, and coasted/camera-pan
exclusion counts. Pace pairs successive observed rows of a track and divides by
the decoded-frame gap at the stated 30 fps assumption. Camera motion is a
coherent median signed shift of at least 5 percent of frame width; frames so
flagged are excluded from pace, centroid-reversal, and spread proxies.

## Pod measurement

Command, run from `/workspace/nba-ai-system` after confirming all eight tables
were present:

```text
nohup setsid nice -n 15 python -m scripts.platformkit.tracking.basketball_imagepx_features --in /tmp/t3b_reemit --out /tmp/g04_features > /tmp/g04.log 2>&1 < /dev/null &
```

All eight outputs were written. `floor` is the median number of observed rows
per decoded frame; `8-10` is its decoded-frame share. `pace` is median
foot-point displacement per second divided by frame width; `rev/min` is the
5-percent-hysteresis centroid-x reversal proxy; `spread` is median per-frame
x standard deviation divided by frame width. They are dimensionless
image-plane quantities, not basketball statistics.

| game | decoded frames | floor | 8-10 | pace | rev/min | spread | pan share |
|---|---:|---:|---:|---:|---:|---:|---:|
| ncaa_basketball_IB-_u4gW3ds | 2,002 | 0.0 | 0.0305 | 0.0291 | 47.65 | 0.0775 | 0.0020 |
| ncaa_basketball_sRtHQbywiTE | 3,898 | 0.0 | 0.0003 | 0.0743 | 72.04 | 0.1355 | 0.0082 |
| ncaa_basketball_tiUvyvWOCxo | 3,268 | 0.0 | 0.0009 | 0.0737 | 88.68 | 0.1806 | 0.0098 |
| ncaa_basketball_zqBCKovJCQU | 5,698 | 0.0 | 0.0121 | 0.0662 | 58.76 | 0.1735 | 0.0063 |
| wnba_01 | 2,998 | 0.0 | 0.0057 | 0.0456 | 76.25 | 0.1245 | 0.0113 |
| wnba_02 | 3,178 | 0.0 | 0.0267 | 0.0590 | 91.76 | 0.1223 | 0.0038 |
| wnba_04 | 3,628 | 0.0 | 0.0050 | 0.0630 | 84.34 | 0.1272 | 0.0050 |
| wnba_05 | 4,348 | 0.0 | 0.0055 | 0.0789 | 34.36 | 0.1102 | 0.0032 |

The zero floor medians are expected from the actual stride-sampled tables:
most decoded frames contain no emitted row. This is why the JSON reports
feature availability rather than presenting a sampled row count as continuous
tracking. The per-feature usable-frame counts and exclusions were:

| game | pace frames | centroid frames | spread frames | pan frames | coasted rows |
|---|---:|---:|---:|---:|---:|
| ncaa_basketball_IB-_u4gW3ds | 573 | 574 | 574 | 4 | 0 |
| ncaa_basketball_sRtHQbywiTE | 712 | 713 | 713 | 32 | 0 |
| ncaa_basketball_tiUvyvWOCxo | 945 | 946 | 946 | 32 | 0 |
| ncaa_basketball_zqBCKovJCQU | 962 | 963 | 963 | 36 | 0 |
| wnba_01 | 964 | 965 | 965 | 34 | 0 |
| wnba_02 | 987 | 988 | 988 | 12 | 0 |
| wnba_04 | 978 | 979 | 979 | 18 | 0 |
| wnba_05 | 531 | 533 | 533 | 14 | 0 |

## Render-and-look

Six source frames evenly spaced across `wnba_01` were decoded on the pod. Green
crosses are source-pixel foot points; each overlay gives the observed row count
and calculated camera-pan flag.

- [frame 0](basketball_imagepx_features_2026-09-02/wnba_01_f000000.png)
- [frame 600](basketball_imagepx_features_2026-09-02/wnba_01_f000600.png)
- [frame 1200](basketball_imagepx_features_2026-09-02/wnba_01_f001200.png)
- [frame 1797](basketball_imagepx_features_2026-09-02/wnba_01_f001797.png)
- [frame 2397](basketball_imagepx_features_2026-09-02/wnba_01_f002397.png)
- [frame 2997](basketball_imagepx_features_2026-09-02/wnba_01_f002997.png)

Looked at all six. Wide views have several marks near player feet, while tight
shots visibly include non-floor people and crowd-side subjects. The selected
evenly spaced frames were all unflagged by this conservative pan rule; that is
not evidence that the game had no pans (34 sampled frames were flagged).

## Honest read and limits

These are image-plane teacher features only. They cannot identify players,
teams, lineups, possessions, ball ownership, court location, speed in physical
units, player spacing in physical units, or a basketball pace statistic.
Camera direction, broadcast cuts, zoom, crop, missed detections, false
detections, stride sampling, and the bbox-foot-point approximation can all move
the proxies. The pan flag is a conservative global-shift heuristic, not a
verified camera-motion model. No scoring, prediction, court transform, or
feature flag was changed.

## Local test

```text
python -m pytest scripts/platformkit/tracking/test_basketball_imagepx_features.py -q
# 1 passed
```
