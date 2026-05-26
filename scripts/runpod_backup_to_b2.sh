#!/bin/bash
# =============================================================================
# runpod_backup_to_b2.sh — R16 companion: upload pod artefacts to B2
#
# The runpod_bootstrap.sh script EXPECTS these artefacts to be on B2:
#   - /root/nba_videos/*.mp4               (23 GB) → b2:<bucket>/full_games/
#   - /workspace/nba-ai-system/data/models/ (48 MB) → b2:<bucket>/models/
#   - /workspace/nba-ai-system/data/nba/    (126 MB) → b2:<bucket>/nba_cache/
#   - /workspace/nba-ai-system/data/cache/  (77 MB)  → b2:<bucket>/cache/
#   - /workspace/nba-ai-system/resources/   (small)  → b2:<bucket>/resources/
#
# This script uploads all of them in one go. Run it ON THE POD before stopping
# the pod (when you have artefacts you want to preserve), or from your laptop
# (uses local copies).
#
# Setup (one-time):
#   1. Create B2 bucket: https://secure.backblaze.com/b2_buckets.htm
#   2. Generate application key with read+write to that bucket
#   3. Install rclone: curl https://rclone.org/install.sh | sudo bash
#   4. Configure: rclone config → create remote named 'b2' (type: Backblaze B2)
#   5. Set B2_BUCKET=<your-bucket> in .env
#
# Usage:
#   bash scripts/runpod_backup_to_b2.sh                 # uses defaults
#   bash scripts/runpod_backup_to_b2.sh /custom/path    # custom source dir
# =============================================================================
set -euo pipefail

# Source .env to get B2_BUCKET (and any rclone config env vars)
if [ -f .env ]; then
    set -a; source .env; set +a
fi

: "${B2_BUCKET:?Set B2_BUCKET in .env (e.g. courtvision-prod-backup)}"

# Source paths — auto-detect pod vs laptop layout
if [ -d /workspace/nba-ai-system ]; then
    POD_ROOT=/workspace/nba-ai-system
    VIDEO_DIR=/root/nba_videos
elif [ -d "$(pwd)/data/models" ]; then
    POD_ROOT="$(pwd)"
    VIDEO_DIR="$(pwd)/data/videos/full_games"
else
    echo "ERROR: can't find data/models/ or /workspace/nba-ai-system" >&2
    exit 1
fi

echo "================================================================================"
echo "B2 backup: source=${POD_ROOT}, videos=${VIDEO_DIR}, target=b2:${B2_BUCKET}"
echo "================================================================================"

# rclone tuning for upload speed (B2 is happy with ~16 parallel uploads)
RCLONE_OPTS="--transfers 16 --checkers 16 --b2-chunk-size 64M --progress"

# 1. Models (critical — weeks of training, no other source)
if [ -d "${POD_ROOT}/data/models" ]; then
    echo "[1/5] Uploading models (~48 MB, 111 files)..."
    rclone sync "${POD_ROOT}/data/models/" "b2:${B2_BUCKET}/models/" $RCLONE_OPTS
fi

# 2. NBA cache (boxscores, rosters — re-fetchable but slow)
if [ -d "${POD_ROOT}/data/nba" ]; then
    echo "[2/5] Uploading NBA cache (~126 MB)..."
    rclone sync "${POD_ROOT}/data/nba/" "b2:${B2_BUCKET}/nba_cache/" $RCLONE_OPTS
fi

# 3. General cache (predictions, parquets, bankroll state)
if [ -d "${POD_ROOT}/data/cache" ]; then
    echo "[3/5] Uploading data/cache (~77 MB)..."
    rclone sync "${POD_ROOT}/data/cache/" "b2:${B2_BUCKET}/cache/" $RCLONE_OPTS \
        --exclude '*.tmp' --exclude '*.lock'
fi

# 4. Resources (court anchors, ONNX, rectify matrices)
if [ -d "${POD_ROOT}/resources" ]; then
    echo "[4/5] Uploading resources/..."
    rclone sync "${POD_ROOT}/resources/" "b2:${B2_BUCKET}/resources/" $RCLONE_OPTS
fi

# 5. Videos (BIG — only sync new files)
if [ -d "${VIDEO_DIR}" ]; then
    echo "[5/5] Uploading videos (sync only NEW files)..."
    rclone copy "${VIDEO_DIR}/" "b2:${B2_BUCKET}/full_games/" \
        --include '*.mp4' --max-age 30d $RCLONE_OPTS
else
    echo "[5/5] WARN: no video dir at ${VIDEO_DIR} — skipping"
fi

echo ""
echo "================================================================================"
echo "BACKUP COMPLETE."
echo "  Bucket usage: $(rclone size b2:${B2_BUCKET}/ 2>/dev/null | grep Total || echo '(rclone size unavailable)')"
echo "  Restore on fresh pod: bash scripts/runpod_bootstrap.sh <IP> <PORT>"
echo "  (bootstrap will rclone-pull from this bucket automatically)"
echo "================================================================================"
