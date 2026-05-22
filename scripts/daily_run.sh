#!/usr/bin/env bash
# Daily pipeline orchestrator. Exits non-zero if any stage fails.
set -euo pipefail

# Paper mode only — NEVER enable live betting from this script
export LIVE_BETTING=0

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

echo "[daily_run] Starting pipeline for $DATE (LIVE_BETTING=$LIVE_BETTING)"

# Stage 1/4: Record previous slate results (T+1 settlement)
echo "[daily_run] stage 1/4: record_slate_results"
python "$SCRIPT_DIR/record_slate_results.py" --date "$DATE" || _fail "record_slate_results"
echo "[daily_run] stage 1/4 done: record_slate_results"

# Stage 2/4: Run today's slate predictions
echo "[daily_run] stage 2/4: run_daily_slate"
python "$SCRIPT_DIR/run_daily_slate.py" --date "$DATE" || _fail "run_daily_slate"
echo "[daily_run] stage 2/4 done: run_daily_slate"

# Log today's prop lines into the history store — builds the market-line
# training dataset over the season. Non-fatal: never blocks the pipeline.
echo "[daily_run] logging prop lines"
python "$SCRIPT_DIR/log_prop_lines.py" --date "$DATE" || \
  echo "[daily_run] log_prop_lines skipped or errored (non-fatal)"

# Stage 3/4: Bet selection
echo "[daily_run] stage 3/4: bet_selector"
python -m src.prediction.bet_selector --date "$DATE" || _fail "bet_selector"
echo "[daily_run] stage 3/4 done: bet_selector"

# Stage 4/4: Auto-retrain stale prop models (14-day gate)
echo "[daily_run] stage 4/4: auto_retrain"
python "$SCRIPT_DIR/auto_retrain.py" || \
  echo "[daily_run] stage 4/4: auto_retrain skipped or errored (non-fatal)"
echo "[daily_run] stage 4/4 done: auto_retrain"

echo "[daily_run] Pipeline complete for $DATE"
