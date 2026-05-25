#!/usr/bin/env bash
# operator_morning.sh — pre-game sequence. Usage: operator_morning.sh YYYY-MM-DD [--dry-run]
set -euo pipefail
DATE="${1:-}"
DRY="${2:-}"
if [[ -z "$DATE" ]]; then echo "usage: $0 YYYY-MM-DD [--dry-run]" >&2; exit 2; fi
run() { if [[ "$DRY" == "--dry-run" ]]; then echo "DRY: $*"; else "$@"; fi; }
run python scripts/predict_slate.py --date "$DATE"
run python scripts/update_inactives.py --date "$DATE"
run nohup python scripts/fetch_live_prop_lines.py --interval-min 10 &
run python scripts/compare_to_lines.py --date "$DATE" --book DK
