#!/bin/bash
# sync_to_pod.sh — Local-side: push everything a fresh RunPod needs, then run
# the pod-side bootstrap. One command from local repo to fully-running pod.
#
# Usage:
#   bash scripts/sync_to_pod.sh <pod_ip> <ssh_port>
#   bash scripts/sync_to_pod.sh 213.192.2.86 40045
#
# Expects (locally):
#   data/videos/youtube_cookies.txt    — YouTube auth for downloader
#   data/ingest/queue.db               — discovered games queue
#   data/nba/                          — NBA play-by-play cache (~75MB)
#   data/videos/full_games/*.mp4       — optional: pre-staged videos
#
# Assumes ssh key works (agent or default ~/.ssh/id_rsa). If you have a specific
# key, set SSH_KEY=path/to/key first.

set -euo pipefail
IP="${1:?usage: sync_to_pod.sh <pod_ip> <ssh_port>}"
PORT="${2:?usage: sync_to_pod.sh <pod_ip> <ssh_port>}"
SSH="ssh -p ${PORT} -o StrictHostKeyChecking=accept-new ${SSH_KEY:+-i $SSH_KEY} root@${IP}"
SSH_RAW="ssh -p ${PORT} -o StrictHostKeyChecking=accept-new ${SSH_KEY:+-i $SSH_KEY}"

ts() { date '+%T'; }

echo "[$(ts)] === sync_to_pod → ${IP}:${PORT} ==="

# 1. Sanity-check connectivity.
$SSH 'echo connected; nvidia-smi --query-gpu=name --format=csv,noheader|head -1' \
    || { echo "FATAL: ssh failed"; exit 1; }

# 2. Make target dirs.
$SSH 'mkdir -p /workspace/nba-ai-system/data/{nba,ingest,videos,tracking,events} /root/nba_videos'

# 3. Push code + models + resources (no videos, no .git, no __pycache__).
#    CRITICAL: exclude *.engine — engines are GPU-specific; pod must rebuild.
echo "[$(ts)] pushing code (~few MB) ..."
tar czf - \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='*.engine' \
    src scripts models resources api config requirements.txt pytest.ini .env \
    yolov8n.pt yolov8n-pose.pt 2>/dev/null \
  | $SSH_RAW root@${IP} 'tar xzf - --no-same-owner -C /workspace/nba-ai-system'

# 4. Push pipeline loop scripts from the repo to the pod's /workspace.
#    (The loops live at /workspace/ on the pod so they survive a code re-sync.)
echo "[$(ts)] pushing loop scripts ..."
for s in disk_watchdog.sh supervisor.sh downloader.sh; do
    if [ -f "scripts/loops/${s}" ]; then
        cat "scripts/loops/${s}" | $SSH "cat > /workspace/${s} && sed -i 's/\r$//' /workspace/${s} && chmod +x /workspace/${s}"
    else
        echo "  WARN: scripts/loops/${s} not found in repo — skipping"
    fi
done

# 5. Push NBA cache + queue + cookies.
echo "[$(ts)] pushing data ..."
tar cf - data/nba data/ingest/queue.db data/videos/youtube_cookies.txt 2>/dev/null \
  | $SSH_RAW root@${IP} 'tar xf - --no-same-owner -C /workspace/nba-ai-system'

# 6. Optional: push pre-staged videos (h264 only — bootstrap codec-scans anyway).
if [ -d data/videos/full_games ] && [ "${SYNC_VIDEOS:-0}" = "1" ]; then
    echo "[$(ts)] pushing pre-staged videos (will codec-scan on pod) ..."
    cd data/videos/full_games
    for f in [0-9]*.mp4; do
        sz=$(stat -c%s "$f" 2>/dev/null || echo 0)
        [ "$sz" -ge 200000000 ] && [ "$sz" -le 5000000000 ] && echo "$f"
    done > /tmp/sync_vidlist.txt
    cd -
    tar cf - -C data/videos/full_games -T /tmp/sync_vidlist.txt \
      | $SSH_RAW root@${IP} 'tar xf - --no-same-owner -C /root/nba_videos'
fi

# 7. Run the pod-side bootstrap.
echo "[$(ts)] running pod bootstrap ..."
$SSH 'bash /workspace/nba-ai-system/scripts/pod_bootstrap.sh' \
    || { echo "FATAL: pod bootstrap failed"; exit 1; }

echo "[$(ts)] === sync complete — pipeline running on ${IP}:${PORT} ==="
echo "Monitor: ssh -p ${PORT} root@${IP} 'tail -f /workspace/nba-ai-system/phase_g_batch_gpu0.log'"
