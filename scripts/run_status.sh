#!/bin/bash
# run_status.sh — one-shot snapshot of pod-run state.
# Usage: bash scripts/run_status.sh <pod_ip> <ssh_port>
set -uo pipefail
IP="${1:?usage: run_status.sh <pod_ip> <ssh_port>}"
PORT="${2:?usage: run_status.sh <pod_ip> <ssh_port>}"
SSH="ssh -p ${PORT} -o ConnectTimeout=10 root@${IP}"

# Single SSH session, single python call — avoids round-trip overhead.
$SSH 'PROJ=/workspace/nba-ai-system; cd $PROJ || exit 1
BL=$PROJ/phase_g_batch_gpu0.log
# 30s throughput sample.
c1=$(grep -c "Frame " "$BL" 2>/dev/null); sleep 30
c2=$(grep -c "Frame " "$BL" 2>/dev/null); fps=$(( (c2 - c1) * 3 / 30 ))

DONE=$(grep -cvE "^hash:" $PROJ/data/phase_g_processed.txt 2>/dev/null)
SV=$(ps -eo args | awk "\$1==\"bash\" && \$2==\"/workspace/supervisor.sh\""|wc -l)
DL=$(ps -eo args | awk "\$1==\"bash\" && \$2==\"/workspace/downloader.sh\""|wc -l)
WD=$(ps -eo args | awk "\$1==\"bash\" && \$2==\"/workspace/disk_watchdog.sh\""|wc -l)
PG=$(ps -eo pid,comm | awk "\$2==\"python3\"{print \$1}" | while read x; do
       tr "\0" " " </proc/$x/cmdline 2>/dev/null | grep -q scripts/run_phase_g.py && echo y
     done | wc -l)
MPS=$(ps -eo args | grep -c "[c]uda-mps-server")
WORKERS=$(pgrep -fc run_clip.py)
VIDS=$(ls /root/nba_videos/*.mp4 2>/dev/null | wc -l)
INPROG=$(for d in $PROJ/data/tracking/*/; do
           g=$(basename $d); grep -qx "$g" $PROJ/data/phase_g_processed.txt 2>/dev/null || echo y
         done | wc -l)
QPEND=$(python3 -c "import sqlite3;print(sqlite3.connect(\"$PROJ/data/ingest/queue.db\").execute(\"SELECT COUNT(*) FROM games WHERE status=\x27queued\x27\").fetchone()[0])" 2>/dev/null)
DLOK=$(grep -c " OK " /workspace/downloader.log 2>/dev/null)
DLFAIL=$(grep -c "FAIL\|REJECT" /workspace/downloader.log 2>/dev/null)
ERR=$(grep -cE "Traceback|\[CRASH\]|CUDA error|MEM FATAL" "$BL" 2>/dev/null)
GPU=$(nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv,noheader|tr -d "\n")
RSS=$(ps -o rss= -C python3 2>/dev/null|awk "{s+=\$1}END{printf \"%.1f\",s/1048576}")
ROOT_FREE=$(df -h /root|tail -1|awk "{print \$4}")

echo "─── pod-run status ──────────────────────────────────────"
echo "loops          : supervisor=$SV  downloader=$DL  watchdog=$WD  mps=$MPS  run_phase_g=$PG ($WORKERS workers)"
echo "throughput     : ${fps} fps (30s sample)"
echo "games          : done=$DONE  in-progress=$INPROG  videos-staged=$VIDS  download-queue=$QPEND"
echo "downloads      : ok=$DLOK  fail/reject=$DLFAIL"
echo "GPU            : $GPU"
echo "RAM            : ${RSS}GB / 116GB cgroup"
echo "disk /root     : $ROOT_FREE free"
echo "errors in log  : $ERR"

echo
echo "─── recent completed games (last 5) ─────────────────────"
tail -5 $PROJ/data/phase_g_metrics.csv 2>/dev/null | awk -F, '\''NR>0 {printf "  %-12s  frames=%-7s  ball=%5.1f%%  stab=%s  id_sw=%s  quality=%s\n", $2, $4, $7, $5, $6, $8}'\'' 2>/dev/null

echo
echo "─── in-progress (current Stage-1 frame) ─────────────────"
grep -oE "Frame [0-9]+" "$BL" 2>/dev/null | tail -8 | sort -u | tail -8

# rough ETA: remaining-frames / fps
REM=$(( (VIDS - INPROG) * 220000 + INPROG * 100000 ))
if [ "$fps" -gt 10 ]; then
    H=$(( REM / fps / 3600 )); M=$(( (REM / fps % 3600) / 60 ))
    echo
    echo "ETA (rough): ${H}h ${M}m at current fps to clear staged videos"
fi
'