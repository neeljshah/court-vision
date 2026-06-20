"""scripts.platformkit.prop_line_ladder_nba -- per-line-ladder NBA prop calibration.

Validates calibration across the FULL line-offset surface (not just the single
nearest .5 line). For each stat and each integer offset k (e.g. -2..+2 half-steps
from the nearest .5 line), we compute P(over line+offset) vs realized outcomes.

HONEST: CALIBRATION not $; UNITS not $; no roi/pnl/profit keys.
INSUFFICIENT_DATA where n < _MIN_N. Absent parquet -> sentinel. Never raises.

Public API: score_nba_line_ladder, write_ladder_cache, load_ladder_cache.
Cache: data/cache/props_eval_nba_ladder.json

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/test_prop_line_ladder_nba.py -q
"""
from __future__ import annotations

import json
import logging
import math
import os
from typing import Dict, List, Optional, Sequence

from scripts.platformkit.props_eval_nba import (
    NBA_STATS,
    INSUFFICIENT_DATA,
    _SIGMA_FLOOR,
    _per_stat_sigma,
    _nearest_half_line,
    _p_over_gaussian,
)
from scripts.platformkit.props_eval import score_prop_predictions

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
_OOF_PATH = os.path.join("data", "cache", "pregame_oof.parquet")
LADDER_CACHE_PATH = os.path.join("data", "cache", "props_eval_nba_ladder.json")

# Minimum sample PER (stat, offset) cell to report calibration.
_MIN_N = 30

# Half-step offsets from the nearest .5 line to evaluate.
# Offset 0 = the standard nearest-.5 line from props_eval_nba.
# Positive = lines further above pred; Negative = lines further below pred.
# E.g. offset +1 means line_nearest + 0.5; offset -1 means line_nearest - 0.5.
_OFFSETS: List[int] = [-2, -1, 0, 1, 2]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ladder_line(pred: float, offset: int) -> float:
    """Return the ladder line for a given pred and integer offset.

    Base = nearest .5 line to pred (same as props_eval_nba). Then shift by
    offset * 0.5 half-steps. Clamped to >= 0.5.
    """
    base = _nearest_half_line(pred)
    line = base + offset * 0.5
    return max(line, 0.5)


def _build_ladder_preds(rows: List[dict], stat: str,
                        offsets: List[int]) -> Dict[int, List[dict]]:
    """Convert OOF rows for a stat -> {offset: [{p_over, outcome}]}.

    Uses the same Gaussian sigma as props_eval_nba (per_stat_sigma floored at
    _SIGMA_FLOOR). A shared sigma is computed once over all rows (not per-line)
    so the P(over) function is consistent with the existing pricer.
    Never raises; returns {offset: []} on bad input.
    """
    result: Dict[int, List[dict]] = {k: [] for k in offsets}
    if not rows:
        return result
    # Pre-filter to rows with valid numeric pred and actual before sigma calc.
    valid_rows = []
    for r in rows:
        p = r.get("pred")
        a = r.get("actual")
        if p is None or a is None:
            continue
        try:
            pf, af = float(p), float(a)
        except (TypeError, ValueError):
            continue
        if math.isfinite(pf) and math.isfinite(af):
            valid_rows.append({"pred": pf, "actual": af})
    if not valid_rows:
        return result
    sigma = max(_per_stat_sigma(valid_rows), _SIGMA_FLOOR.get(stat, 1.0))
    # valid_rows already contains only finite floats; no re-check needed.
    for r in valid_rows:
        pred_f = r["pred"]
        actual_f = r["actual"]
        for off in offsets:
            line = _ladder_line(pred_f, off)
            p = _p_over_gaussian(pred_f, sigma, line)
            outcome = 1 if actual_f > line else 0
            result[off].append({"p_over": p, "outcome": outcome})
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_nba_line_ladder(
    df=None,
    *,
    oof_path: Optional[str] = None,
    stats: Optional[Sequence[str]] = None,
    offsets: Optional[Sequence[int]] = None,
) -> Dict[str, object]:
    """Per-(stat, offset) NBA prop calibration across the line-offset surface.

    Returns:
      {
        "stats": [...],
        "offsets": [...],
        "per_stat_offset": {
          stat: {
            offset: {n, ece, brier, brier_skill_score, reliability_bins}
                 OR INSUFFICIENT_DATA string
          }
        },
        "note": str
      }

    Absent parquet or n < _MIN_N per cell -> INSUFFICIENT_DATA (never fabricated).
    No $ key anywhere. CALIBRATION only. Never raises.
    """
    use_stats = list(stats) if stats is not None else list(NBA_STATS)
    use_offsets = list(offsets) if offsets is not None else list(_OFFSETS)

    # Empty sentinel
    base: Dict[str, object] = {
        "stats": use_stats,
        "offsets": use_offsets,
        "per_stat_offset": {s: {o: INSUFFICIENT_DATA for o in use_offsets}
                            for s in use_stats},
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
        logger.warning("prop_line_ladder_nba: OOF load failed: %s", exc)
        base["note"] = f"OOF load failed: {exc}"
        return base

    if df is None or len(df) == 0:
        base["note"] = "empty OOF dataframe -> INSUFFICIENT_DATA"
        return base

    required = {"stat", "oof_pred", "actual"}
    if not required.issubset(set(df.columns)):
        missing = required - set(df.columns)
        base["note"] = f"OOF missing columns: {missing}"
        return base

    per_stat_offset: Dict[str, Dict[int, object]] = {}

    for stat in use_stats:
        subset = df[df["stat"] == stat]
        rows: List[dict] = []
        for _, r in subset.iterrows():
            try:
                pv = float(r["oof_pred"])
                av = float(r["actual"])
            except (TypeError, ValueError):
                continue
            if math.isfinite(pv) and math.isfinite(av):
                rows.append({"pred": pv, "actual": av})

        offset_preds = _build_ladder_preds(rows, stat, use_offsets)
        cell_results: Dict[int, object] = {}
        for off in use_offsets:
            preds = offset_preds[off]
            if len(preds) < _MIN_N:
                cell_results[off] = INSUFFICIENT_DATA
            else:
                scored = score_prop_predictions(preds)
                # Keep only the fields needed for the surface (drop log_loss /
                # hit_rate / mean_p / sharpness to keep the payload compact).
                cell_results[off] = {
                    "n": scored.get("n", 0),
                    "ece": scored.get("ece"),
                    "brier": scored.get("brier"),
                    "bss": scored.get("brier_skill_score"),
                    "reliability_bins": scored.get("reliability_bins", []),
                }
        per_stat_offset[stat] = cell_results

    note = (
        "NBA OOF line-ladder: calibration across the full half-step offset surface. "
        "Offset 0 = nearest .5 line (same as props_eval_nba). "
        "Calibration only -- not a $-edge. INSUFFICIENT_DATA where n < %d per cell." % _MIN_N
    )
    return {
        "stats": use_stats,
        "offsets": use_offsets,
        "per_stat_offset": per_stat_offset,
        "note": note,
    }


def write_ladder_cache(
    df=None,
    *,
    oof_path: Optional[str] = None,
    out_path: Optional[str] = None,
    stats: Optional[Sequence[str]] = None,
    offsets: Optional[Sequence[int]] = None,
) -> Dict[str, object]:
    """Run score_nba_line_ladder and write cache JSON atomically.

    Returns payload dict with "written": bool key. Never raises.
    Cache path: data/cache/props_eval_nba_ladder.json.
    """
    from datetime import datetime, timezone

    res = score_nba_line_ladder(df, oof_path=oof_path, stats=stats, offsets=offsets)

    # Serialise: convert int offset keys to strings for JSON.
    per_stat_offset_str: Dict[str, object] = {}
    for stat, cells in ((res or {}).get("per_stat_offset") or {}).items():
        per_stat_offset_str[stat] = {str(k): v for k, v in (cells or {}).items()}

    payload: Dict[str, object] = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "mode": "nba_oof_line_ladder",
        "stats": res.get("stats", []),
        "offsets": res.get("offsets", []),
        "per_stat_offset": per_stat_offset_str,
        "note": res.get("note", ""),
    }

    dest = out_path or LADDER_CACHE_PATH
    written = _write_json(payload, dest)
    payload["written"] = written
    return payload


def load_ladder_cache(path: Optional[str] = None) -> Dict[str, object]:
    """Load ladder cache. Returns {} on absent/unreadable. Never raises."""
    try:
        p = path or LADDER_CACHE_PATH
        if not os.path.exists(p):
            return {}
        with open(p, "r", encoding="ascii") as fh:
            obj = json.load(fh)
        # Validate mode
        if (obj or {}).get("mode") != "nba_oof_line_ladder":
            logger.warning("load_ladder_cache: unexpected mode %r", (obj or {}).get("mode"))
        return obj if isinstance(obj, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("load_ladder_cache failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Internal I/O helper
# ---------------------------------------------------------------------------

def _write_json(payload: Dict[str, object], path: str) -> bool:
    """Atomic JSON write. False on failure; never raises."""
    try:
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="ascii") as fh:
            json.dump(payload, fh, ensure_ascii=True, indent=2, sort_keys=True)
        os.replace(tmp, path)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("prop_line_ladder_nba: write failed: %s", exc)
        return False


__all__ = [
    "NBA_STATS", "INSUFFICIENT_DATA", "LADDER_CACHE_PATH",
    "_MIN_N", "_OFFSETS",
    "score_nba_line_ladder", "write_ladder_cache", "load_ladder_cache",
]
