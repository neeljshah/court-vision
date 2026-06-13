"""health_snapshot.py — System health snapshot module.

Returns a single JSON-serialisable dict describing the current health of the
CourtVision platform: loop heartbeat age, capture ledger freshness, API
liveness, registry parquet age, disk headroom, and vault write age.

Usage:
    from scripts.platformkit.obs.health_snapshot import snapshot
    state = snapshot()           # pure, side-effect-free

    python -m scripts.platformkit.obs.health_snapshot   # writes .bot_state/health_snapshot.json
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Thresholds (times in seconds)
STALE_LOOP_SEC: int = 86_400      # 24 h — loop heartbeat
CAPTURE_STALE_SEC: int = 3_600    # 1 h  — forward-capture ledger
REGISTRY_STALE_SEC: int = 86_400  # 24 h — registry parquets
VAULT_STALE_SEC: int = 172_800    # 48 h — vault auto-writes
DISK_MIN_GB: float = 5.0          # minimum free disk space


def _find_repo_root() -> Path:
    """Walk up from __file__ until a directory containing CLAUDE.md is found."""
    candidate = Path(__file__).resolve()
    for _ in range(10):
        candidate = candidate.parent
        if (candidate / "CLAUDE.md").exists():
            return candidate
    return Path(__file__).resolve().parents[3]  # fallback


REPO_ROOT: Path = _find_repo_root()


def _field(value: Any, unit: str, threshold: Any, **extras: Any) -> Dict[str, Any]:
    """Build a standardised field dict: value + unit + threshold + optional extras."""
    d: Dict[str, Any] = {"value": value, "unit": unit, "threshold": threshold}
    d.update(extras)
    return d


def _loop_heartbeat_age() -> Dict[str, Any]:
    """Age of data/registry/state.json; includes loop iter when present."""
    state_path = REPO_ROOT / "data" / "registry" / "state.json"
    if not state_path.exists():
        return _field(None, "sec", STALE_LOOP_SEC, note="absent")
    try:
        age = round(time.time() - os.path.getmtime(str(state_path)), 1)
    except OSError:
        return _field(None, "sec", STALE_LOOP_SEC, note="stat_error")
    result = _field(age, "sec", STALE_LOOP_SEC)
    try:
        with open(str(state_path), "r", encoding="utf-8") as fh:
            result["iter"] = json.load(fh).get("iter_id")
    except Exception:
        pass
    return result


def _parse_ts(raw: Any) -> Optional[float]:
    """Parse a ledger ts_utc_observed into an epoch-seconds float.

    The N-CLV-001 ledger writes ``ts_utc_observed`` as an ISO-8601 UTC string
    (e.g. ``2026-06-11T18:30:00Z``); a numeric epoch is also tolerated. Returns
    ``None`` if the value cannot be interpreted.
    """
    if raw is None:
        return None
    # Numeric epoch (int/float or a purely-numeric string).
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        s = raw.strip()
        try:
            return float(s)
        except ValueError:
            pass
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            return None
    return None


def _capture_row_age() -> Dict[str, Any]:
    """Age of the newest ts_utc_observed in forward-capture ledger JSONL files.

    Degrades gracefully when ledger_schema / ledger files are absent.
    """
    ledger_dir = REPO_ROOT / "data" / "lines" / "forward"
    if not ledger_dir.exists():
        return _field(None, "sec", CAPTURE_STALE_SEC, note="no_ledger")
    jsonl_files = glob.glob(str(ledger_dir / "**" / "*.jsonl"), recursive=True)
    if not jsonl_files:
        return _field(None, "sec", CAPTURE_STALE_SEC, note="no_ledger")

    newest_ts: Optional[float] = None
    for path in jsonl_files:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line).get("ts_utc_observed")
                    except json.JSONDecodeError:
                        continue
                    ts = _parse_ts(raw)
                    if ts is not None and (newest_ts is None or ts > newest_ts):
                        newest_ts = ts
        except OSError:
            continue

    if newest_ts is None:
        return _field(None, "sec", CAPTURE_STALE_SEC, note="no_rows")
    return _field(round(time.time() - newest_ts, 1), "sec", CAPTURE_STALE_SEC)


def _api_health() -> Dict[str, Any]:
    """Probe GET http://127.0.0.1:8077/health (1 s timeout). Never raises."""
    try:
        import urllib.request  # noqa: PLC0415
        req = urllib.request.Request(
            "http://127.0.0.1:8077/health",
            headers={"User-Agent": "health_snapshot/1.0"},
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            code = resp.getcode()
            value = "up" if code == 200 else f"http_{code}"
    except Exception:
        value = "unreachable"
    return _field(value, "status", "up")


def _registry_parquet_freshness() -> Dict[str, Any]:
    """Age of the newest *.parquet under data/registry/ (read-only stat)."""
    reg_dir = REPO_ROOT / "data" / "registry"
    if not reg_dir.exists():
        return _field(None, "sec", REGISTRY_STALE_SEC, note="absent")
    parquet_files = list(reg_dir.glob("*.parquet"))
    if not parquet_files:
        return _field(None, "sec", REGISTRY_STALE_SEC, note="no_parquets")
    now = time.time()
    newest_mtime: Optional[float] = None
    for pf in parquet_files:
        try:
            mt = os.path.getmtime(str(pf))
            if newest_mtime is None or mt > newest_mtime:
                newest_mtime = mt
        except OSError:
            continue
    if newest_mtime is None:
        return _field(None, "sec", REGISTRY_STALE_SEC, note="stat_error")
    return _field(round(now - newest_mtime, 1), "sec", REGISTRY_STALE_SEC)


def _disk_headroom() -> Dict[str, Any]:
    """Free disk space at repo root in GB."""
    try:
        free_gb = round(shutil.disk_usage(str(REPO_ROOT)).free / 1e9, 2)
    except OSError:
        return _field(None, "GB", DISK_MIN_GB, note="stat_error")
    return _field(free_gb, "GB", DISK_MIN_GB)


def _vault_autowrite_age() -> Dict[str, Any]:
    """Age of the newest file under vault/."""
    vault_dir = REPO_ROOT / "vault"
    if not vault_dir.exists():
        return _field(None, "sec", VAULT_STALE_SEC, note="absent")
    now = time.time()
    newest_mtime: Optional[float] = None
    for root_str, _dirs, files in os.walk(str(vault_dir)):
        for fname in files:
            try:
                mt = os.path.getmtime(os.path.join(root_str, fname))
                if newest_mtime is None or mt > newest_mtime:
                    newest_mtime = mt
            except OSError:
                continue
    if newest_mtime is None:
        return _field(None, "sec", VAULT_STALE_SEC, note="no_files")
    return _field(round(now - newest_mtime, 1), "sec", VAULT_STALE_SEC)


def snapshot() -> Dict[str, Any]:
    """Return a JSON-serialisable health snapshot dict.

    Pure and side-effect-free. All fields carry ``value``, ``unit``,
    and ``threshold`` keys.
    """
    return {
        "loop_heartbeat_age_sec": _loop_heartbeat_age(),
        "capture_row_age_sec": _capture_row_age(),
        "api_health": _api_health(),
        "registry_parquet_freshness_sec": _registry_parquet_freshness(),
        "disk_headroom_gb": _disk_headroom(),
        "last_vault_autowrite_age_sec": _vault_autowrite_age(),
    }


if __name__ == "__main__":
    import sys  # noqa: PLC0415
    sys.path.insert(0, str(REPO_ROOT / "scripts" / "bot_guards"))
    try:
        from _state import write_json_atomic as _wja  # type: ignore[import]
    except ImportError:
        _wja = None  # type: ignore[assignment]

    data = snapshot()
    out_path = REPO_ROOT / ".bot_state" / "health_snapshot.json"
    if _wja is not None:
        _wja(out_path, data)
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps(data, indent=2))
