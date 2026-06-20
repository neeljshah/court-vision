"""scripts.platformkit.props_eval_nba -- per-stat NBA prop calibration from OOF.

Calibration (NOT $-edge): does model P(over line) match realized outcomes?
Source: data/cache/pregame_oof.parquet (leak-free walk-forward OOF rows).
Cache -> data/cache/props_eval_nba_calibration.json; CLI -> props_eval_nba_cli.py.

Public API: score_nba_oof, write_nba_calibration_cache, load_nba_calibration.
Absent parquet or n < _MIN_N -> INSUFFICIENT_DATA sentinel, never fabricated.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_props_eval_nba.py -q
"""
from __future__ import annotations

import json
import logging
import math
import os
from typing import Dict, List, Optional, Sequence

from scripts.platformkit.props_eval import score_prop_predictions
from scripts.platformkit import prop_tiering

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_OOF_PATH = os.path.join("data", "cache", "pregame_oof.parquet")
NBA_CALIBRATION_PATH = os.path.join("data", "cache", "props_eval_nba_calibration.json")

# NBA stats present in the OOF parquet
NBA_STATS = ["pts", "reb", "ast", "stl", "blk", "fg3m", "tov"]

# Minimum sample to report calibration (avoid tiny-N noise -> INSUFFICIENT_DATA)
_MIN_N = 30

# Per-stat Gaussian sigma floors (match player_props.py _SIGMA_FLOOR exactly so
# the P(over) we score matches what the pricer would serve live)
_SIGMA_FLOOR: Dict[str, float] = {
    "pts": 4.0, "reb": 2.0, "ast": 1.5, "stl": 1.0,
    "blk": 1.0, "fg3m": 1.0, "tov": 1.2,
}

INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _phi(z: float) -> float:
    """Standard-normal CDF via erf (stdlib only)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _nearest_half_line(pred: float) -> float:
    """Nearest .5 line to oof_pred, clamped >=0.5 (same logic as props_eval.py)."""
    if not math.isfinite(pred) or pred < 0:
        return 0.5
    line = round(pred - 0.5) + 0.5
    return max(line, 0.5)


def _p_over_gaussian(pred: float, sigma: float, line: float) -> float:
    """P(actual > line) under Gaussian(pred, sigma). Clipped to (0, 1)."""
    if sigma <= 0 or not math.isfinite(pred):
        return 0.5
    z = (line - pred) / sigma
    p = 1.0 - _phi(z)
    return float(min(1.0, max(0.0, p)))


def _per_stat_sigma(rows: List[dict]) -> float:
    """Residual std from the OOF predictions for a stat (sample std)."""
    diffs = [r["actual"] - r["pred"] for r in rows
             if math.isfinite(r["actual"]) and math.isfinite(r["pred"])]
    n = len(diffs)
    if n < 2:
        return 1.0
    mean_d = sum(diffs) / n
    var = sum((d - mean_d) ** 2 for d in diffs) / (n - 1)
    return math.sqrt(max(var, 1e-6))


def _build_preds_for_stat(rows: List[dict], stat: str) -> List[dict]:
    """Convert OOF rows for a stat -> [{p_over, outcome}] for score_prop_predictions."""
    if not rows:
        return []
    sigma = max(_per_stat_sigma(rows), _SIGMA_FLOOR.get(stat, 1.0))
    preds: List[dict] = []
    for r in rows:
        pred = r.get("pred")
        actual = r.get("actual")
        if pred is None or actual is None:
            continue
        if not (math.isfinite(float(pred)) and math.isfinite(float(actual))):
            continue
        pred_f = float(pred)
        actual_f = float(actual)
        line = _nearest_half_line(pred_f)
        p = _p_over_gaussian(pred_f, sigma, line)
        outcome = 1 if actual_f > line else 0
        preds.append({"p_over": p, "outcome": outcome})
    return preds


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_nba_oof(
    df=None,
    *,
    oof_path: Optional[str] = None,
    stats: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    """Per-stat NBA OOF calibration scores.

    Returns {
      "stats": [...], "per_stat": {stat: {n, brier, bss, ece, ...} or INSUFFICIENT_DATA},
      "overall": {...}, "note": str
    }.

    Absent parquet or empty input -> per_stat entries are INSUFFICIENT_DATA strings,
    overall n=0. Never raises. CALIBRATION not $.
    """
    use_stats = list(stats) if stats else list(NBA_STATS)
    _empty_stat = INSUFFICIENT_DATA

    base = {
        "stats": use_stats,
        "per_stat": {s: _empty_stat for s in use_stats},
        "overall": score_prop_predictions([]),
        "note": "",
    }

    # Load OOF parquet
    try:
        import pandas as pd
        path = oof_path or _OOF_PATH
        if df is None:
            if not os.path.exists(path):
                base["note"] = "pregame_oof.parquet absent -> INSUFFICIENT_DATA"
                return base
            df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("props_eval_nba: OOF load failed: %s", exc)
        base["note"] = f"OOF load failed: {exc}"
        return base

    if df is None or len(df) == 0:
        base["note"] = "empty OOF dataframe -> INSUFFICIENT_DATA"
        return base

    # Validate required columns
    required = {"stat", "oof_pred", "actual"}
    if not required.issubset(set(df.columns)):
        missing = required - set(df.columns)
        base["note"] = f"OOF missing columns: {missing}"
        return base

    all_preds: List[dict] = []
    per_stat: Dict[str, object] = {}

    for stat in use_stats:
        subset = df[df["stat"] == stat]
        rows: List[dict] = []
        for _, r in subset.iterrows():
            if r["oof_pred"] is None or r["actual"] is None:
                continue
            try:
                rows.append({"pred": float(r["oof_pred"]), "actual": float(r["actual"])})
            except (TypeError, ValueError):
                logger.debug("props_eval_nba: skipping non-coercible row for %s", stat)
                continue
        preds = _build_preds_for_stat(rows, stat)

        if len(preds) < _MIN_N:
            per_stat[stat] = INSUFFICIENT_DATA
        else:
            scored = score_prop_predictions(preds)
            per_stat[stat] = scored
            all_preds.extend(preds)

    overall = score_prop_predictions(all_preds) if all_preds else score_prop_predictions([])
    note = (
        "NBA OOF calibration: leak-free walk-forward OOF predictions -> per-stat "
        "Brier/BSS/ECE. Calibration only -- not a $-edge. AST expected proven; "
        "others likely marginal/weak. INSUFFICIENT_DATA where n < %d." % _MIN_N
    )
    return {"stats": use_stats, "per_stat": per_stat, "overall": overall, "note": note}


def write_nba_calibration_cache(
    df=None,
    *,
    oof_path: Optional[str] = None,
    out_path: Optional[str] = None,
    stats: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    """Run score_nba_oof and write via prop_tiering.write_calibration_cache_json.

    Returns the payload dict with a "written": bool key. Never raises.
    Cache path: data/cache/props_eval_nba_calibration.json (NBA-specific; disjoint
    from the soccer cache so the two boards never overwrite each other).
    ``stats`` optionally restricts which stats to score (forwarded to score_nba_oof).
    """
    res = score_nba_oof(df, oof_path=oof_path, stats=stats)
    payload = _build_nba_cache_payload(res)
    dest = out_path or NBA_CALIBRATION_PATH
    written = prop_tiering.write_calibration_cache_json(payload, dest)
    payload["written"] = written
    return payload


def load_nba_calibration(path: Optional[str] = None) -> Dict[str, object]:
    """Load NBA calibration from cache. {} on absent/unreadable. Never raises.

    Uses a direct JSON load (bypassing the soccer settle-logic staleness guard
    in prop_tiering.load_calibration) because NBA has no soccer settlement version.
    The returned dict has the same shape {stat: {bss, n, brier, ece}} so callers
    can feed it to prop_tiering.classify directly.
    """
    try:
        p = path or NBA_CALIBRATION_PATH
        if not os.path.exists(p):
            return {}
        with open(p, "r", encoding="ascii") as fh:
            payload = json.load(fh)
        per_stat = (payload or {}).get("per_stat")
        if not isinstance(per_stat, dict):
            return {}
        # Validate mode: refuse to load soccer cache as NBA cache
        mode = (payload or {}).get("mode", "")
        if mode and "nba" not in mode.lower() and "soccer" in mode.lower():
            logger.warning(
                "load_nba_calibration: refusing soccer cache (mode=%r) at %s", mode, p)
            return {}
        out: Dict[str, object] = {}
        for stat, d in per_stat.items():
            if isinstance(d, dict):
                out[stat] = dict(d)
        return out
    except Exception as exc:  # noqa: BLE001 -- never raise
        logger.warning("load_nba_calibration failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Internal cache builder
# ---------------------------------------------------------------------------

def _build_nba_cache_payload(res: Dict[str, object]) -> Dict[str, object]:
    """Slim score_nba_oof result into the cache JSON structure."""
    from datetime import datetime, timezone

    per_stat_out: Dict[str, object] = {}
    for stat, d in ((res or {}).get("per_stat") or {}).items():
        if not isinstance(d, dict):
            # INSUFFICIENT_DATA sentinel -- exclude from cache (load_calibration
            # returns {} for absent keys, so the board falls back to "unmeasured")
            continue
        n = d.get("n", 0)
        if n == 0:
            continue
        per_stat_out[stat] = {
            "bss": d.get("brier_skill_score"),
            "brier": d.get("brier"),
            "ece": d.get("ece"),
            "n": n,
        }

    ov = (res or {}).get("overall") or {}
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "settle_logic_version": None,  # NBA OOF has no settle version stamp
        "mode": "nba_oof_walk_forward",
        "overall": {
            "bss": ov.get("brier_skill_score"),
            "brier": ov.get("brier"),
            "ece": ov.get("ece"),
            "n": ov.get("n", 0),
        },
        "per_stat": per_stat_out,
        "note": (res or {}).get("note", ""),
    }


__all__ = [
    "NBA_STATS", "NBA_CALIBRATION_PATH", "INSUFFICIENT_DATA",
    "score_nba_oof", "write_nba_calibration_cache", "load_nba_calibration",
]
