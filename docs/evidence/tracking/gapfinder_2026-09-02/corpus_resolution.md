# Pod footage-corpus resolution census (2026-09-02, gap-finder lane)

Read-only measurement on the pod (213.192.2.83:40048), repo
`/workspace/nba-ai-system`. Every `data/footage_corpus/*.mp4` opened with
`cv2.VideoCapture` and read for width/height/frame-count/fps only (no decode).
Raw rows: `pod_corpus_census.json` (61 objects, one per file).

## The number

25 of 61 clips (41.0 pct) are 640x360. 26 are 1280x720, 10 are 1920x1080.

| sport prefix | clips | 360p | 720p | 1080p |
|---|---:|---:|---:|---:|
| football | 9 | 6 | 1 | 2 |
| kbo | 11 | 8 | 3 | 0 |
| mlb | 10 | 3 | 7 | 0 |
| ncaa_basketball | 6 | 2 | 2 | 2 |
| npb | 6 | 4 | 2 | 0 |
| soccer | 5 | 0 | 4 | 1 |
| tennis | 9 | 2 | 3 | 4 |
| wnba | 5 | 0 | 4 | 1 |

The skew is by sport, not uniform: the baseball family (mlb + kbo + npb) is
15 of 27 clips (55.6 pct) at 360p and football is 6 of 9 (66.7 pct), while
soccer and wnba are 0 of 10. Every clip that has produced a landed baseball
evidence number (mlb_2iosUkpL0Bc, mlb_3Oc4S_1np98, mlb_ARtRmUHC7dw,
mlb_gMm3EODDb6w) is 720p; no 360p baseball clip appears in any landed result.

## Why it is a gap, not a fact

Line/court detection is resolution-sensitive by construction (the top-hat
kernel in `domains/tennis/tracking/court_lines.py` is scaled by frame height;
the ingest memo measured 3.7x on line detection between itag 18 and HLS).
The daemon ledger row (`data/tracking/track_daemon_ledger.jsonl`) carries
`game_id, sport, status, rows, passed, failures, seconds, tail` and no source
resolution, and the `data/tracking/<game>/tracking_data.csv` tables written by
the daemon carry no `frame_width`/`frame_height` columns either (header is
`frame,track_id,cls,x,y,coordinate_calibration_reason,coordinate_space,
observation,calibration`). So every per-sport harness verdict pools 360p and
1080p sources with no way to stratify after the fact.

## Achievable limit

Re-ingest the 25 clips with the `--cookies` + HLS 300/301 recipe from the
ingest-resolution memo and stamp `source_height` into the ledger row; the
ceiling is whatever height YouTube still serves for that video id, so the
honest target is a stratified denominator, not 0 clips at 360p.
