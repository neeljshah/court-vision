#!/bin/bash
# Periodic utilization sampler for RunPod 4090 pod.
# Writes one CSV row per 60s to /workspace/nba-ai-system/stats_log.csv
STATSFILE=/workspace/nba-ai-system/stats_log.csv
LOGFILE=/workspace/nba-ai-system/phase_g_batch.log
QUOTA_CORES=13.6

if [ ! -f "$STATSFILE" ]; then
  echo 'ts,load1,load5,cpu_pct,nr_throttled,gpu_util,vram_mb,ram_used_gb,overlay_gb,workers,max_frame' > "$STATSFILE"
fi

while true; do
  ts=$(date +%s)
  read l1 l5 _ < /proc/loadavg
  cpu_pct=$(awk -v l="$l1" -v q="$QUOTA_CORES" 'BEGIN{printf "%.1f", l/q*100}')
  nr_t=$(awk '/nr_throttled/{print $2}' /sys/fs/cgroup/cpu.stat 2>/dev/null)
  gpu=$(nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' ')
  gpu_util=$(echo "$gpu" | cut -d, -f1)
  vram=$(echo "$gpu" | cut -d, -f2)
  ram=$(free -g | awk '/Mem:/{print $3}')
  overlay=$(df -BG / | awk 'NR==2{gsub("G",""); print $3}')
  workers=$(pgrep -f run_clip.py 2>/dev/null | wc -l)
  max_frame=$(grep -oE 'Frame [0-9]+' "$LOGFILE" 2>/dev/null | awk '{print $2}' | sort -n | tail -1)
  echo "$ts,$l1,$l5,$cpu_pct,$nr_t,$gpu_util,$vram,$ram,$overlay,$workers,$max_frame" >> "$STATSFILE"
  sleep 60
done
