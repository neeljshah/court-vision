#!/usr/bin/env bash
# vps_setup.sh — Provision a fresh Hetzner CX11 for CourtVision daily runs.
#
# Usage:
#   bash scripts/vps_setup.sh [--dry-run]
#
# --dry-run: print commands without executing (for local testing)
#
# Requirements: Ubuntu 22.04 LTS, 2GB RAM, git, curl pre-installed.

set -euo pipefail

DRY_RUN=false
for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && DRY_RUN=true
done

_run() {
  if $DRY_RUN; then
    echo "[dry-run] $*"
  else
    eval "$*"
  fi
}

REPO_DIR="${HOME}/nba-ai-system"
CONDA_DIR="${HOME}/miniconda3"
LOG_DIR="${HOME}/logs"
CRON_TIME="0 13 * * *"  # 9 AM ET = 13:00 UTC

echo "[vps_setup] Starting CourtVision VPS provisioning..."

# 1. Install Miniconda if not present
if [[ ! -d "$CONDA_DIR" ]]; then
  _run "curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh"
  _run "bash /tmp/miniconda.sh -b -p ${CONDA_DIR}"
  _run "rm /tmp/miniconda.sh"
  _run "${CONDA_DIR}/bin/conda init bash"
fi

# 2. Clone or pull repo
if [[ ! -d "$REPO_DIR" ]]; then
  _run "git clone https://github.com/neeljshah/court-vision.git ${REPO_DIR}"
else
  _run "git -C ${REPO_DIR} pull --ff-only"
fi

# 3. Create conda environment
_run "${CONDA_DIR}/bin/conda env create -f ${REPO_DIR}/environment.yml --name basketball_ai -q 2>/dev/null || \
      ${CONDA_DIR}/bin/conda env update -f ${REPO_DIR}/environment.yml --name basketball_ai -q"

# 4. Create log directory
_run "mkdir -p ${LOG_DIR}"

# 5. Wire cron: daily_run.sh at CRON_TIME UTC
CRON_CMD="${CRON_TIME} ${CONDA_DIR}/bin/conda run -n basketball_ai bash ${REPO_DIR}/scripts/daily_run.sh >> ${LOG_DIR}/daily_run.log 2>&1"
if ! $DRY_RUN; then
  (crontab -l 2>/dev/null | grep -v "daily_run.sh"; echo "$CRON_CMD") | crontab -
  echo "[vps_setup] Cron entry installed."
else
  echo "[dry-run] crontab entry: $CRON_CMD"
fi

# 6. Smoke test: verify daily_run.sh help available
_run "${CONDA_DIR}/bin/conda run -n basketball_ai python ${REPO_DIR}/scripts/run_daily_slate.py --help >/dev/null 2>&1 && echo '[vps_setup] run_daily_slate.py help: OK' || echo '[vps_setup] WARN: run_daily_slate.py not functional yet'"

echo "[vps_setup] Provisioning complete."
