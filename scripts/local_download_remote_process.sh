#!/bin/bash
# Download NBA full game videos locally (residential IP), upload to RunPod, process there.
# Usage: bash scripts/local_download_remote_process.sh

: "${RUNPOD_HOST:?Set RUNPOD_HOST=root@<ip>}"
REMOTE="$RUNPOD_HOST"
RPORT="${RUNPOD_PORT:?Set RUNPOD_PORT=<ssh_port>}"
REMOTE_DIR="/workspace/nba-ai-system"
LOCAL_TMP="data/videos/full_games"
PYTHON="python3"

mkdir -p "$LOCAL_TMP"

# YouTube video IDs and their NBA game IDs (from manuelmazon channel)
# Format: YT_ID|GAME_ID|MATCHUP
GAMES=(
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
  "3gBeJyl7Szg|0022500585|CLE vs PHI"
  "kLwhJOEjoH0|0022500594|PHX vs DET"
  "FZAUuuuREg0|0022500593|OKC vs HOU"
  "6pjxpCEZq8E|0022500591|MIL vs SAS"
  "0nz5c3sNzKE|0022500609|MEM vs ORL"
  "4aAQ31ApYcY|0022500592|BOS vs MIA"
  "7jKNSIUQ37Q|0022500575|SAS vs OKC"
  "SE6dodowjdM|0022500586|NYK vs SAC"
  "IL-rGv_wy1I|0022500576|UTA vs CHI"
  "4n_xzQVZmfs|0022500577|TOR vs IND"
)

PROCESSED=0
LIMIT=${1:-10}

for entry in "${GAMES[@]}"; do
  if [ "$PROCESSED" -ge "$LIMIT" ]; then
    echo "=== Reached limit of $LIMIT games ==="
    break
  fi

  IFS='|' read -r YT_ID GAME_ID MATCHUP <<< "$entry"
  echo ""
  echo "=== [$((PROCESSED+1))/$LIMIT] $GAME_ID $MATCHUP ==="

  # Check if already processed on pod
  ROWS=$(ssh -o StrictHostKeyChecking=no -p $RPORT $REMOTE "wc -l < $REMOTE_DIR/data/tracking/$GAME_ID/tracking_data.csv 2>/dev/null || echo 0")
  if [ "$ROWS" -gt 10000 ]; then
    echo "  Already processed ($ROWS rows) — skipping"
    continue
  fi

  # Download locally
  LOCAL_FILE="$LOCAL_TMP/${GAME_ID}.mp4"
  if [ ! -f "$LOCAL_FILE" ] || [ $(stat -c%s "$LOCAL_FILE" 2>/dev/null || echo 0) -lt 10000000 ]; then
    echo "  Downloading from YouTube..."
    yt-dlp -f 'best[height<=720]/best' "https://www.youtube.com/watch?v=$YT_ID" -o "$LOCAL_FILE" --no-part 2>&1 | tail -3
    if [ ! -f "$LOCAL_FILE" ]; then
      echo "  DOWNLOAD FAILED — skipping"
      continue
    fi
  fi
  SIZE=$(du -h "$LOCAL_FILE" | cut -f1)
  echo "  Downloaded: $SIZE"

  # Upload to pod
  echo "  Uploading to RunPod..."
  ssh -o StrictHostKeyChecking=no -p $RPORT $REMOTE "mkdir -p $REMOTE_DIR/data/videos/full_games"
  scp -P $RPORT "$LOCAL_FILE" "$REMOTE:$REMOTE_DIR/data/videos/full_games/${GAME_ID}.mp4"
  echo "  Uploaded"

  # Run pipeline on pod
  echo "  Running pipeline on RTX 4090..."
  ssh -o StrictHostKeyChecking=no -p $RPORT $REMOTE "cd $REMOTE_DIR && $PYTHON scripts/run_phase_g.py --game-id $GAME_ID --video data/videos/full_games/${GAME_ID}.mp4 --frames 18000 --no-show 2>&1 | tail -5"

  # Check result
  ROWS=$(ssh -o StrictHostKeyChecking=no -p $RPORT $REMOTE "wc -l < $REMOTE_DIR/data/tracking/$GAME_ID/tracking_data.csv 2>/dev/null || echo 0")
  echo "  Result: $ROWS rows"

  # Cleanup video on both sides
  ssh -o StrictHostKeyChecking=no -p $RPORT $REMOTE "rm -f $REMOTE_DIR/data/videos/full_games/${GAME_ID}.mp4"
  rm -f "$LOCAL_FILE"

  # Pull data back
  echo "  Syncing tracking data to local..."
  mkdir -p "data/tracking/$GAME_ID"
  scp -r -P $RPORT "$REMOTE:$REMOTE_DIR/data/tracking/$GAME_ID/" "data/tracking/$GAME_ID/"

  PROCESSED=$((PROCESSED + 1))
  echo "  Done ($PROCESSED/$LIMIT)"
done

echo ""
echo "=== Complete: $PROCESSED games processed ==="
