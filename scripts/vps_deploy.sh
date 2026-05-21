#!/usr/bin/env bash
# vps_deploy.sh — Pull latest code and restart cron on the VPS.
set -euo pipefail

REPO_DIR="${HOME}/nba-ai-system"
CONDA_DIR="${HOME}/miniconda3"

echo "[vps_deploy] Deploying latest CourtVision code..."
git -C "${REPO_DIR}" pull --ff-only
"${CONDA_DIR}/bin/conda" env update -f "${REPO_DIR}/environment.yml" --name basketball_ai -q
echo "[vps_deploy] Deploy complete. Cron will pick up new code on next run."
