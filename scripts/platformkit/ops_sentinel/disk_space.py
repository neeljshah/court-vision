"""scripts.platformkit.ops_sentinel.disk_space -- free-GB on the data drive +
growth-STALL detection for the 5 key capture dirs (gumbo_live, ingame_grade,
ingame_grade_joined, kalshi_trades, line_history).

A capture dir whose NEWEST file mtime exceeds 2x its expected write cadence
DURING an active slate window reads RED (silent starvation); outside the slate
window it reads IDLE (an empty overnight is honest, never red). Read-only, no
restart authority.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ops_sentinel/test_disk_space.py -q
"""
from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, NamedTuple, Optional

from scripts.platformkit.ops_sentinel.status_doc import (
    GREEN, IDLE, OPS_DIR, RED, YELLOW, repo_root, write_doc,
)

COMPONENT = "ops_disk_space"
STATUS_PATH = OPS_DIR / "disk_space.json"
_NOTE = ("free-GB + growth-stall visibility only; read-only, NO restart "
         "authority, no $ field. IDLE outside the slate window is honest.")

FREE_GB_RED = 5.0
FREE_GB_YELLOW = 20.0

# ponytail: crude local-hour slate proxy (13:00-23:59 covers MLB day slates
# through NBA/soccer evenings on this ET box); upgrade path = read the live
# slate from the schedule feed if false-IDLE/false-RED ever matters.
SLATE_HOURS = range(13, 24)


class _Dir(NamedTuple):
    path: Path          # repo-relative capture dir
    cadence_sec: float  # expected write cadence during an active slate


_R = repo_root()
TABLE: Dict[str, _Dir] = {
    "gumbo_live": _Dir(_R / "data" / "domains" / "mlb" / "gumbo_live", 1800.0),
    "ingame_grade": _Dir(_R / "data" / "cache" / "ingame_grade", 1800.0),
    "ingame_grade_joined": _Dir(
        _R / "data" / "cache" / "ingame_grade_joined", 3600.0),
    "kalshi_trades": _Dir(
        _R / "data" / "cache" / "book_depth" / "kalshi_trades", 1800.0),
    "line_history": _Dir(_R / "data" / "cache" / "line_history", 900.0),
}


def slate_active(now: Optional[float] = None) -> bool:
    ts = float(now) if now is not None else time.time()
    return datetime.fromtimestamp(ts).hour in SLATE_HOURS


def newest_mtime(path: Path) -> Optional[float]:
    """Newest file mtime under *path* (recursive). Missing/empty -> None."""
    newest: Optional[float] = None
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    m = os.stat(os.path.join(root, f)).st_mtime
                    if newest is None or m > newest:
                        newest = m
                except OSError:
                    continue
    except Exception:  # noqa: BLE001
        return None
    return newest


def check_free_gb(*, usage_fn: Optional[Callable[[str], Any]] = None,
                  ) -> Dict[str, Any]:
    """Free-GB row for the drive holding data/. Never raises."""
    try:
        fn = usage_fn if usage_fn is not None else shutil.disk_usage
        free_gb = fn(str(_R / "data")).free / 1e9
        status = (RED if free_gb < FREE_GB_RED
                  else YELLOW if free_gb < FREE_GB_YELLOW else GREEN)
        return {"name": "disk_free", "status": status,
                "free_gb": round(free_gb, 2), "red_below_gb": FREE_GB_RED,
                "yellow_below_gb": FREE_GB_YELLOW, "reason": None}
    except Exception as exc:  # noqa: BLE001
        return {"name": "disk_free", "status": RED, "free_gb": None,
                "reason": "error:%s" % str(exc)[:80]}


def check_all(*, now: Optional[float] = None,
              table: Optional[Dict[str, _Dir]] = None,
              slate_fn: Optional[Callable[[float], bool]] = None,
              usage_fn: Optional[Callable[[str], Any]] = None,
              ) -> List[Dict[str, Any]]:
    ts = float(now) if now is not None else time.time()
    in_slate = (slate_fn if slate_fn is not None else slate_active)(ts)
    rows = [check_free_gb(usage_fn=usage_fn)]
    for name, ent in sorted((table if table is not None else TABLE).items()):
        row: Dict[str, Any] = {"name": name, "path": str(ent.path),
                               "cadence_sec": ent.cadence_sec,
                               "slate_active": in_slate}
        try:
            if not ent.path.exists():
                row.update(status=RED, age_sec=None, reason="missing_dir")
                rows.append(row)
                continue
            m = newest_mtime(ent.path)
            age = None if m is None else max(0.0, ts - m)
            row["age_sec"] = None if age is None else round(age, 1)
            if not in_slate:
                row.update(status=IDLE, reason="outside_slate_window")
            elif age is None or age > 2.0 * ent.cadence_sec:
                row.update(status=RED, reason="growth_stalled")
            else:
                row.update(status=GREEN, reason=None)
        except Exception as exc:  # noqa: BLE001
            row.update(status=RED, reason="error:%s" % str(exc)[:80])
        rows.append(row)
    return rows


def tick(*, now: Optional[float] = None,
         status_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Check -> status doc. Never raises."""
    ts = float(now) if now is not None else time.time()
    try:
        rows = check_all(now=ts)
    except Exception as exc:  # noqa: BLE001
        rows = [{"name": "disk_space", "status": RED,
                 "reason": "error:%s" % str(exc)[:80]}]
    write_doc(status_path if status_path is not None else STATUS_PATH,
              COMPONENT, rows, now=ts, honest_note=_NOTE)
    return rows


__all__ = ["TABLE", "COMPONENT", "STATUS_PATH", "FREE_GB_RED", "FREE_GB_YELLOW",
           "slate_active", "newest_mtime", "check_free_gb", "check_all", "tick"]
