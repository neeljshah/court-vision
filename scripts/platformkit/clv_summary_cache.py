"""scripts.platformkit.clv_summary_cache -- mtime-keyed memo over clv_ledger.

clv_ledger.load_ledger() re-parses the whole JSONL ledger on every call (tens of
ms for the current ~5k-row / 4MB file, growing with the ledger); clv_summary()
adds a further aggregation pass. Every warm /api/paper/clv and /api/paper/open
request re-pays both. This module memoizes on (path, mtime, size) -- the same
pattern as clv_close_lookup._MEM / pm_trail_browse._ENRICH_CACHE (both
load-bearing precedents in this repo) -- so a repeat call against an unchanged
ledger is a dict hit, not a re-parse/re-aggregate.

Bounded to the single latest version per path (no unbounded growth). A lock
guards concurrent callers from double-parsing. Read-only: never mutates the
on-disk ledger, never raises (falls back to the uncached read on a stat race).
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.platformkit import clv_ledger as _cl

_LOCK = threading.Lock()
_LEDGER_CACHE: Dict[str, Tuple[Tuple[float, int], List[Dict[str, Any]]]] = {}
_SUMMARY_CACHE: Dict[str, Tuple[Tuple[float, int], Dict[str, Any]]] = {}


def _stamp(target: Path) -> Optional[Tuple[float, int]]:
    try:
        st = target.stat()
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


def cached_load_ledger(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Memoized clv_ledger.load_ledger(path): cache hit iff mtime+size unchanged."""
    target = Path(path) if path is not None else _cl.DEFAULT_LEDGER
    key = str(target)
    stamp = _stamp(target)
    if stamp is None:
        return _cl.load_ledger(target)  # missing/stat-race -- no cache
    with _LOCK:
        hit = _LEDGER_CACHE.get(key)
        if hit is not None and hit[0] == stamp:
            return hit[1]
    rows = _cl.load_ledger(target)
    with _LOCK:
        _LEDGER_CACHE[key] = (stamp, rows)
    return rows


def cached_clv_summary(path: Optional[Path] = None) -> Dict[str, Any]:
    """Memoized clv_ledger.clv_summary() over cached_load_ledger(path)."""
    target = Path(path) if path is not None else _cl.DEFAULT_LEDGER
    key = str(target)
    stamp = _stamp(target)
    if stamp is None:
        return _cl.clv_summary(_cl.load_ledger(target))
    with _LOCK:
        hit = _SUMMARY_CACHE.get(key)
        if hit is not None and hit[0] == stamp:
            return hit[1]
    summary = _cl.clv_summary(cached_load_ledger(target))
    with _LOCK:
        _SUMMARY_CACHE[key] = (stamp, summary)
    return summary


__all__ = ["cached_load_ledger", "cached_clv_summary"]
