"""Read-only comparison of tracking-number producer modules on pod and master."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Mapping, Sequence


SCOPE_GLOBS = (
    "domains/*/tracking/*.py",
    "scripts/platformkit/tracking/*.py",
    "scripts/platformkit/track_daemon*.py",
    "scripts/platformkit/tracking_harness.py",
    # The harness dependencies below. Kept in step with HARNESS_DEPENDENCIES and
    # with pod_command() by test_pod_drift_scope.py -- the scope used to live in
    # three places and only one of them ever got updated.
    "scripts/platformkit/metric_local_profile.py",
    "scripts/platformkit/tracking_schema.py",
    "scripts/platformkit/coordinate_provenance.py",
    "scripts/platformkit/liveness_metrics.py",
)
# Local-only tooling that never runs on the pod. It is in the scope globs by
# path but is not a tracking-number producer, so leaving it in reports a
# permanent DIFFERS and trains the reader to ignore the check. Anything added
# here needs the same justification: it cannot affect a pod-produced number.
LOCAL_ONLY_MODULES = frozenset((
    "scripts/platformkit/tracking/worktree_data_links.py",  # Windows junctions
    "scripts/platformkit/tracking/pod_drift.py",            # the checker itself
))
POD_ROOT = "/workspace/nba-ai-system"
DEFAULT_HOST = "213.192.2.83"
DEFAULT_PORT = "40193"
_POD_LINE = re.compile(r"^([0-9a-fA-F]{32})\s+/workspace/nba-ai-system/(.+)$")


# tracking_harness.py is in scope, but until 2026-09-02 its DEPENDENCIES were not,
# and every one of them changes tracking numbers: metric_local_profile builds
# report fields, tracking_schema and coordinate_provenance define the coordinate
# contract, liveness_metrics computes a gated verdict. That blind spot broke the
# pod twice in one day -- once deploying the harness without these (ImportError),
# once rolling the harness back without metric_local_profile, which then passed a
# field the older QualityReport would not accept (TypeError on three tables).
# A drift checker that cannot see a module feeding the thing it checks is the
# same class of silent gap as the SSH port that drifted unnoticed for a day.
# test_pod_drift_scope.py fails if the harness gains an import that is not here.
HARNESS_DEPENDENCIES = frozenset((
    "metric_local_profile.py",
    "tracking_schema.py",
    "coordinate_provenance.py",
    "liveness_metrics.py",
))


def _is_scoped_module(path: str) -> bool:
    """Return whether a repository-relative path is a production scope member."""
    if not path.endswith(".py") or Path(path).name.startswith("test_"):
        return False
    if path in LOCAL_ONLY_MODULES:
        return False
    parts = path.split("/")
    return (
        len(parts) == 4 and parts[0] == "domains" and parts[2] == "tracking"
    ) or (
        len(parts) == 4 and parts[:3] == ["scripts", "platformkit", "tracking"]
    ) or (
        len(parts) == 3
        and parts[:2] == ["scripts", "platformkit"]
        and (parts[2].startswith("track_daemon")
             or parts[2] == "tracking_harness.py"
             or parts[2] in HARNESS_DEPENDENCIES)
    )


def master_hashes(repo: Path) -> dict[str, str]:
    """Hash the current master worktree's Git-tracked producer modules."""
    command = ["git", "-C", str(repo), "ls-files", "--", *SCOPE_GLOBS]
    listed = subprocess.run(command, text=True, capture_output=True, check=True)
    hashes: dict[str, str] = {}
    for relative in listed.stdout.splitlines():
        if _is_scoped_module(relative):
            hashes[relative] = hashlib.md5(
                (repo / relative).read_bytes(), usedforsecurity=False
            ).hexdigest()
    return hashes


def pod_command() -> str:
    """Return the pod command; it uses only find and md5sum, never Git."""
    return (
        "find /workspace/nba-ai-system/domains -path '*/tracking/*.py' -type f "
        "-exec md5sum {} \\; 2>/dev/null; "
        "find /workspace/nba-ai-system/scripts/platformkit/tracking -maxdepth 1 "
        "-type f -name '*.py' -exec md5sum {} \\; 2>/dev/null; "
        "find /workspace/nba-ai-system/scripts/platformkit -maxdepth 1 -type f "
        "\( -name 'track_daemon*.py' -o -name 'tracking_harness.py'" + "".join(" -o -name '%s'" % n for n in sorted(HARNESS_DEPENDENCIES)) + " \) "
        "-exec md5sum {} \\; 2>/dev/null"
    )


def pod_hashes(output: str) -> dict[str, str]:
    """Parse the pod's MD5 listing into repository-relative paths."""
    hashes: dict[str, str] = {}
    for line in output.splitlines():
        match = _POD_LINE.fullmatch(line)
        if not match:
            raise ValueError("unexpected pod MD5 output")
        relative = match.group(2)
        if _is_scoped_module(relative):
            hashes[relative] = match.group(1).lower()
    return hashes


def named_sets(
    master: Mapping[str, str], pod: Mapping[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """Return sorted DIFFERS, POD-ONLY, and MASTER-ONLY path sets."""
    differs = sorted(path for path in master if path in pod and master[path] != pod[path])
    pod_only = sorted(path for path in pod if path not in master)
    master_only = sorted(path for path in master if path not in pod)
    return differs, pod_only, master_only


def _print_set(name: str, paths: Sequence[str], emit: Callable[[str], None]) -> None:
    emit(f"  {name} ({len(paths)})")
    for path in paths:
        emit(f"    {path}")
    if not paths:
        emit("    (none)")


def run_drift_check(
    repo: Path,
    host: str,
    port: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    emit: Callable[[str], None] = print,
) -> int:
    """Print the three drift sets, or UNKNOWN when the read-only pod query fails."""
    try:
        master = master_hashes(repo)
        result = runner(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=15",
                "-p",
                port,
                f"root@{host}",
                pod_command(),
            ],
            text=True,
            capture_output=True,
            timeout=20,
            check=True,
        )
        pod = pod_hashes(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        emit("UNKNOWN: pod drift check unavailable")
        return 0

    differs, pod_only, master_only = named_sets(master, pod)
    emit("== pod drift (tracking-number producer modules)")
    _print_set("DIFFERS", differs, emit)
    _print_set("POD-ONLY", pod_only, emit)
    _print_set("MASTER-ONLY", master_only, emit)
    return 0


def main() -> int:
    """Run the check from loop_status.sh or directly for verification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--host", default=os.environ.get("POD_HOST", DEFAULT_HOST))
    parser.add_argument("--port", default=os.environ.get("POD_PORT", DEFAULT_PORT))
    args = parser.parse_args()
    return run_drift_check(args.repo, args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
