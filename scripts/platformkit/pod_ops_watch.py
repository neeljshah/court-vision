"""Emit a single JSON health record for the pod cron monitor."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
GIB = 1024 * 1024 * 1024
RAM_WARN_GB = 90.0
RAM_FAIL_GB = 105.0
ROOT_DISK_FAIL_GB = 5.0
BEAT_FAIL_S = 300.0
BEAT_WARN_S = 3600.0


def _meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value, *_ = line.replace(":", "").split()
            values[key] = int(value) * 1024
    except (OSError, ValueError):
        pass
    return values


def _own_private_bytes() -> int:
    total = 0
    uid = os.getuid()
    proc = Path("/proc")
    if not proc.exists():
        return total
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
            for line in (entry / "smaps_rollup").read_text().splitlines():
                if line.startswith(("Private_Clean:", "Private_Dirty:", "Private_Hugetlb:")):
                    total += int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            continue
    return total


def collect_ram() -> float:
    """Return pod RAM used in GiB, based on private process commit when available."""
    private_bytes = _own_private_bytes()
    info = _meminfo()
    if private_bytes:
        return round(private_bytes / GIB, 3)
    total = info.get("MemTotal", 0)
    available = info.get("MemAvailable", total)
    return round((total - available) / GIB, 3)


def disk_free_gb(path: str) -> float | None:
    try:
        output = subprocess.run(["df", "-Pk", path], capture_output=True, text=True, timeout=10, check=True).stdout
        fields = output.splitlines()[-1].split()
        return round(int(fields[3]) * 1024 / GIB, 3)
    except (IndexError, OSError, ValueError, subprocess.SubprocessError):
        return None


def collect_gpu() -> list[dict[str, Any]] | None:
    if not shutil.which("nvidia-smi"):
        return None
    command = ["nvidia-smi", "--query-gpu=index,name,memory.used,memory.total,utilization.gpu", "--format=csv,noheader,nounits"]
    try:
        output = subprocess.run(command, capture_output=True, text=True, timeout=10, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    gpus = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) == 5:
            gpus.append(dict(zip(("index", "name", "memory_used_mb", "memory_total_mb", "utilization_pct"), parts)))
    return gpus


def collect_heartbeats(now: float | None = None) -> tuple[float | None, list[str]]:
    now = time.time() if now is None else now
    beats = list((ROOT / "data/cache/daemon_heartbeats").glob("*.txt"))
    if not beats:
        return None, []
    ages = [(max(0.0, now - beat.stat().st_mtime), beat.name) for beat in beats]
    return min(age for age, _ in ages), sorted(name for age, name in ages if age > BEAT_WARN_S)


def ledger_last_ts() -> Any:
    ledger = ROOT / "data/tracking_reports/ledger.jsonl"
    try:
        with ledger.open("r", encoding="utf-8") as handle:
            lines = [line for line in handle if line.strip()]
        return json.loads(lines[-1]).get("ts") if lines else None
    except (OSError, ValueError):
        return None


def verdict_for(ram_gb: float, disk_root_gb: float | None, newest_beat_age_s: float | None, stale: list[str]) -> str:
    if ram_gb > RAM_FAIL_GB or (disk_root_gb is not None and disk_root_gb < ROOT_DISK_FAIL_GB):
        return "FAIL"
    if newest_beat_age_s is not None and newest_beat_age_s > BEAT_FAIL_S:
        return "FAIL"
    if ram_gb > RAM_WARN_GB or stale:
        return "WARN"
    return "OK"


def build_record(now: float | None = None) -> dict[str, Any]:
    ram_gb = collect_ram()
    disk_ws_gb = disk_free_gb("/workspace")
    disk_root_gb = disk_free_gb("/root")
    newest_beat_age_s, stale = collect_heartbeats(now)
    return {
        "ts": int(time.time() if now is None else now),
        "ram_gb": ram_gb,
        "disk_ws_gb": disk_ws_gb,
        "disk_root_gb": disk_root_gb,
        "gpu": collect_gpu(),
        "newest_beat_age_s": newest_beat_age_s,
        "stale": stale,
        "ledger_last_ts": ledger_last_ts(),
        "verdict": verdict_for(ram_gb, disk_root_gb, newest_beat_age_s, stale),
    }


def main() -> int:
    record = build_record()
    print(json.dumps(record, separators=(",", ":"), default=str))
    return 1 if record["verdict"] == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
