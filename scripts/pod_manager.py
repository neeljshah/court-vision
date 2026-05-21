#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/pod_manager.py - Autonomous RunPod GPU pod lifecycle manager.

Subcommands
-----------
launch    Provision a new pod via the RunPod API and wait until it is ready.
status    Print the current pod status (requires RUNPOD_IP or .runpod config).
sync      Pull completed tracking results from the pod to local data/tracking/.
teardown  Terminate the pod (after confirming data has been pulled).

Usage
-----
    python scripts/pod_manager.py launch [--gpu RTX_3090] [--workers 6]
    python scripts/pod_manager.py status
    python scripts/pod_manager.py sync [--dry-run]
    python scripts/pod_manager.py teardown [--force]
    python scripts/pod_manager.py --help

Environment / config
--------------------
Credentials are read from (in priority order):
  1. Environment variables: RUNPOD_API_KEY, RUNPOD_IP, RUNPOD_PORT
  2. .runpod file in the project root (KEY=VALUE shell syntax)

The .runpod file is gitignored and never committed.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

# Force UTF-8 stdout/stderr so print() works cross-platform with special chars.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RUNPOD_API_URL = "https://api.runpod.io/graphql"
DEFAULT_GPU = "NVIDIA GeForce RTX 3090"
DEFAULT_IMAGE = "runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04"
PROJ_PATH = "/workspace/nba-ai-system"
REMOTE_TRACKING_DIR = f"{PROJ_PATH}/data/tracking"
LOCAL_TRACKING_DIR = "data/tracking"
RUNPOD_CONFIG_FILE = ".runpod"

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _load_dotrunpod(root: Optional[Path] = None) -> Dict[str, str]:
    """Parse the .runpod KEY=VALUE config file if it exists."""
    if root is None:
        root = Path(__file__).parent.parent
    cfg_path = root / RUNPOD_CONFIG_FILE
    cfg: Dict[str, str] = {}
    if not cfg_path.exists():
        return cfg
    for line in cfg_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            cfg[key.strip()] = val.strip().strip('"').strip("'")
    return cfg


def _get_config() -> Dict[str, str]:
    """Merge .runpod file with environment variables (env takes precedence)."""
    cfg = _load_dotrunpod()
    for key in ("RUNPOD_API_KEY", "RUNPOD_IP", "RUNPOD_PORT", "RUNPOD_POD_ID"):
        if key in os.environ:
            cfg[key] = os.environ[key]
    return cfg


def _require_credentials(cfg: Dict[str, str], *keys: str) -> None:
    """Exit with a helpful error if any required credential is missing."""
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        print(
            "ERROR: missing credentials: {}. "
            "Set via environment variables or a .runpod file in the project root.".format(
                ", ".join(missing)
            ),
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# RunPod API helpers
# ---------------------------------------------------------------------------


def _gql_request(
    api_key: str, query: str, variables: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Execute a GraphQL request against the RunPod API.

    Parameters
    ----------
    api_key:
        RunPod API key (RUNPOD_API_KEY).
    query:
        GraphQL query/mutation string.
    variables:
        Optional variables dict.

    Returns
    -------
    dict
        Parsed JSON response body.

    Raises
    ------
    RuntimeError
        On non-200 HTTP responses or GraphQL errors.
    """
    try:
        import urllib.request

        payload = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = urllib.request.Request(
            RUNPOD_API_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer {}".format(api_key),
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
    except Exception as exc:
        raise RuntimeError("RunPod API request failed: {}".format(exc)) from exc

    if "errors" in body:
        raise RuntimeError("GraphQL errors: {}".format(body["errors"]))
    return body


def launch_pod(
    api_key: str,
    gpu_type: str = DEFAULT_GPU,
    workers: int = 6,
    image: str = DEFAULT_IMAGE,
) -> Dict[str, Any]:
    """Create a new RunPod GPU pod and return the pod info dict.

    Parameters
    ----------
    api_key:
        RunPod API key.
    gpu_type:
        GPU display name, e.g. ``"NVIDIA GeForce RTX 3090"``.
    workers:
        Number of parallel pipeline workers to use (stored in env var on pod).
    image:
        Docker image for the pod.

    Returns
    -------
    dict
        Pod info with at minimum ``id``, ``status`` keys.
    """
    mutation = """
    mutation PodCreate($input: PodFindAndDeployOnDemandInput!) {
      podFindAndDeployOnDemand(input: $input) {
        id
        imageName
        desiredStatus
        runtime {
          ports { ip privatePort publicPort type }
        }
      }
    }
    """
    variables: Dict[str, Any] = {
        "input": {
            "cloudType": "COMMUNITY",
            "gpuCount": 1,
            "gpuTypeId": gpu_type,
            "containerDiskInGb": 50,
            "volumeInGb": 200,
            "volumeMountPath": "/workspace",
            "imageName": image,
            "dockerArgs": "",
            "ports": "22/tcp",
            "env": [
                {"key": "PARALLEL_WORKERS", "value": str(workers)},
                {"key": "OMP_NUM_THREADS", "value": "6"},
                {"key": "MALLOC_ARENA_MAX", "value": "2"},
            ],
        }
    }
    data = _gql_request(api_key, mutation, variables)
    return data["data"]["podFindAndDeployOnDemand"]


def get_pod_status(api_key: str, pod_id: str) -> Dict[str, Any]:
    """Fetch current status of a RunPod pod.

    Parameters
    ----------
    api_key:
        RunPod API key.
    pod_id:
        Pod ID returned by :func:`launch_pod`.

    Returns
    -------
    dict
        Pod info dict with ``id``, ``desiredStatus``, ``runtime`` keys.
    """
    query = """
    query Pod($podId: String!) {
      pod(input: { podId: $podId }) {
        id
        desiredStatus
        lastStatusChange
        runtime {
          ports { ip privatePort publicPort type }
        }
      }
    }
    """
    data = _gql_request(api_key, query, {"podId": pod_id})
    return data["data"]["pod"]


def terminate_pod(api_key: str, pod_id: str) -> bool:
    """Terminate (stop + remove) a RunPod pod.

    Parameters
    ----------
    api_key:
        RunPod API key.
    pod_id:
        Pod ID to terminate.

    Returns
    -------
    bool
        True if the terminate request succeeded.
    """
    mutation = """
    mutation PodTerminate($input: PodTerminateInput!) {
      podTerminate(input: $input)
    }
    """
    _gql_request(api_key, mutation, {"input": {"podId": pod_id}})
    return True


# ---------------------------------------------------------------------------
# SSH / rsync helpers
# ---------------------------------------------------------------------------


def _ssh_cmd(ip: str, port: str, command: str, timeout: int = 60) -> int:
    """Run a command on the pod via SSH and return the exit code."""
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-p", str(port),
        "root@{}".format(ip),
        command,
    ]
    result = subprocess.run(cmd, timeout=timeout)
    return result.returncode


def _rsync_pull(
    ip: str,
    port: str,
    remote_dir: str = REMOTE_TRACKING_DIR,
    local_dir: str = LOCAL_TRACKING_DIR,
    dry_run: bool = False,
) -> int:
    """Rsync completed tracking results from the pod to local storage.

    Parameters
    ----------
    ip:
        Pod IP address.
    port:
        Pod SSH port.
    remote_dir:
        Remote path to pull from.
    local_dir:
        Local destination path.
    dry_run:
        If True, append ``--dry-run`` to rsync and print without transferring.

    Returns
    -------
    int
        rsync exit code.
    """
    Path(local_dir).mkdir(parents=True, exist_ok=True)
    cmd = [
        "rsync",
        "-az",
        "--progress",
        "-e", "ssh -o StrictHostKeyChecking=no -p {}".format(port),
    ]
    if dry_run:
        cmd.append("--dry-run")
    cmd += ["root@{}:{}/".format(ip, remote_dir), "{}/".format(local_dir)]
    result = subprocess.run(cmd, timeout=300)
    return result.returncode


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


def cmd_launch(args: argparse.Namespace, cfg: Dict[str, str]) -> int:
    """Provision a new pod and print connection details."""
    _require_credentials(cfg, "RUNPOD_API_KEY")
    api_key = cfg["RUNPOD_API_KEY"]
    gpu = getattr(args, "gpu", DEFAULT_GPU) or DEFAULT_GPU
    workers = getattr(args, "workers", 6) or 6

    print("[pod_manager] Launching pod - GPU: {}, workers: {}".format(gpu, workers))
    try:
        pod = launch_pod(api_key, gpu_type=gpu, workers=workers)
    except RuntimeError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1

    pod_id = pod.get("id", "unknown")
    print("[pod_manager] Pod created: {}".format(pod_id))

    # Poll until running (max 5 min)
    print("[pod_manager] Waiting for pod to reach RUNNING state...")
    for attempt in range(30):
        time.sleep(10)
        try:
            info = get_pod_status(api_key, pod_id)
        except RuntimeError:
            continue
        status = info.get("desiredStatus", "")
        print("  [{}/30] status={}".format(attempt + 1, status))
        if status == "RUNNING":
            ports = info.get("runtime", {}).get("ports", [])
            ssh_port = next(
                (p["publicPort"] for p in ports if p.get("privatePort") == 22), None
            )
            ip = next(
                (p["ip"] for p in ports if p.get("privatePort") == 22), None
            )
            print("[pod_manager] Pod RUNNING - IP={}, SSH port={}".format(ip, ssh_port))
            print("[pod_manager] To monitor: ssh -p {} root@{}".format(ssh_port, ip))
            print("  export RUNPOD_IP={}".format(ip))
            print("  export RUNPOD_PORT={}".format(ssh_port))
            print("  export RUNPOD_POD_ID={}".format(pod_id))
            return 0

    print("ERROR: Pod did not reach RUNNING state within 5 minutes.", file=sys.stderr)
    return 1


def cmd_status(args: argparse.Namespace, cfg: Dict[str, str]) -> int:
    """Print pod status - works with API or SSH connectivity check."""
    api_key = cfg.get("RUNPOD_API_KEY")
    pod_id = cfg.get("RUNPOD_POD_ID")
    ip = cfg.get("RUNPOD_IP")
    port = cfg.get("RUNPOD_PORT", "22")

    if not ip and not pod_id:
        dot_runpod = Path(__file__).parent.parent / RUNPOD_CONFIG_FILE
        print(
            "ERROR: No RUNPOD_IP set and no .runpod file found at {}. "
            "Set RUNPOD_IP (and optionally RUNPOD_PORT) in your environment or .runpod.".format(
                dot_runpod
            ),
            file=sys.stderr,
        )
        return 1

    if api_key and pod_id:
        try:
            info = get_pod_status(api_key, pod_id)
            print("[pod_manager] Pod {}: {}".format(pod_id, info.get("desiredStatus", "UNKNOWN")))
        except RuntimeError as exc:
            print("[pod_manager] API error: {}".format(exc), file=sys.stderr)
            # Fall through to SSH check

    if ip:
        rc = _ssh_cmd(ip, str(port), "nvidia-smi --query-gpu=name --format=csv,noheader", timeout=15)
        if rc == 0:
            print("[pod_manager] SSH reachable - {}:{}".format(ip, port))
        else:
            print("[pod_manager] SSH unreachable - {}:{} (exit {})".format(ip, port, rc))
        return rc

    return 0


def cmd_sync(args: argparse.Namespace, cfg: Dict[str, str]) -> int:
    """Pull tracking results from pod; --dry-run prints without transferring."""
    dry_run: bool = getattr(args, "dry_run", False)
    ip = cfg.get("RUNPOD_IP")
    port = cfg.get("RUNPOD_PORT", "22")

    if dry_run:
        print("[pod_manager] dry-run sync: would pull {} -> {}".format(
            REMOTE_TRACKING_DIR, LOCAL_TRACKING_DIR
        ))
        print("[pod_manager] dry-run: no files transferred")
        return 0

    if not ip:
        print(
            "ERROR: RUNPOD_IP not set. Export it or add to .runpod file.",
            file=sys.stderr,
        )
        return 1

    print("[pod_manager] Syncing {}:{} {} -> {}".format(
        ip, port, REMOTE_TRACKING_DIR, LOCAL_TRACKING_DIR
    ))
    rc = _rsync_pull(ip, str(port), dry_run=False)
    if rc == 0:
        print("[pod_manager] Sync complete.")
    else:
        print("[pod_manager] rsync exited {}".format(rc), file=sys.stderr)
    return rc


def cmd_teardown(args: argparse.Namespace, cfg: Dict[str, str]) -> int:
    """Terminate pod - requires RUNPOD_API_KEY + RUNPOD_POD_ID."""
    force: bool = getattr(args, "force", False)

    _require_credentials(cfg, "RUNPOD_API_KEY", "RUNPOD_POD_ID")
    api_key = cfg["RUNPOD_API_KEY"]
    pod_id = cfg["RUNPOD_POD_ID"]

    if not force:
        answer = input(
            "[pod_manager] Terminate pod {}? Ephemeral disk will be wiped. [y/N] ".format(pod_id)
        ).strip().lower()
        if answer not in ("y", "yes"):
            print("[pod_manager] Teardown cancelled.")
            return 0

    print("[pod_manager] Terminating pod {}...".format(pod_id))
    try:
        terminate_pod(api_key, pod_id)
        print("[pod_manager] Pod {} terminated.".format(pod_id))
        return 0
    except RuntimeError as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="pod_manager",
        description="Autonomous RunPod GPU pod lifecycle manager for NBA ingest.",
    )
    sub = parser.add_subparsers(dest="subcommand", metavar="SUBCOMMAND")

    # launch
    p_launch = sub.add_parser("launch", help="Provision a new RunPod GPU pod.")
    p_launch.add_argument(
        "--gpu",
        default=DEFAULT_GPU,
        help="GPU type (default: {!r})".format(DEFAULT_GPU),
    )
    p_launch.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Parallel pipeline workers on the pod (default: 6).",
    )

    # status
    sub.add_parser("status", help="Print pod status (SSH or API).")

    # sync
    p_sync = sub.add_parser("sync", help="Pull tracking results from pod.")
    p_sync.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Print what would be synced without transferring.",
    )

    # teardown
    p_tear = sub.add_parser("teardown", help="Terminate the pod.")
    p_tear.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt.",
    )

    return parser


def main() -> int:
    """Entry point - parse args and dispatch to the correct subcommand."""
    parser = build_parser()
    args = parser.parse_args()

    if args.subcommand is None:
        parser.print_help()
        return 0

    cfg = _get_config()

    dispatch = {
        "launch": cmd_launch,
        "status": cmd_status,
        "sync": cmd_sync,
        "teardown": cmd_teardown,
    }
    handler = dispatch[args.subcommand]
    return handler(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
