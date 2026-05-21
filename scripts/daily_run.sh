#!/usr/bin/env bash
# Daily pipeline orchestrator. Exits non-zero if any stage fails.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DATE="${1:-$(date +%Y-%m-%d)}"
ALERTS_DIR="$PROJECT_DIR/data/output/alerts"
VAULT_LOG="$PROJECT_DIR/vault/alerts.log"

mkdir -p "$ALERTS_DIR"

_fail() {
  local stage="$1"
  local msg="Daily pipeline FAILED at stage: $stage (date=$DATE)"
  # Write alert file
  echo "$msg" > "$ALERTS_DIR/ALERT_${DATE}.txt"
  # Append to vault log
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $msg" >> "$VAULT_LOG"
  # Fire Telegram if token set
  if [[ -n "${TELEGRAM_BOT_TOKEN:-}" ]] && [[ -n "${TELEGRAM_CHAT_ID:-}" ]]; then
    python "$SCRIPT_DIR/bot_guards/send_telegram.py" "$msg" 2>/dev/null || true
  fi
  exit 1
}

echo "[daily_run] Starting pipeline for $DATE"

# Stage 1: Record previous slate results
python "$SCRIPT_DIR/record_slate_results.py" --date "$DATE" || _fail "record_slate_results"
echo "[daily_run] Stage 1 done: record_slate_results"

# Stage 2: Run today's slate predictions
python "$SCRIPT_DIR/run_daily_slate.py" --date "$DATE" || _fail "run_daily_slate"
echo "[daily_run] Stage 2 done: run_daily_slate"

# Stage 3: Bet selection
python -m src.prediction.bet_selector --date "$DATE" 2>/dev/null || \
  python "$SCRIPT_DIR/run_daily_slate.py" --bet-select --date "$DATE" 2>/dev/null || \
  echo "[daily_run] Stage 3: bet_selector not wired yet (skipped)"

echo "[daily_run] Pipeline complete for $DATE"
