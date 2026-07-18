"""scripts.platformkit.calibration_grid.caveats -- reliability-map lookup for
the winprob_dispatch caveat seam. Never authors a number; only reads the
per-sport reliability map JSON that {nba,mlb,soccer}_grid.py already wrote and
reports whether THIS state is one the model is calibrated on.

Fail-closed by construction: a missing map file, an unmapped state, or any
parse failure returns can_price=False with a specific reason -- never a
silent pass-through. edge_claimed is never set true anywhere in this module.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.platformkit.calibration_grid.buckets import mlb_bucket, nba_bucket, soccer_bucket

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MAP_DIR = _REPO_ROOT / "data" / "cache" / "calibration_grid"
_MAP_PATHS = {
    "nba": _MAP_DIR / "nba_reliability_map.json",
    "mlb": _MAP_DIR / "mlb_reliability_map.json",
    "soccer": _MAP_DIR / "soccer_reliability_map.json",
    "soccer_intl": _MAP_DIR / "soccer_reliability_map.json",
}


@lru_cache(maxsize=None)
def load_reliability_map(sport: str) -> Optional[Dict[str, Any]]:
    """The parsed reliability-map doc for `sport`, or None if it hasn't been
    built yet / is unreadable. Cached -- call load_reliability_map.cache_clear()
    in tests that write a fresh map mid-run."""
    path = _MAP_PATHS.get(str(sport).lower())
    if path is None or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def bucket_for(sport: str, ingame_state: Dict[str, Any]) -> Optional[str]:
    """The bucket key for this sport's state dict, or None if the sport has no
    bucket function or the state is missing its required keys."""
    s = str(sport).lower()
    st = ingame_state or {}
    if s == "nba":
        if "elapsed" not in st:
            return None
        lead = float(st.get("home_score", 0) or 0) - float(st.get("away_score", 0) or 0)
        elapsed = float(st["elapsed"])
        return nba_bucket(elapsed, lead, is_ot=elapsed > 48.0)
    if s == "mlb":
        if "inning" not in st:
            return None
        diff = float(st.get("home_score", 0) or 0) - float(st.get("away_score", 0) or 0)
        inning = float(st["inning"])
        return mlb_bucket(inning, diff, extras=inning > 9.0)
    if s in ("soccer", "soccer_intl"):
        if "elapsed" not in st:
            return None
        diff = None
        if "home_score" in st and "away_score" in st:
            diff = float(st["home_score"]) - float(st["away_score"])
        return soccer_bucket(float(st["elapsed"]), diff)
    return None


def caveat_for(sport: str, ingame_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """{state_bucket, can_price, reason, n_games, model_brier, market_brier} for a
    mapped state, or {state_bucket: None, can_price: False, reason: "UNMAPPED_STATE..."}
    when the sport/state can't be bucketed or has no reliability map yet."""
    key = bucket_for(sport, ingame_state or {})
    if key is None:
        return {"state_bucket": None, "can_price": False,
                "reason": "UNMAPPED_STATE -- no reliability data for this state"}
    doc = load_reliability_map(sport)
    if doc is None:
        return {"state_bucket": key, "can_price": False,
                "reason": "UNMAPPED_STATE -- no reliability map built yet for this sport"}
    row = (doc.get("buckets") or {}).get(key)
    if row is None:
        return {"state_bucket": key, "can_price": False,
                "reason": "UNMAPPED_STATE -- no reliability data for this state"}
    return {
        "state_bucket": key,
        "can_price": bool(row.get("can_price", False)),
        "reason": row.get("reason", "unknown"),
        "n_games": row.get("n_games"),
        "model_brier": row.get("model_brier"),
        "market_brier": row.get("market_brier"),
    }


__all__ = ["load_reliability_map", "bucket_for", "caveat_for"]
