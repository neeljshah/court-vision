"""scripts.platformkit.ops_sentinel.status_doc -- shared status-doc writer for the
failsafe sentinels (guard_integrity / disk_space / heartbeat_coverage /
exception_burst). Same atomic tmp+os.replace doc shape as output_freshness.
Never raises."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_REPO = Path(__file__).resolve().parents[3]
OPS_DIR = _REPO / "data" / "frontend" / "ops"
STATE_DIR = _REPO / "data" / "cache" / "ops_sentinel"

GREEN = "GREEN"
YELLOW = "YELLOW"
RED = "RED"
NA = "NA"
IDLE = "IDLE"


def repo_root() -> Path:
    return _REPO


def write_doc(path: Path, component: str, rows: List[Dict[str, Any]], *,
              now: Optional[float] = None, honest_note: str = "",
              extra: Optional[Dict[str, Any]] = None) -> bool:
    """Atomically write a sentinel status doc. Never raises."""
    try:
        ts = float(now) if now is not None else time.time()
        rows = list(rows or [])
        n_red = sum(1 for r in rows if r.get("status") == RED)
        n_yellow = sum(1 for r in rows if r.get("status") == YELLOW)
        doc: Dict[str, Any] = {
            "generated_at": ts, "component": component, "rows": rows,
            "n_rows": len(rows), "n_red": n_red, "n_yellow": n_yellow,
            "overall": RED if n_red else (YELLOW if n_yellow else GREEN),
            "honest_note": honest_note,
        }
        if extra:
            doc.update(extra)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=True, indent=2, sort_keys=True),
                       encoding="ascii")
        os.replace(str(tmp), str(p))
        return True
    except Exception:  # noqa: BLE001 -- a failed status write never sinks a tick
        return False


def load_json(path: Path) -> Dict[str, Any]:
    """Best-effort JSON object read. Missing/bad -> {}. Never raises."""
    try:
        p = Path(path)
        if not p.exists():
            return {}
        doc = json.loads(p.read_text(encoding="ascii"))
        return doc if isinstance(doc, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


__all__ = ["OPS_DIR", "STATE_DIR", "GREEN", "YELLOW", "RED", "NA", "IDLE",
           "repo_root", "write_doc", "load_json"]
