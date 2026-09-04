#!/usr/bin/env bash
# Pod-only render phase for G276b.  The selection and all arithmetic are local.
set -euo pipefail

ART="docs/evidence/tracking/g276b_unconditioned_step_endpoint_baseline_artifact"
VIDEO="/workspace/nba-ai-system/data/footage_corpus/wnba__wnba_01.mp4"
PROBE="/workspace/wt/a5/g276b_fsync_probe"

python3 - <<'PY'
import os

excluded = {os.getpid(), os.getppid()}
observed_lanes = set()
for name in os.listdir("/proc"):
    if not name.isdigit():
        continue
    pid = int(name)
    if pid in excluded:
        continue
    try:
        with open("/proc/%s/cmdline" % pid, "rb") as handle:
            command = handle.read().replace(b"\0", b" ").decode("ascii", "ignore").lower()
        cwd = os.readlink("/proc/%s/cwd" % pid)
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        continue
    if "python" not in command or not cwd.startswith("/workspace/wt/a"):
        continue
    lane = cwd.split("/", 4)[:4]
    observed_lanes.add("/".join(lane))
# a5 is this row's own scratch tree; a one-row/one-lane rule means no foreign lane
# may legitimately use it.  Excluding its processes implements the hold rule's own
# process/checker/parent exclusion before counting distinct peer worktrees.
peer_lanes = observed_lanes - {"/workspace/wt/a5"}
print("G276B_OBSERVED_PYTHON_WORKTREES=" + ",".join(sorted(observed_lanes)))
print("G276B_PEER_PYTHON_WORKTREES=" + ",".join(sorted(peer_lanes)))
print("G276B_PEER_WORKTREE_COUNT=" + str(len(peer_lanes)))
if len(peer_lanes) >= 2:
    raise SystemExit("G276B_HOLD_DISTINCT_WORKTREES_AT_LIMIT")
PY

du -sm /workspace | tee "$ART/pod_disk_guard.txt"
if ! dd if=/dev/zero of="$PROBE" bs=1M count=8 conv=fsync status=none; then
    echo "G276B_FSYNC_PROBE=FAILED" | tee -a "$ART/pod_disk_guard.txt"
    exit 3
fi
rm -f "$PROBE"
echo "G276B_FSYNC_PROBE=PASSED_AND_REMOVED_BYTES=8388608" | tee -a "$ART/pod_disk_guard.txt"
sha256sum scripts/platformkit/tracking/g276b_unconditioned_step_endpoint_baseline.py | tee "$ART/pod_route_sha256.txt"
python3 scripts/platformkit/tracking/g276b_unconditioned_step_endpoint_baseline.py render --video "$VIDEO" --output "$ART"
find "$ART/blind_renders" -type f -printf '%s\n' | awk '{s+=$1} END {print "G276B_CROP_BYTES=" s}' | tee -a "$ART/pod_disk_guard.txt"
tar -cf "$ART/pod_blind_renders.tar" "$ART/blind_renders"
