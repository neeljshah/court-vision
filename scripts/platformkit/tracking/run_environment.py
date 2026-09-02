"""Additive provenance stamps for newly written tracking evidence."""
from __future__ import annotations

import hashlib
import importlib
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


_ROOT = Path(__file__).resolve().parents[3]


def _package_version(name: str, importer: Callable[[str], object]) -> str | None:
    try:
        return str(getattr(importer(name), "__version__"))
    except (ImportError, AttributeError):
        return None


def _torch_details(importer: Callable[[str], object]) -> tuple[str | None, bool | None]:
    try:
        torch = importer("torch")
    except ImportError:
        return None, None
    try:
        available = bool(torch.cuda.is_available())
    except AttributeError:
        available = None
    return str(getattr(torch, "__version__", None)), available


def _git_value(args: list[str], runner: Callable[..., subprocess.CompletedProcess[str]],
               allow_empty: bool = False) -> tuple[str | None, str | None]:
    try:
        result = runner(args, cwd=_ROOT, capture_output=True, text=True, check=False)
    except OSError as exc:
        return None, "git unavailable: %s" % exc
    value = (result.stdout or "").strip()
    if result.returncode or (not value and not allow_empty):
        return None, "git %s failed (exit %s): %s" % (
            " ".join(args[1:]), result.returncode, (result.stderr or "").strip() or "no output")
    return value, None


def _source_hashes(module_paths: Iterable[str | Path]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for item in module_paths:
        path = Path(item).resolve()
        try:
            name = str(path.relative_to(_ROOT)).replace("\\", "/")
            hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        except (OSError, ValueError) as exc:
            raise ValueError("cannot hash result module %s: %s" % (path, exc)) from exc
    return dict(sorted(hashes.items()))


def build_run_environment_stamp(
        seed: int | None, module_paths: Iterable[str | Path],
        seed_reason: str | None = None,
        importer: Callable[[str], object] = importlib.import_module,
        git_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    """Return provenance facts for one evidence artifact without deciding its verdict."""
    torch_version, cuda_available = _torch_details(importer)
    revision, revision_reason = _git_value(["git", "rev-parse", "HEAD"], git_runner)
    dirty_raw, dirty_reason = _git_value(
        ["git", "status", "--porcelain"], git_runner, allow_empty=True)
    dirty = None if dirty_raw is None else bool(dirty_raw)
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cv2_version": _package_version("cv2", importer),
        "numpy_version": _package_version("numpy", importer),
        "torch_version": torch_version,
        "cuda_available": cuda_available,
        "seed": seed,
        "seed_reason": seed_reason,
        "git_revision": revision,
        "git_revision_reason": revision_reason,
        "git_tree_dirty": dirty,
        "git_tree_dirty_reason": dirty_reason,
        "source_hashes_sha256": _source_hashes(module_paths),
    }


def with_run_environment(payload: dict[str, object], seed: int | None,
                         module_paths: Iterable[str | Path],
                         seed_reason: str | None = None) -> dict[str, object]:
    """Return an additive copy; historical payloads remain valid without this key."""
    stamped = dict(payload)
    stamped["run_environment"] = build_run_environment_stamp(
        seed, module_paths, seed_reason=seed_reason)
    return stamped
