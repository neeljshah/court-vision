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
)
POD_ROOT = "/workspace/nba-ai-system"
DEFAULT_HOST = "213.192.2.83"
DEFAULT_PORT = "40193"
_POD_LINE = re.compile(r"^([0-9a-fA-F]{32})\s+/workspace/nba-ai-system/(.+)$")


def _is_scoped_module(path: str) -> bool:
    """Return whether a repository-relative path is a production scope member."""
    if not path.endswith(".py") or Path(path).name.startswith("test_"):
        return False
    parts = path.split("/")
    return (
        len(parts) == 4 and parts[0] == "domains" and parts[2] == "tracking"
    ) or (
        len(parts) == 4 and parts[:3] == ["scripts", "platformkit", "tracking"]
    ) or (
        len(parts) == 3
        and parts[:2] == ["scripts", "platformkit"]
        and (parts[2].startswith("track_daemon") or parts[2] == "tracking_harness.py")
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
        "\\( -name 'track_daemon*.py' -o -name 'tracking_harness.py' \\) "
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
