"""G62 run-environment sidecar: capture(), write() and read() for evidence artifacts.

Additive: it only creates a NEW file named ``environment.json`` beside an artifact, and ``read()``
returns ``None`` for an artifact with none, so a stampless artifact stays readable. ``capture()``
never raises -- an unimportable library, an unreadable git revision or cgroup file and a missing
named module each become an explicit null carrying its reason. As a script it prints one capture.
"""
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "g62_environment_sidecar_v1"
SIDECAR_NAME = "environment.json"
LIBRARIES = ("cv2", "numpy", "pandas", "scipy", "sklearn", "torch", "ultralytics")
THREAD_VARS = ("MKL_NUM_THREADS", "OMP_NUM_THREADS")
POD_MARKER = "/workspace/nba-ai-system"
ROLE_RULE = "role is 'pod' when " + POD_MARKER + " exists, else 'local'"
CGROUP_FILES = ("/sys/fs/cgroup/cpu.max", "/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
NO_SEED = "no seeded randomness on this route"

_FILE = globals().get("__file__", "")
_ROOT = Path(_FILE).resolve().parents[2] if _FILE.endswith("env_sidecar.py") else Path.cwd()


def _imported(name):
    try:
        return __import__(name)
    except BaseException:
        return None


def _torch_facts(torch):
    threads = {name: os.environ.get(name) for name in THREAD_VARS}
    threads["torch_num_threads"] = None
    build = {"cuda_available": None, "cuda_version": None, "cudnn_version": None, "unavailable_reason": None if torch is not None else "torch not importable"}
    if torch is None:
        return threads, build
    try:
        threads["torch_num_threads"] = int(torch.get_num_threads())
        build["cuda_available"] = bool(torch.cuda.is_available())
        build["cuda_version"] = getattr(getattr(torch, "version", None), "cuda", None)
        build["cudnn_version"] = torch.backends.cudnn.version()
    except BaseException as exc:
        build["unavailable_reason"] = "probe failed: " + type(exc).__name__
    return threads, build


def _git(root):
    out = {"head_sha": None, "dirty": None, "unavailable_reason": None}
    cmd = ["git", "-C", str(root)]
    kw = {"capture_output": True, "text": True, "timeout": 60}
    try:
        sha = subprocess.run(cmd + ["rev-parse", "HEAD"], **kw)
        status = subprocess.run(cmd + ["status", "--porcelain"], **kw)
    except BaseException as exc:
        out["unavailable_reason"] = "git not runnable: " + type(exc).__name__
        return out
    if sha.returncode != 0 or not sha.stdout.strip():
        out["unavailable_reason"] = "git rev-parse exit %d: %s" % (sha.returncode, sha.stderr.strip()[:120] or "no output")
        return out
    out["head_sha"] = sha.stdout.strip()
    if status.returncode != 0:
        out["unavailable_reason"] = "git status exit %d; dirty flag unknown" % status.returncode
    else:
        out["dirty"] = bool(status.stdout.strip())
    return out


def _cgroup_cpu_quota():
    for name in CGROUP_FILES:
        try:
            text = Path(name).read_text(encoding="ascii").strip()
        except BaseException:
            continue
        if text:
            return name + "=" + text
    return None


def _modules(paths, root):
    out = []
    for item in sorted({str(p) for p in (paths or ())}):
        source = Path(item) if Path(item).is_absolute() else root / item
        record = {"path": item.replace("\\", "/"), "sha256": None, "unavailable_reason": None}
        try:
            record["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        except BaseException as exc:
            record["unavailable_reason"] = "unreadable: " + type(exc).__name__
        out.append(record)
    return out


def capture(modules=None, seed=None, seed_reason=None, root=None) -> dict:
    """Run-environment stamp for this process; `modules` names the files that fix the result."""
    base = Path(root) if root is not None else _ROOT
    threads, build = _torch_facts(_imported("torch"))
    try:
        hostname = socket.gethostname()
    except BaseException:
        hostname = None
    if seed_reason is None:
        seed_reason = NO_SEED if seed is None else "seed supplied by the caller"
    return {
        "captured_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cgroup_cpu_quota": _cgroup_cpu_quota(),
        "cpu_count": os.cpu_count(),
        "git": _git(base),
        "host": {"hostname": hostname, "role": "pod" if Path(POD_MARKER).exists() else "local", "role_rule": ROLE_RULE},
        "libraries": {name: str(getattr(_imported(name), "__version__", "") or "") or None for name in LIBRARIES},
        "modules": _modules(modules, base),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "schema": SCHEMA,
        "seed": seed,
        "seed_reason": seed_reason,
        "threads": threads,
        "torch_build": build,
    }


def _resolve(path):
    target = Path(path)
    return target if target.suffix == ".json" else target / SIDECAR_NAME


def write(path, **kwargs) -> Path:
    """Write the stamp beside an artifact directory (or to an explicit .json path)."""
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(capture(**kwargs), indent=2, sort_keys=True, ensure_ascii=True)
    target.write_text(body + "\n", encoding="ascii")
    return target


def read(path):
    """Return the stamp, or None when the artifact has none. Stampless artifacts stay readable."""
    try:
        return json.loads(_resolve(path).read_text(encoding="ascii"))
    except FileNotFoundError:
        return None


if __name__ == "__main__":
    print(json.dumps(capture(), indent=2, sort_keys=True, ensure_ascii=True))
