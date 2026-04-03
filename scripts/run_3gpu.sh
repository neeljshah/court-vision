#!/bin/bash
# Run pipeline across 3 GPUs on RunPod.
# Waits for all videos to finish uploading, then splits across GPU 0/1/2.
PROJ=/workspace/nba-ai-system
VIDEOS=$PROJ/data/videos/full_games
LOG=/workspace

echo "[$(date '+%H:%M:%S')] Waiting for 50+ videos in $VIDEOS ..."
while true; do
  COUNT=$(find "$VIDEOS" -name "*.mp4" 2>/dev/null | wc -l)
  echo "  $COUNT videos on disk..."
  [ "$COUNT" -ge 50 ] && break
  sleep 20
done

echo "[$(date '+%H:%M:%S')] $COUNT videos ready — building game list..."

# Build sorted game ID list
mapfile -t GAMES < <(find "$VIDEOS" -name "*.mp4" | xargs -I{} basename {} .mp4 | sort)
TOTAL=${#GAMES[@]}
PER=$(( (TOTAL + 2) / 3 ))

IDS0="${GAMES[@]:0:$PER}"
IDS1="${GAMES[@]:$PER:$PER}"
IDS2="${GAMES[@]:$(($PER*2))}"

echo "[$(date '+%H:%M:%S')] $TOTAL games — GPU0: $PER, GPU1: $PER, GPU2: rest"
echo "  GPU0: $IDS0"
echo "  GPU1: $IDS1"
echo "  GPU2: $IDS2"

cd "$PROJ"

CUDA_VISIBLE_DEVICES=0 nohup python3 -u scripts/run_phase_g.py \
  --game-ids $IDS0 --frames 18000 --parallel 3 \
  > "$LOG/gpu0.log" 2>&1 &
PID0=$!
echo "[GPU0] PID $PID0 started"

CUDA_VISIBLE_DEVICES=1 nohup python3 -u scripts/run_phase_g.py \
  --game-ids $IDS1 --frames 18000 --parallel 3 \
  > "$LOG/gpu1.log" 2>&1 &
PID1=$!
echo "[GPU1] PID $PID1 started"

CUDA_VISIBLE_DEVICES=2 nohup python3 -u scripts/run_phase_g.py \
  --game-ids $IDS2 --frames 18000 --parallel 3 \
  > "$LOG/gpu2.log" 2>&1 &
PID2=$!
echo "[GPU2] PID $PID2 started"

echo "[$(date '+%H:%M:%S')] All 3 GPU pipelines running. Tailing gpu0.log..."
wait $PID0 $PID1 $PID2
echo "[$(date '+%H:%M:%S')] ALL DONE"
