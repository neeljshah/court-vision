#!/usr/bin/env bash
# G280: guarded, unchanged production-route draws in pod scratch only.
set -euo pipefail
video=/workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4
store=/workspace/nba-ai-system/data/tracking
artifact=docs/evidence/tracking/g280_amateur_footage_trackability_artifact
module=scripts.platformkit.tracking.g280_amateur_footage_trackability
python -m "$module" preflight --video "$video" --tracking-root "$store" --output "$artifact/g280_pod_preflight.json"
for run in 1 2 3; do
  python -m "$module" run --video "$video" --output "$artifact/run_$run/tracking_data.csv" --root .
done
python -m "$module" analyze --inputs "$artifact/run_1/tracking_data.csv" "$artifact/run_2/tracking_data.csv" "$artifact/run_3/tracking_data.csv" --output "$artifact/g280_per_run_summary.json"
