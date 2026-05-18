#!/bin/bash
# Full 57-game batch — Phase 1: immediate 3-GPU launch on existing 41 videos,
# Phase 2: download+upload 13 remaining games, Phase 3: process those,
# Phase 4: pull all tracking data back to local.
#
# Usage: bash scripts/run_full_batch_57.sh
# Resume-safe: already-tracked games are skipped automatically.

set -euo pipefail

REMOTE_HOST="${RUNPOD_HOST:?Set RUNPOD_HOST}"
REMOTE_PORT="${RUNPOD_PORT:?Set RUNPOD_PORT}"
REMOTE="root@${REMOTE_HOST}"
REMOTE_DIR="/workspace/nba-ai-system"
LOCAL_TMP="data/videos/full_games"
SSH="ssh -o StrictHostKeyChecking=no -p ${REMOTE_PORT}"
SCP="scp -o StrictHostKeyChecking=no -P ${REMOTE_PORT}"

mkdir -p "$LOCAL_TMP"
mkdir -p data/tracking

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ---------------------------------------------------------------------------
# PHASE 1 — Kill stale procs, launch 3-GPU pipeline on current 41 videos
# ---------------------------------------------------------------------------
log "=== PHASE 1: Launching 3-GPU pipeline on current videos ==="

$SSH "$REMOTE" bash -s << 'REMOTE_PHASE1'
set -euo pipefail
PROJ=/workspace/nba-ai-system
VIDEOS=$PROJ/data/videos/full_games

# Kill any stale workers
pkill -f run_phase_g 2>/dev/null && echo "Killed stale procs" || echo "No stale procs"
pkill -f run_3gpu    2>/dev/null || true
sleep 2

# Build game list from videos on disk (skip already-tracked ones)
SKIP=()
for gdir in "$PROJ/data/tracking"/*/; do
  gid=$(basename "$gdir")
  rows=$(wc -l < "$gdir/tracking_data.csv" 2>/dev/null || echo 0)
  [ "$rows" -gt 10000 ] && SKIP+=("$gid")
done

ALL=()
while IFS= read -r f; do
  gid=$(basename "$f" .mp4)
  skip=0
  for s in "${SKIP[@]:-}"; do [ "$s" = "$gid" ] && skip=1 && break; done
  [ "$skip" -eq 0 ] && ALL+=("$gid")
done < <(find "$VIDEOS" -name "*.mp4" | sort)

TOTAL=${#ALL[@]}
if [ "$TOTAL" -eq 0 ]; then
  echo "No videos to process — exiting Phase 1"
  exit 0
fi

PER=$(( (TOTAL + 2) / 3 ))
G0=("${ALL[@]:0:$PER}")
G1=("${ALL[@]:$PER:$PER}")
G2=("${ALL[@]:$(($PER*2))}")

cd "$PROJ"
echo "[$(date '+%H:%M:%S')] $TOTAL games split across 3 GPUs (${#G0[@]} / ${#G1[@]} / ${#G2[@]})"

CUDA_VISIBLE_DEVICES=0 nohup python3 -u scripts/run_phase_g.py \
  --game-ids "${G0[@]}" --frames 18000 \
  > /workspace/gpu0.log 2>&1 &
echo "[GPU0] PID $! — ${G0[*]}"

CUDA_VISIBLE_DEVICES=1 nohup python3 -u scripts/run_phase_g.py \
  --game-ids "${G1[@]}" --frames 18000 \
  > /workspace/gpu1.log 2>&1 &
echo "[GPU1] PID $! — ${G1[*]}"

CUDA_VISIBLE_DEVICES=2 nohup python3 -u scripts/run_phase_g.py \
  --game-ids "${G2[@]}" --frames 18000 \
  > /workspace/gpu2.log 2>&1 &
echo "[GPU2] PID $! — ${G2[*]}"

echo "All 3 GPU workers launched — $TOTAL games queued"
REMOTE_PHASE1

log "Phase 1 launched. 3 GPU workers running on the pod."

# ---------------------------------------------------------------------------
# PHASE 2 — Download + upload remaining 13 games not yet on the pod
# ---------------------------------------------------------------------------
log "=== PHASE 2: Downloading + uploading remaining games ==="

# Games from local_download_remote_process.sh NOT already on the pod
# Pod has: 033-068, 574-577, 581-586, 591-592  (41 total)
REMAINING=(
  "4MoMewm2j-o|0022500622|BKN vs NYK"
  "Nabp76SLZaM|0022500630|GSW vs DAL"
  "tu8IOgZoWm0|0022500629|DEN vs WAS"
  "-_d4k1r6x7M|0022500624|DET vs NOP"
  "gZde9IkIf7o|0022500621|IND vs BOS"
  "coYlCAzzpjI|0022500906|LAL vs DEN"
  "4uxDaDDzuic|0022500809|LAL vs LAC"
  "lYdjynqOzl4|0022500634|MIA vs POR"
  "mg-1tlNMQCs|0022500601|UTA vs DAL"
  "5-RZCY3agIE|0022500623|ATL vs MEM"
  "kLwhJOEjoH0|0022500594|PHX vs DET"
  "FZAUuuuREg0|0022500593|OKC vs HOU"
  "0nz5c3sNzKE|0022500609|MEM vs ORL"
)

UPLOADED=()
for entry in "${REMAINING[@]}"; do
  IFS='|' read -r YT_ID GAME_ID MATCHUP <<< "$entry"

  # Skip if already tracked on pod
  ROWS=$($SSH "$REMOTE" "wc -l < $REMOTE_DIR/data/tracking/$GAME_ID/tracking_data.csv 2>/dev/null || echo 0" 2>/dev/null || echo 0)
  if [ "${ROWS:-0}" -gt 10000 ]; then
    log "  $GAME_ID already tracked ($ROWS rows) — skipping"
    continue
  fi

  LOCAL_FILE="$LOCAL_TMP/${GAME_ID}.mp4"

  # Download if not present
  if [ ! -f "$LOCAL_FILE" ] || [ "$(stat -c%s "$LOCAL_FILE" 2>/dev/null || echo 0)" -lt 10000000 ]; then
    log "  Downloading $GAME_ID ($MATCHUP) from YouTube..."
    yt-dlp -f 'best[height<=720]/best' "https://www.youtube.com/watch?v=$YT_ID" \
      -o "$LOCAL_FILE" --no-part --quiet --progress 2>&1 | tail -3
    if [ ! -f "$LOCAL_FILE" ]; then
      log "  DOWNLOAD FAILED for $GAME_ID — skipping"
      continue
    fi
  fi
  SIZE=$(du -h "$LOCAL_FILE" | cut -f1)
  log "  $GAME_ID downloaded ($SIZE) — uploading to pod..."

  # Upload to pod
  $SSH "$REMOTE" "mkdir -p $REMOTE_DIR/data/videos/full_games"
  $SCP "$LOCAL_FILE" "$REMOTE:$REMOTE_DIR/data/videos/full_games/${GAME_ID}.mp4"
  log "  $GAME_ID uploaded"

  UPLOADED+=("$GAME_ID")

  # Clean up local video to save disk space
  rm -f "$LOCAL_FILE"
done

log "Phase 2 complete. Uploaded: ${#UPLOADED[@]} games (${UPLOADED[*]:-none})"

# ---------------------------------------------------------------------------
# PHASE 3 — Process the newly uploaded games on all 3 GPUs
# ---------------------------------------------------------------------------
if [ "${#UPLOADED[@]}" -gt 0 ]; then
  log "=== PHASE 3: Waiting for Phase 1 to finish, then processing new uploads ==="

  # Wait for Phase 1 GPU workers to finish
  $SSH "$REMOTE" bash << 'WAIT_PHASE1'
while pgrep -f run_phase_g > /dev/null; do
  echo "[$(date '+%H:%M:%S')] GPU workers still running... $(pgrep -c -f run_phase_g) active"
  sleep 60
done
echo "[$(date '+%H:%M:%S')] Phase 1 complete — all GPU workers done"
WAIT_PHASE1

  log "Phase 1 finished. Launching Phase 3 for ${#UPLOADED[@]} new games..."

  UPLOAD_LIST="${UPLOADED[*]}"
  $SSH "$REMOTE" bash -s <<< "
set -euo pipefail
PROJ=/workspace/nba-ai-system
cd \"\$PROJ\"

ALL=($UPLOAD_LIST)
TOTAL=\${#ALL[@]}
PER=\$(( (TOTAL + 2) / 3 ))
G0=(\"\${ALL[@]:0:\$PER}\")
G1=(\"\${ALL[@]:\$PER:\$PER}\")
G2=(\"\${ALL[@]:\$((\$PER*2))}\")

CUDA_VISIBLE_DEVICES=0 nohup python3 -u scripts/run_phase_g.py --game-ids \${G0[@]:+\"\${G0[@]}\"} --frames 18000 > /workspace/gpu0_p3.log 2>&1 &
echo \"[GPU0-P3] PID \$!\"
CUDA_VISIBLE_DEVICES=1 nohup python3 -u scripts/run_phase_g.py --game-ids \${G1[@]:+\"\${G1[@]}\"} --frames 18000 > /workspace/gpu1_p3.log 2>&1 &
echo \"[GPU1-P3] PID \$!\"
CUDA_VISIBLE_DEVICES=2 nohup python3 -u scripts/run_phase_g.py --game-ids \${G2[@]:+\"\${G2[@]}\"} --frames 18000 > /workspace/gpu2_p3.log 2>&1 &
echo \"[GPU2-P3] PID \$!\"
echo \"Phase 3 — \$TOTAL games launched across 3 GPUs\"

# Wait for completion
wait
echo \"[Phase 3] All done\"
"
fi

# ---------------------------------------------------------------------------
# PHASE 4 — Wait for ALL workers to finish, then pull data back
# ---------------------------------------------------------------------------
log "=== PHASE 4: Waiting for all workers, then pulling tracking data ==="

$SSH "$REMOTE" bash << 'WAIT_ALL'
while pgrep -f run_phase_g > /dev/null; do
  ACTIVE=$(pgrep -c -f run_phase_g)
  echo "[$(date '+%H:%M:%S')] $ACTIVE GPU worker(s) still running..."
  sleep 60
done
echo "[$(date '+%H:%M:%S')] All GPU workers done"

# Print summary
PROJ=/workspace/nba-ai-system
echo ""
echo "=== TRACKING SUMMARY ==="
for gdir in "$PROJ/data/tracking"/*/; do
  gid=$(basename "$gdir")
  rows=$(wc -l < "$gdir/tracking_data.csv" 2>/dev/null || echo "NO DATA")
  echo "  $gid: $rows rows"
done
WAIT_ALL

log "Pulling all tracking data to local data/tracking/..."
$SSH "$REMOTE" "ls /workspace/nba-ai-system/data/tracking/" | while read -r GAME_ID; do
  [ -z "$GAME_ID" ] && continue
  mkdir -p "data/tracking/$GAME_ID"
  $SCP -r "$REMOTE:$REMOTE_DIR/data/tracking/$GAME_ID/" "data/tracking/" 2>/dev/null || \
    log "  WARNING: failed to sync $GAME_ID"
  ROWS=$(wc -l < "data/tracking/$GAME_ID/tracking_data.csv" 2>/dev/null || echo 0)
  log "  $GAME_ID: $ROWS rows pulled"
done

log "=== ALL DONE ==="
$SSH "$REMOTE" "echo 'GPU0 tail:' && tail -5 /workspace/gpu0.log 2>/dev/null; echo 'GPU1 tail:' && tail -5 /workspace/gpu1.log 2>/dev/null; echo 'GPU2 tail:' && tail -5 /workspace/gpu2.log 2>/dev/null"

TOTAL_TRACKED=$(ls -d data/tracking/*/  2>/dev/null | wc -l)
log "Final: $TOTAL_TRACKED game directories pulled to data/tracking/"
