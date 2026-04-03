#!/bin/bash
# reprocess_safe.sh — Process games one-at-a-time (memory safe)
# Each game runs in a fresh Python process that exits cleanly

conda activate basketball_ai

GAMES=(
  "0022400430"
  "0022400537"
  "0022400909"
  "0022401123"
  "0022401183"
  "0022400625"
  "0022400687"
  "0022401185"
  "0022401190"
  "0022401196"
  "0022401198"
)

echo "=== SAFE REPROCESSING (1 game per process) ==="
echo "Each game runs in its own Python process"
echo "Memory freed after each game completes"
echo ""

for i in "${!GAMES[@]}"; do
  game=${GAMES[$i]}
  idx=$((i+1))
  total=${#GAMES[@]}

  echo "[$idx/$total] Processing $game..."

  # Run in separate process (guarantees memory cleanup)
  python scripts/run_phase_g.py --game-ids "$game" --frames 4500 --reprocess

  status=$?
  if [ $status -eq 0 ]; then
    echo "  ✓ SUCCESS"
  else
    echo "  ✗ FAILED (exit code $status)"
  fi

  echo ""
done

echo "=== COMPLETE ==="
