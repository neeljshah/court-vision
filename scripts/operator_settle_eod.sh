#!/usr/bin/env bash
# operator_settle_eod.sh — end-of-day settle + reports. Usage: operator_settle_eod.sh YYYY-MM-DD [--dry-run]
set -euo pipefail
DATE="${1:-}"
DRY="${2:-}"
if [[ -z "$DATE" ]]; then echo "usage: $0 YYYY-MM-DD [--dry-run]" >&2; exit 2; fi
run() { if [[ "$DRY" == "--dry-run" ]]; then echo "DRY: $*"; else "$@"; fi; }
run pkill -f live_inplay_daemon || true
run pkill -f fetch_live_prop_lines || true
run python scripts/settle_bet.py --auto --date "$DATE"
run python scripts/pnl_report.py --range 7d --by strategy
run python scripts/clv_report.py --range 7d --by stat
