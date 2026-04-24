# Preflight Triage Report
Generated: 2026-04-15

## Summary

5 entries in `data/phase_g_processed.txt` carry `_PREFLIGHT_FAIL` suffix.
All 5 were probed with `cv2.VideoCapture` (ffprobe unavailable on this host).
All 5 are **AV1-encoded** (fourcc=`AV01`) — decoder lacks hardware AV1 support.

## Results

| game_id     | fourcc | frames  | fps  | size (MB) | classification |
|-------------|--------|---------|------|-----------|----------------|
| 0022400625  | AV01   | 367,978 | 59.9 | 1503.1    | AV1            |
| 0022400687  | AV01   |  62,959 | 59.9 |  292.7    | AV1            |
| 0022400689  | AV01   |  55,147 | 59.9 |  250.4    | AV1            |
| 0022400710  | AV01   |  22,380 | 30.0 |  110.2    | AV1            |
| 0022400852  | AV01   |  22,380 | 30.0 |  110.2    | AV1            |

**Note:** `0022400625` also has a tracking dir with 819,604 rows — it was partially
processed before the AV1 quarantine policy was introduced (likely via a codec fallback
that is no longer active). Its existing tracking data is preserved; the source video is
now quarantined to prevent re-queuing.

## Action Taken

Files moved to `data/videos/full_games_av1_quarantine/`:
- 0022400625.mp4
- 0022400687.mp4
- 0022400689.mp4
- 0022400710.mp4
- 0022400852.mp4

## Resolution Options

1. **Re-encode**: `ffmpeg -i <game>.mp4 -c:v libx264 -crf 22 -preset fast <game>_h264.mp4`
   then move H.264 version back to `full_games/`. Adds ~30–60 min CPU per file.
2. **Skip**: These 5 games are excluded from Phase G. 2024-25 season has ample
   H.264 alternatives.
3. **RunPod with AV1 support**: Some newer ffmpeg builds include libaom-av1 decoding.
   Not available on current RTX 4090 pod image.
