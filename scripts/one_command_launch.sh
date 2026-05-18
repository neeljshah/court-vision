#!/bin/bash
# one_command_launch.sh — When user is back: one command does everything.
#
# Usage:
#   bash scripts/one_command_launch.sh <POD_IP> <POD_PORT>
#
# Does:
#   1. Bootstraps pod (pushes code, installs deps, stages videos)
#   2. Launches Phase G with 4 parallel workers, OMP cap, VRAM check
#   3. Starts local rsync watchdog (pulls tracking data every 15 min)
#   4. Starts budget watchdog (auto-stops pod at $14 spent or 80 CLEAN reached)
#   5. Tails the worker log

set -euo pipefail

IP="${1:?Usage: bash scripts/one_command_launch.sh <IP> <PORT>}"
PORT="${2:?Usage: bash scripts/one_command_launch.sh <IP> <PORT>}"

cd "$(dirname "$0")/.."

echo "=== Step 1: Bootstrap pod and launch ==="
bash scripts/bootstrap_pod.sh "$IP" "$PORT"

echo ""
echo "=== Step 2: Start local sync watchdog (rsync every 15 min) ==="
nohup bash scripts/local_sync_watchdog.sh "$IP" "$PORT" > logs/sync_watchdog.log 2>&1 &
echo "Sync watchdog PID: $!"
echo "$!" > .sync_watchdog.pid

echo ""
echo "=== Step 3: Start budget watchdog (auto-stop at $14 or 80 CLEAN) ==="
nohup bash scripts/budget_watchdog.sh "$IP" "$PORT" > logs/budget_watchdog.log 2>&1 &
echo "Budget watchdog PID: $!"
echo "$!" > .budget_watchdog.pid

echo ""
echo "=== Step 4: Tailing remote worker log ==="
echo "(Ctrl-C to stop tailing — watchdogs keep running)"
ssh -F ~/.ssh/config.pod -o ConnectTimeout=10 -p "$PORT" "root@$IP" \
    "tail -f /workspace/nba-ai-system/phase_g_batch.log"
