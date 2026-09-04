#!/usr/bin/env bash
# G280 blind packet: map stays on pod until verdict commit precedes unblinding.
set -euo pipefail
artifact=docs/evidence/tracking/g280_amateur_footage_trackability_artifact
python -m scripts.platformkit.tracking.g280_amateur_footage_trackability preflight \
  --video /workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4 \
  --tracking-root /workspace/nba-ai-system/data/tracking \
  --output "$artifact/g280_pod_preflight.json"
python -m scripts.platformkit.tracking.g280_amateur_blind_precision prepare \
  --input "$artifact/run_1/tracking_data.csv" \
  --video /workspace/nba-ai-system/data/footage_corpus/basketball__amateur_jh3fnwMi7dM.mp4 \
  --output "$artifact/blind_packet"
tar -C "$artifact/blind_packet" -czf "$artifact/blind_packet_sealed.tar.gz" \
  blind_order_commitment.json blind_presentation_order.csv blind_verdicts.csv blind_renders
