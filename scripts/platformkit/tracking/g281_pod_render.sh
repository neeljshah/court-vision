#!/usr/bin/env bash
# Pod-only G281 crop rendering. Local pair construction and all arithmetic are separate.
set -euo pipefail
ART="docs/evidence/tracking/g281_identity_purity_one_second_artifact"
VIDEO="/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
PROBE="/workspace/wt/a6/g281_fsync_probe"
mkdir -p "$ART"
python3 - <<'PY' | tee "$ART/pod_occupancy.txt"
import os
excluded = {os.getpid(), os.getppid()}
lanes = {}
for name in os.listdir('/proc'):
    if not name.isdigit() or int(name) in excluded:
        continue
    try:
        cwd = os.readlink('/proc/%s/cwd' % name)
        args = open('/proc/%s/cmdline' % name, 'rb').read().replace(b'\0', b' ').decode('ascii', 'replace').strip()
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        continue
    if not args.startswith(('python ', 'python3 ', '/usr/bin/python', '/opt/conda')) or not cwd.startswith('/workspace/wt/a'):
        continue
    lane = '/'.join(cwd.split('/')[:4]); lanes.setdefault(lane, []).append((name, args))
print('G281_OBSERVED_PYTHON_WORKTREES=' + ','.join(sorted(lanes)))
for lane in sorted(lanes):
    for pid, args in lanes[lane]: print('G281_OCCUPANT lane=%s pid=%s args=%s' % (lane, pid, args))
peers = sorted(set(lanes) - {'/workspace/wt/a6'})
print('G281_PEER_WORKTREES=' + ','.join(peers)); print('G281_PEER_WORKTREE_COUNT=%d' % len(peers))
if len(peers) >= 2: raise SystemExit('G281_HOLD_DISTINCT_WORKTREES_AT_LIMIT')
PY
nvidia-smi --query-gpu=utilization.gpu,utilization.memory,memory.used,memory.total --format=csv,noheader | tee -a "$ART/pod_occupancy.txt"
du -sm /workspace | tee "$ART/pod_disk_guard.txt"
if ! dd if=/dev/zero of="$PROBE" bs=1M count=8 conv=fsync status=none; then echo 'G281_FSYNC_PROBE=FAILED' | tee -a "$ART/pod_disk_guard.txt"; exit 3; fi
rm -f "$PROBE"; echo 'G281_FSYNC_PROBE=PASSED_AND_REMOVED_BYTES=8388608' | tee -a "$ART/pod_disk_guard.txt"
sha256sum scripts/platformkit/tracking/g281_identity_purity_one_second.py scripts/platformkit/tracking/g281_pod_render.sh | tee "$ART/pod_route_sha256.txt"
python3 scripts/platformkit/tracking/g281_identity_purity_one_second.py render --video "$VIDEO" --output "$ART"
find "$ART/blind_renders" -type f -printf '%s\n' | awk '{sum+=$1} END {print "G281_CROP_BYTES=" sum}' | tee -a "$ART/pod_disk_guard.txt"
