#!/bin/bash
# ingest_preflight.sh — Validate pod environment before 7-9 hr ingest run.
# Exit 0 = all checks pass. Exit 1 = at least one FAIL.
set -uo pipefail

PROJ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJ"

PASS=0
FAIL=0
WARN=0

_ok()   { echo "  [PASS] $1"; PASS=$((PASS+1)); }
_fail() { echo "  [FAIL] $1"; echo "         Fix: $2"; FAIL=$((FAIL+1)); }
_warn() { echo "  [WARN] $1"; WARN=$((WARN+1)); }

echo "=== ingest_preflight.sh ==="
echo ""

# ── 1. Python 3.9+ ──────────────────────────────────────────────────────────
PY_VER=$(python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>/dev/null || echo "0.0")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 9 ]; then
  _ok "Python $PY_VER"
else
  _fail "Python $PY_VER < 3.9" "conda activate basketball_ai"
fi

# ── 2. ffprobe ───────────────────────────────────────────────────────────────
if command -v ffprobe >/dev/null 2>&1; then
  _ok "ffprobe found: $(ffprobe -version 2>&1 | head -1)"
else
  _fail "ffprobe not found" "conda install -c conda-forge ffmpeg  OR  apt install ffmpeg"
fi

# ── 3. yt-dlp ────────────────────────────────────────────────────────────────
if command -v yt-dlp >/dev/null 2>&1; then
  _ok "yt-dlp found: $(yt-dlp --version 2>/dev/null)"
else
  _fail "yt-dlp not found" "pip install yt-dlp"
fi

# ── 4. decord (NVDEC GPU decode) ─────────────────────────────────────────────
if python -c "import decord" 2>/dev/null; then
  _ok "decord importable"
else
  _fail "decord not installed — CPU decode will bottleneck workers" "pip install decord"
fi

# ── 5. torch.cuda available ──────────────────────────────────────────────────
CUDA_INFO=$(python -c "
import torch
avail = torch.cuda.is_available()
count = torch.cuda.device_count() if avail else 0
name  = torch.cuda.get_device_name(0) if avail and count > 0 else 'n/a'
print(f'{avail},{count},{name}')
" 2>/dev/null || echo "false,0,error")
CUDA_AVAIL=$(echo "$CUDA_INFO" | cut -d, -f1)
CUDA_COUNT=$(echo "$CUDA_INFO" | cut -d, -f2)
CUDA_NAME=$(echo "$CUDA_INFO" | cut -d, -f3-)
if [ "$CUDA_AVAIL" = "True" ] && [ "$CUDA_COUNT" -ge 1 ]; then
  _ok "CUDA available: $CUDA_COUNT GPU(s) — $CUDA_NAME"
else
  _fail "CUDA not available (is_available=$CUDA_AVAIL, count=$CUDA_COUNT)" \
        "Ensure CUDA drivers installed and NVIDIA GPU present"
fi

# ── 6. _VRAM_FLUSH_INTERVAL = 3000 ───────────────────────────────────────────
FLUSH=$(grep -oE '_VRAM_FLUSH_INTERVAL\s*=\s*[0-9]+' src/pipeline/unified_pipeline.py 2>/dev/null | head -1)
if echo "$FLUSH" | grep -q "3000"; then
  _ok "_VRAM_FLUSH_INTERVAL = 3000"
else
  _fail "_VRAM_FLUSH_INTERVAL != 3000 (found: '$FLUSH')" \
        "Edit src/pipeline/unified_pipeline.py: set _VRAM_FLUSH_INTERVAL = 3000"
fi

# ── 7. data/videos/full_games symlink resolves ───────────────────────────────
if ls data/videos/full_games/ >/dev/null 2>&1; then
  TARGET=$(readlink data/videos/full_games 2>/dev/null || echo "(not a symlink)")
  _ok "data/videos/full_games resolves → $TARGET"
else
  _fail "data/videos/full_games does not resolve" \
        "mkdir -p /root/nba_videos && ln -sfn /root/nba_videos data/videos/full_games"
fi

# ── 8. cgroup CPU quota ───────────────────────────────────────────────────────
QUOTA=""
if [ -f /sys/fs/cgroup/cpu.max ]; then
  QUOTA=$(cat /sys/fs/cgroup/cpu.max 2>/dev/null)
  _ok "cgroup v2 cpu.max: $QUOTA"
elif [ -f /sys/fs/cgroup/cpu,cpuacct/cpu.cfs_quota_us ]; then
  QUOTA=$(cat /sys/fs/cgroup/cpu,cpuacct/cpu.cfs_quota_us 2>/dev/null)
  _ok "cgroup v1 cpu.cfs_quota_us: $QUOTA"
else
  _warn "cgroup quota file not found (may be bare-metal or WSL)"
fi

# ── 9. Free RAM > 80 GB ───────────────────────────────────────────────────────
FREE_KB=$(grep MemAvailable /proc/meminfo 2>/dev/null | awk '{print $2}' || echo "0")
FREE_GB=$((FREE_KB / 1024 / 1024))
if [ "$FREE_KB" -eq 0 ]; then
  _warn "/proc/meminfo not available (non-Linux?)"
elif [ "$FREE_GB" -ge 80 ]; then
  _ok "Free RAM: ${FREE_GB} GB"
else
  _warn "Free RAM ${FREE_GB} GB < 80 GB — check for leaks or pre-loaded models"
fi

# ── 10. B2 credentials (warning only — sync is optional) ─────────────────────
if [ -f ".env" ] && grep -q "B2_BUCKET=" .env && ! grep -q "^B2_BUCKET=$" .env; then
  _ok "B2_BUCKET set in .env"
else
  _warn "B2_BUCKET not set in .env — cloud sync will be skipped"
fi

# ── 11. SQLite queue exists and has rows ─────────────────────────────────────
QUEUE_STATUS=$(python -m src.ingest.manifest status 2>&1 | tail -3)
if python -c "
from src.ingest.db import connect, migrate
conn = connect()
migrate(conn)
n = conn.execute(\"SELECT COUNT(*) FROM games\").fetchone()[0]
conn.close()
assert n > 0, f'queue is empty ({n} rows)'
" 2>/dev/null; then
  _ok "SQLite queue has rows"
  echo "         $QUEUE_STATUS"
else
  _fail "SQLite queue is empty or missing" \
        "python -m src.ingest.manifest migrate  OR  python scripts/ingest_fetch.py --count N"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=== Preflight summary: $PASS passed, $WARN warnings, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "Fix the FAIL items above before launching the pod run."
  exit 1
fi
echo "All checks passed. Ready to launch."
exit 0
