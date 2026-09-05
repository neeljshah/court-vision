#!/usr/bin/env bash
set -euo pipefail
cd /c/Users/neelj/nba-track-a6
OUT=docs/evidence/tracking/g298_detector_capacity_and_input_resolution_artifact
mkdir -p "$OUT"
ssh -F "$HOME/.ssh/config.pod" pod 'mkdir -p /workspace/wt/a6/g298_scratch; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader; dd if=/dev/zero of=/workspace/wt/a6/g298_scratch/preflight_fsync_probe.bin bs=1M count=8 conv=fsync' 2>&1 | tee "$OUT/preflight.log"
FETCH=()
for arm in A A_repeat B C; do
  FETCH+=(--fetch "$OUT/$arm.csv" --fetch "$OUT/${arm}_summary.json")
done
for name in probes.json determinism.json scratch_bytes.json; do
  FETCH+=(--fetch "$OUT/$name")
done
SHIP=()
for name in scripts/__init__.py scripts/platformkit/__init__.py scripts/platformkit/tracking/__init__.py scripts/platformkit/tracking/association.py scripts/platformkit/tracking/g298_detect.py scripts/platformkit/tracking/g298_compare.py src/__init__.py src/tracking/__init__.py src/tracking/player_detection.py src/tracking/utils/__init__.py src/tracking/utils/plot_tools.py docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv; do
  if [ -f "$name" ]; then SHIP+=(--ship "$name"); fi
done
bash scripts/platformkit/tracking/g298_pod_run_minimal.sh a6 "${SHIP[@]}" "${FETCH[@]}" -- "PYTHONPATH=/workspace/wt/a6/g298_code:/workspace/wt/_pylib PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=298 YOLO_CONFIG_DIR=/workspace/wt/a6/g298_scratch MPLCONFIGDIR=/workspace/wt/a6/g298_scratch/matplotlib python /workspace/wt/a6/g298_code/scripts/platformkit/tracking/g298_detect.py --video /workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4 --located-feet /workspace/wt/a6/g298_code/docs/evidence/tracking/g285b_locate_then_match_recall_artifact/located_feet.csv --output /workspace/wt/a6/$OUT" 2>&1 | tee "$OUT/pod_run_minimal.log"
