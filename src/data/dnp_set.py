"""src/data/dnp_set.py — tier3-11 (loop 5) DNP-aware projection-set loader.

Wraps `data/dnp_rows.parquet` (or its CSV/JSONL fallback) produced by
`scripts/aggregate_dnp_rows.py`. The loader is GATED on file existence:
when the parquet is absent (fresh checkout, or aggregation has not run)
all accessors return empty so callers degrade gracefully.

Public API
----------
    load_dnp_rows() -> pd.DataFrame | None
    dnp_for_game(game_id: str) -> List[Dict]
    dnp_for_player(player_id: int, season: str | None = None) -> List[Dict]
    by_game_index() -> Dict[str, List[Dict]]

See module docstring of scripts/aggregate_dnp_rows.py for schema +
provenance details.
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
_DEFAULT_PATH = os.path.join(PROJECT_DIR, "data", "dnp_rows.parquet")
_CSV_FALLBACK = _DEFAULT_PATH.replace(".parquet", ".csv")
_JSONL_FALLBACK = _DEFAULT_PATH.replace(".parquet", ".jsonl")

# Process-level cache. dnp_rows.parquet is small (tens of thousands of
# rows at most) so loading once per process is fine.
_CACHE: Optional[list] = None
_CACHE_BY_GAME: Optional[Dict[str, List[Dict]]] = None


def _records_from_file(path: str) -> Optional[List[Dict]]:
    """Read DNP rows from a parquet/csv/jsonl file into list of dicts."""
    if not os.path.exists(path):
        return None
    try:
        if path.endswith(".parquet"):
            import pandas as pd  # noqa: PLC0415
            df = pd.read_parquet(path)
            return df.to_dict("records")
        if path.endswith(".csv"):
            import pandas as pd  # noqa: PLC0415
            df = pd.read_csv(path)
            return df.to_dict("records")
        if path.endswith(".jsonl"):
            out = []
            with open(path, encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if ln:
                        out.append(json.loads(ln))
            return out
    except Exception:
        return None
    return None


def _ensure_loaded() -> None:
    """Populate _CACHE / _CACHE_BY_GAME lazily, only on first access.

    Walks the preferred parquet path first, then CSV, then JSONL. When
    none exists the cache becomes an empty list (so subsequent accessors
    return empty lists — the no-op back-compat path).
    """
    global _CACHE, _CACHE_BY_GAME
    if _CACHE is not None:
        return
    for path in (_DEFAULT_PATH, _CSV_FALLBACK, _JSONL_FALLBACK):
        recs = _records_from_file(path)
        if recs is not None:
            _CACHE = recs
            break
    if _CACHE is None:
        _CACHE = []
    by_game: Dict[str, List[Dict]] = {}
    for r in _CACHE:
        gid = str(r.get("game_id") or "").strip()
        if not gid:
            continue
        by_game.setdefault(gid, []).append(r)
    _CACHE_BY_GAME = by_game


def reset_cache() -> None:
    """Drop the process-level cache. Tests use this between cases."""
    global _CACHE, _CACHE_BY_GAME
    _CACHE = None
    _CACHE_BY_GAME = None


def load_dnp_rows():
    """Return the cached DNP records as a pandas DataFrame.

    Returns an empty DataFrame when the parquet is absent — never None,
    so call sites can chain `.empty` checks without a guard.
    """
    _ensure_loaded()
    try:
        import pandas as pd  # noqa: PLC0415
        return pd.DataFrame(_CACHE or [])
    except Exception:
        # pandas missing → return a thin shim that mimics .empty / len.
        class _ListDF:
            def __init__(self, data):
                self._data = data
            @property
            def empty(self):
                return not self._data
            def __len__(self):
                return len(self._data)
            def to_dict(self, _orient="records"):
                return list(self._data)
        return _ListDF(_CACHE or [])


def dnp_for_game(game_id: str) -> List[Dict]:
    """List of DNP records for a single game_id. [] when game has none."""
    _ensure_loaded()
    return list((_CACHE_BY_GAME or {}).get(str(game_id), []))


def dnp_for_player(player_id: int, season: Optional[str] = None) -> List[Dict]:
    """All DNP records for a player, optionally restricted to a season."""
    _ensure_loaded()
    out = []
    pid = int(player_id)
    for r in (_CACHE or []):
        try:
            rpid = int(r.get("player_id") or 0)
        except Exception:
            continue
        if rpid != pid:
            continue
        if season and str(r.get("season") or "") != season:
            continue
        out.append(r)
    return out


def by_game_index() -> Dict[str, List[Dict]]:
    """Whole game_id -> records map. Empty dict when no parquet."""
    _ensure_loaded()
    return dict(_CACHE_BY_GAME or {})


def count() -> int:
    """Total number of DNP rows in the cache."""
    _ensure_loaded()
    return len(_CACHE or [])
