#!/usr/bin/env bash
# G280 hold observation: count distinct lane CWDs, never Python PIDs.
set -euo pipefail
declare -A lane_args=()
lane_count=0
for proc in /proc/[0-9]*; do
  pid="${proc#/proc/}"
  cwd="$(readlink "$proc/cwd" 2>/dev/null || true)"
  case "$cwd" in
    /workspace/wt/a[0-9]*) ;;
    *) continue ;;
  esac
  [ "$cwd" = "/workspace/wt/a5" ] && continue
  args="$(tr '\0' ' ' < "$proc/cmdline" 2>/dev/null || true)"
  [ -n "$args" ] || args="$(readlink "$proc/exe" 2>/dev/null || true)"
  if [ -z "${lane_args[$cwd]+present}" ]; then
    lane_count=$((lane_count + 1))
  fi
  lane_args["$cwd"]+="pid=$pid args=$args | "
done
printf 'G280_GPU='
nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader
printf 'G280_OCCUPANCY_COUNT=%d\n' "$lane_count"
for lane in "${!lane_args[@]}"; do
  printf 'G280_LANE cwd=%s %s\n' "$lane" "${lane_args[$lane]}"
done
[ "$lane_count" -lt 2 ] || exit 75
