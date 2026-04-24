#!/bin/bash
# launch_single_3090_pod.sh — one-command pod setup + orchestrator start for a single RTX 3090.
#
# $5 budget target: 80 good games from 17 existing = 63 more needed.
# At ~10 good games/hr on single 3090: ~6-7 hrs @ $0.35-0.50/hr = $2.10-3.50
#
# Usage (run once after SSH into pod):
#   cd /workspace/nba-ai-system
#   bash scripts/launch_single_3090_pod.sh
#
# Optional — YouTube cookies (doubles download success rate):
#   Copy browser cookies to: data/videos/youtube_cookies.txt
#   Then run this script. fetch_games.py auto-detects and uses them.

set -uo pipefail
PROJ="/workspace/nba-ai-system"
cd "$PROJ"

echo "=== Single 3090 pod setup ==="

# ── Step 0: Preflight — fail loudly before wasting compute ──────────────────
bash scripts/ingest_preflight.sh || exit 1

# ── Step 1: pip install decord (GPU video decode, frees ~1.5 CPU cores/worker) ──
pip install decord -q && echo "decord OK" || echo "decord failed (non-fatal)"

# ── Step 2: Stage video dir on fast local disk ──────────────────────────────────
VIDEOS="/root/nba_videos"
mkdir -p "$VIDEOS"
ln -sfn "$VIDEOS" data/videos/full_games
echo "videos dir: $VIDEOS (symlinked)"

# ── Step 2b: Verify symlink resolves (overlay FS relative symlinks can break) ───
if ! ls data/videos/full_games/ >/dev/null 2>&1; then
  echo "ERROR: data/videos/full_games/ symlink does not resolve."
  echo "  Fix: mkdir -p /root/nba_videos && ln -sfn /root/nba_videos data/videos/full_games"
  exit 1
fi
echo "symlink OK: data/videos/full_games/ → $(readlink data/videos/full_games)"

# ── Step 3: Preflight check — VRAM_FLUSH must be 3000 ───────────────────────────
FLUSH=$(grep -oE '_VRAM_FLUSH_INTERVAL = [0-9]+' src/pipeline/unified_pipeline.py | head -1)
case "$FLUSH" in
  *3000*) echo "preflight OK: $FLUSH" ;;
  *)      echo "ERROR: _VRAM_FLUSH_INTERVAL != 3000 (got: $FLUSH). Fix before running."; exit 1 ;;
esac

# ── Step 4: Start cloud sync loop (push every 5 min) ───────────────────────────
if [ -f ".env" ] && grep -q "B2_BUCKET=" .env && grep -qv "B2_BUCKET=$" .env; then
  nohup python scripts/sync_remote.py --loop 5 --push > "$PROJ/sync.log" 2>&1 & disown
  echo "sync loop started (push every 5 min) — tail $PROJ/sync.log"
else
  echo "B2 creds not set in .env — skipping cloud sync loop"
fi

# ── Step 5: Start orchestrator ───────────────────────────────────────────────────
# Single 3090: PARALLEL=4 workers × ~2GB VRAM = ~8GB of 24GB used.
# OMP_NUM_THREADS=4: 4 workers × 4 threads = 16 threads (safe for 8-16 vCPU pods).
# BATCH=12: enough games to keep 4 workers busy without wasting download time.
# TARGET=90: aim for 90 good games total (17 existing + 73 new = buffer over 80 goal).
# Good-game rate: ~35% download success × ~65% quality = ~2-3 good games per batch.
# ~30 batches needed; each batch ~25 min → ~12 hrs max. Should finish in ~7-8 hrs.

echo ""
echo "=== Launching orchestrator (single 3090, PARALLEL=4) ==="
nohup env \
  TARGET=90 \
  BATCH=12 \
  FRAMES=18000 \
  PARALLEL=4 \
  SEGMENT=900 \
  CUDA_VISIBLE_DEVICES=0 \
  COURTV_NO_LOFTR=1 \
  MALLOC_ARENA_MAX=2 \
  PYTHONUNBUFFERED=1 \
  PHASE_G_STAGGER_S=0 \
  OMP_NUM_THREADS=4 \
  MKL_NUM_THREADS=4 \
  OPENBLAS_NUM_THREADS=4 \
  NUMEXPR_NUM_THREADS=4 \
  bash scripts/season_100_orchestrator.sh \
  > "$PROJ/orchestrator.log" 2>&1 & disown

sleep 2
echo "orchestrator PID: $(pgrep -f season_100_orchestrator | head -1)"
echo ""
echo "=== Health check in 60s ==="
echo "  tail -f $PROJ/orchestrator.log"
echo "  ps aux | grep run_clip | grep -v grep | wc -l   # expect 4 workers after first batch"
echo "  nvidia-smi   # expect ~8GB VRAM used across 4 workers"
echo ""
echo "=== Data sync (run locally after pod finishes) ==="
echo "  scp -P <PORT> root@<IP>:/workspace/nba-ai-system/data/phase_g_metrics.csv data/"
echo "  scp -P <PORT> root@<IP>:/workspace/nba-ai-system/data/phase_g_processed.txt data/"
echo "  rsync -az -e 'ssh -p <PORT>' root@<IP>:/workspace/nba-ai-system/data/tracking/ data/tracking/"
