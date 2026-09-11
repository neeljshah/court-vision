"""G390 receipt-only wrapper for a future pod A8 process; it never launches one."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

ROW_GPU_MINUTES = 90.0
CUMULATIVE_GPU_MINUTES = 120.0
EXPECTED_ROUTE_HASH = "cbc7cd9dfb7e18691f310b7594be046ac0d3184a279c43d8eb427210355bc9ea"
EXPECTED_WEIGHT_HASH = "bc979654e281c5de6e0e992e1f9587b3a9faa2eec996ea41b1b03954ba0b6e52"


def sha256_file(path: Path) -> str:
    """Return one file hash, refusing a source absent from this worktree."""
    path = Path(path)
    if not path.is_file():
        print("ABSENT-IN-WORKTREE " + path.as_posix())
        raise FileNotFoundError("ABSENT-IN-WORKTREE " + path.as_posix())
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_launch_hashes(route_path: Path, weight_path: Path) -> dict[str, str]:
    """Return exact future pod identities, or refuse a drifted launch."""
    hashes = {"route": sha256_file(route_path), "weight": sha256_file(weight_path)}
    if hashes["route"] != EXPECTED_ROUTE_HASH:
        raise ValueError("route-hash-mismatch")
    if hashes["weight"] != EXPECTED_WEIGHT_HASH:
        raise ValueError("weight-hash-mismatch")
    return hashes


def hash_artifacts(paths: Mapping[str, Path]) -> dict[str, str]:
    """Hash every named route, checkpoint, or output supplied to a future receipt."""
    return {name: sha256_file(path) for name, path in sorted(paths.items())}


def record_gpu_run(
    receipt_path: Path,
    *,
    phase: str,
    elapsed_seconds: float,
    prior_training_gpu_minutes: float,
    identities: Mapping[str, str],
) -> dict[str, object]:
    """Write a LF receipt for an already-completed process and enforce both caps."""
    if phase not in {"training", "inference"} or elapsed_seconds < 0:
        raise ValueError("invalid-run-receipt")
    gpu_minutes = elapsed_seconds / 60.0
    if phase == "training" and (gpu_minutes > ROW_GPU_MINUTES or
                                prior_training_gpu_minutes + gpu_minutes > CUMULATIVE_GPU_MINUTES):
        raise ValueError("gpu-minute-budget-exceeded")
    receipt = {
        "phase": phase,
        "gpu_minutes": gpu_minutes,
        "prior_training_gpu_minutes": prior_training_gpu_minutes,
        "cumulative_training_gpu_minutes": prior_training_gpu_minutes +
        (gpu_minutes if phase == "training" else 0.0),
        "identities": dict(sorted(identities.items())),
    }
    target = Path(receipt_path)
    if target.exists():
        raise ValueError("run-receipt-immutable")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                      encoding="ascii", newline="\n")
    return receipt
