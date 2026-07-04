"""scripts.platformkit.venue_history.progress_sidecar -- tiny shared JSON
progress-file read/write (atomic write via tmp+replace) used by both venue
backfill lanes (kalshi_intragame, polymarket_intragame) so an interrupted
resumable run persists its cursor/date + counters identically in both.

INVARIANTS: platformkit-only; <=300 LOC; ASCII; stdlib only.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/venue_history/test_progress_sidecar.py -q
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


def load_progress(path: Path) -> Dict[str, Any]:
    """Return the JSON dict at *path*, or {} if missing/unreadable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_progress(path: Path, doc: Dict[str, Any]) -> None:
    """Atomically write *doc* as JSON to *path* (tmp write + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1, default=str), encoding="utf-8")
    os.replace(str(tmp), str(path))


__all__ = ["load_progress", "save_progress"]
