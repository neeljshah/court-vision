#!/usr/bin/env bash
# G283: disk-guarded span downsample, same-route detection arms, and blind packet only.
set -euo pipefail
video=/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4
artifact=docs/evidence/tracking/g283_resolution_control_artifact
downsample="$artifact/wnba_01_span_1280x720.mp4"
declare -A lanes=()
for proc in /proc/[0-9]*; do
  cwd="$(readlink "$proc/cwd" 2>/dev/null || true)"
  case "$cwd" in /workspace/wt/a[0-9]*) ;; *) continue ;; esac
  [ "$cwd" = /workspace/wt/a5 ] || lanes["$cwd"]=1
done
printf 'G283_GPU='
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
printf 'G283_LANES_SET='
printf '%s\n' "${!lanes[@]}" | sort | paste -sd, -
printf 'G283_OCCUPANCY_COUNT=%d\n' "${#lanes[@]}"
[ "${#lanes[@]}" -lt 2 ] || exit 75
du -sm /workspace
dd if=/dev/zero of=/workspace/wt/a5/g283_fsync_probe.bin bs=1048576 count=8 conv=fsync status=none
rm -f /workspace/wt/a5/g283_fsync_probe.bin
mkdir -p "$artifact"
du -sm /workspace | tee "$artifact/pod_disk_before.txt"
printf '%s\n' 'ffmpeg -hide_banner -loglevel error -ss 00:10:53.300 -i /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 -map 0:v:0 -an -sn -dn -frames:v 3801 -vf scale=1280:720:flags=lanczos -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -movflags +faststart docs/evidence/tracking/g283_resolution_control_artifact/wnba_01_span_1280x720.mp4' > "$artifact/ffmpeg_command.txt"
ffmpeg -hide_banner -loglevel error -ss 00:10:53.300 -i "$video" -map 0:v:0 -an -sn -dn -frames:v 3801 -vf "scale=1280:720:flags=lanczos" -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -movflags +faststart "$downsample"
python -m scripts.platformkit.tracking.g283_resolution_control prepare --video-1080 "$video" --video-720 "$downsample" --output "$artifact"
downsample_bytes=$(stat -c %s "$downsample")
rm -f "$downsample"
printf 'G283_DOWNSAMPLE_BYTES_FREED=%s\n' "$downsample_bytes" | tee "$artifact/downsample_cleanup.txt"
du -sm /workspace | tee "$artifact/pod_disk_after.txt"
tar -C "$artifact" -czf "$artifact/blind_packet.tar.gz" blind_order_commitment.json blind_presentation_order.csv blind_verdicts.csv blind_renders
