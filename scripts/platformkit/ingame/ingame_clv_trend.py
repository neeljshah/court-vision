"""scripts.platformkit.ingame.ingame_clv_trend -- multi-batch in-game CLV trend/delta.

Reads clv_series from ingame_clv_aggregate.aggregate, splits into chronological batches,
and answers: is live re-pricing CLV IMPROVING / WORSENING / FLAT / INSUFFICIENT_DATA?

VERDICT: <2 scored batches -> INSUFFICIENT_DATA; monotone non-drop -> IMPROVING; last<first
-> WORSENING; any drop > DELTA_THRESH -> regression_flag True; else -> FLAT.
Measurement-only; probability space; no $ / roi / pnl / profit / bankroll anywhere.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_clv_trend.py -q
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from scripts.platformkit.ingame import ingame_clv_aggregate as agg

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# tunables (all override-able by callers)                                      #
# --------------------------------------------------------------------------- #
BATCH_SIZE: int = 3           # games per batch window
MIN_BATCH_FILL: int = 2       # last (partial) window kept only if >= this many games
MIN_BATCHES: int = 2          # need >= 2 batches for any trend verdict
DELTA_THRESH: float = 0.002   # batch-to-batch drop > this flags regression (probability units)


# --------------------------------------------------------------------------- #
# batch helpers                                                                #
# --------------------------------------------------------------------------- #
def _batch_mean(games: Sequence[Dict[str, Any]]) -> Optional[float]:
    """Mean CLV across a window. None (INSUFFICIENT_DATA) if no ticks in the window."""
    clvs = [float(g["mean_clv"]) for g in games if int(g.get("n_ticks", 0)) > 0]
    return sum(clvs) / len(clvs) if clvs else None


def _split_batches(series: Sequence[Dict[str, Any]], *,
                   batch_size: int = BATCH_SIZE,
                   min_fill: int = MIN_BATCH_FILL) -> List[List[Dict[str, Any]]]:
    """Partition series into non-overlapping windows of batch_size games (chronological).

    The final window is kept only if it holds >= min_fill games (to avoid a
    one-game partial manufacturing a spurious trend direction).
    """
    bs = max(1, batch_size)
    windows: List[List[Dict[str, Any]]] = []
    items = list(series)
    for start in range(0, len(items), bs):
        chunk = items[start:start + bs]
        if len(chunk) < bs:
            # Last (partial) window: include only if it has enough games.
            if len(chunk) >= min_fill:
                windows.append(chunk)
        else:
            windows.append(chunk)
    return windows


def _batch_record(idx: int, games: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a summary record for one batch."""
    mean = _batch_mean(games)
    first_ts = games[0].get("settle_ts", "") if games else ""
    last_ts = games[-1].get("settle_ts", "") if games else ""
    return {
        "batch_idx": idx,
        "n_games": len(games),
        "mean_clv": round(mean, 6) if mean is not None else None,
        "verdict": "INSUFFICIENT_DATA" if mean is None else "SCORED",
        "ts_first": first_ts,
        "ts_last": last_ts,
    }


# --------------------------------------------------------------------------- #
# trend analysis                                                               #
# --------------------------------------------------------------------------- #
def _scored_means(batch_records: Sequence[Dict[str, Any]]) -> List[float]:
    """Extract mean_clv from batches that have a real (non-None) value, in order."""
    return [b["mean_clv"] for b in batch_records if b["mean_clv"] is not None]


def _is_monotone_non_decreasing(values: Sequence[float], *,
                                 delta_thresh: float = DELTA_THRESH) -> bool:
    """True if each step is flat or rising (within tiny noise = no drop > delta_thresh)."""
    for i in range(len(values) - 1):
        if values[i + 1] < values[i] - delta_thresh:
            return False
    return True


def _has_regression(values: Sequence[float], *,
                    delta_thresh: float = DELTA_THRESH) -> bool:
    """True if any consecutive pair shows a drop > delta_thresh."""
    for i in range(len(values) - 1):
        if values[i + 1] < values[i] - delta_thresh:
            return True
    return False


# --------------------------------------------------------------------------- #
# public API                                                                   #
# --------------------------------------------------------------------------- #
def compute_trend(clv_series: Sequence[Dict[str, Any]], *,
                  batch_size: int = BATCH_SIZE,
                  min_fill: int = MIN_BATCH_FILL,
                  min_batches: int = MIN_BATCHES,
                  delta_thresh: float = DELTA_THRESH) -> Dict[str, Any]:
    """Compute multi-batch CLV trend from a clv_series (list of per-game CLV dicts).

    clv_series is the 'clv_series' field from ingame_clv_aggregate.aggregate -- each
    element has {game_id, settle_ts, mean_clv, n_ticks}. Input must be pre-sorted by
    settle_ts (aggregate guarantees this).

    Returns a dict with:
      verdict         : IMPROVING | WORSENING | FLAT | INSUFFICIENT_DATA
      monotone_improving: bool (True only when verdict == IMPROVING)
      regression_flag : bool (True when any batch-to-batch drop > delta_thresh)
      n_batches       : int (total windows including INSUFFICIENT_DATA ones)
      n_scored_batches: int (batches with a real CLV value)
      batches         : List[batch_record] (batch_idx, mean_clv, n_games, verdict, ts range)
      delta_series    : List[float] (batch-to-batch CLV deltas; empty if <2 scored batches)
      units           : "probability"
      edge_claimed    : False

    Never raises.
    """
    try:
        return _compute_trend_inner(list(clv_series),
                                    batch_size=batch_size,
                                    min_fill=min_fill,
                                    min_batches=min_batches,
                                    delta_thresh=delta_thresh)
    except Exception as exc:  # noqa: BLE001
        logger.warning("compute_trend failed unexpectedly: %s", exc)
        return _insufficient("error: %s" % type(exc).__name__)


def _insufficient(reason: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "verdict": "INSUFFICIENT_DATA",
        "monotone_improving": False,
        "regression_flag": False,
        "n_batches": 0,
        "n_scored_batches": 0,
        "batches": [],
        "delta_series": [],
        "units": "probability",
        "edge_claimed": False,
        "label": "measurement only -- in-game CLV trend, probability space, no currency",
    }
    if reason:
        out["reason"] = reason
    return out


def _compute_trend_inner(series: List[Dict[str, Any]], *,
                         batch_size: int,
                         min_fill: int,
                         min_batches: int,
                         delta_thresh: float) -> Dict[str, Any]:
    windows = _split_batches(series, batch_size=batch_size, min_fill=min_fill)
    batch_records = [_batch_record(i, w) for i, w in enumerate(windows)]
    n_batches = len(batch_records)
    scored_means = _scored_means(batch_records)
    n_scored = len(scored_means)

    deltas: List[float] = [
        round(scored_means[i + 1] - scored_means[i], 6)
        for i in range(n_scored - 1)
    ]

    if n_scored < min_batches:
        out = _insufficient("n_scored_batches=%d < min_batches=%d" % (n_scored, min_batches))
        out["n_batches"] = n_batches
        out["n_scored_batches"] = n_scored
        out["batches"] = batch_records
        out["delta_series"] = deltas
        return out

    reg = _has_regression(scored_means, delta_thresh=delta_thresh)
    improving = _is_monotone_non_decreasing(scored_means, delta_thresh=delta_thresh)
    first_mean = scored_means[0]
    last_mean = scored_means[-1]

    if improving and last_mean > first_mean:
        verdict = "IMPROVING"
    elif last_mean < first_mean:
        verdict = "WORSENING"
    else:
        verdict = "FLAT"

    return {
        "verdict": verdict,
        "monotone_improving": improving and verdict == "IMPROVING",
        "regression_flag": reg,
        "n_batches": n_batches,
        "n_scored_batches": n_scored,
        "batches": batch_records,
        "delta_series": deltas,
        "first_batch_mean_clv": round(first_mean, 6),
        "last_batch_mean_clv": round(last_mean, 6),
        "cumulative_delta": round(last_mean - first_mean, 6),
        "units": "probability",
        "edge_claimed": False,
        "label": "measurement only -- in-game CLV trend, probability space, no currency",
    }


def trend_from_aggregate(grade_dir: Optional[Path] = None, *,
                         sport: Optional[str] = None,
                         paths: Optional[Sequence[Path]] = None,
                         batch_size: int = BATCH_SIZE,
                         min_fill: int = MIN_BATCH_FILL,
                         min_batches: int = MIN_BATCHES,
                         delta_thresh: float = DELTA_THRESH,
                         agg_min_games: int = agg.MIN_GAMES,
                         agg_min_total_ticks: int = agg.MIN_TOTAL_TICKS) -> Dict[str, Any]:
    """One-call entry point: aggregate + trend in one step. NEVER raises.

    Calls ingame_clv_aggregate.aggregate to build the per-game CLV series, then
    compute_trend on top. The aggregate verdict (BEAT/BEHIND/MATCH/INSUFFICIENT_DATA)
    is preserved in agg_verdict for the caller.
    """
    try:
        agg_result = agg.aggregate(
            grade_dir=grade_dir, sport=sport, paths=paths,
            min_games=agg_min_games, min_total_ticks=agg_min_total_ticks,
        )
        clv_series = agg_result.get("clv_series", [])
        trend = compute_trend(
            clv_series,
            batch_size=batch_size, min_fill=min_fill,
            min_batches=min_batches, delta_thresh=delta_thresh,
        )
        trend["agg_verdict"] = agg_result.get("verdict", "INSUFFICIENT_DATA")
        trend["agg_n_games"] = agg_result.get("n_games", 0)
        trend["agg_pooled_mean_clv"] = agg_result.get("pooled_mean_clv", 0.0)
        return trend
    except Exception as exc:  # noqa: BLE001
        logger.warning("trend_from_aggregate failed: %s", exc)
        return _insufficient("error: %s" % type(exc).__name__)


def format_trend_report(result: Dict[str, Any]) -> str:
    """ASCII summary of the trend result. No $ anywhere."""
    lines = [
        "=== Multi-batch in-game CLV trend (honest) ===",
        "verdict           : %s" % result.get("verdict", "INSUFFICIENT_DATA"),
        "monotone_improving: %s" % result.get("monotone_improving", False),
        "regression_flag   : %s" % result.get("regression_flag", False),
        "n_batches         : %d  (%d scored)"
        % (result.get("n_batches", 0), result.get("n_scored_batches", 0)),
    ]
    if "first_batch_mean_clv" in result:
        lines += [
            "first_batch_clv   : %+.5f" % result["first_batch_mean_clv"],
            "last_batch_clv    : %+.5f" % result["last_batch_mean_clv"],
            "cumulative_delta  : %+.5f" % result.get("cumulative_delta", 0.0),
        ]
    deltas = result.get("delta_series", [])
    if deltas:
        lines.append("delta_series      : %s" % ["%+.5f" % d for d in deltas])
    if result.get("agg_verdict"):
        lines.append("agg_verdict       : %s  (pooled mean_clv %+.5f over %d games)"
                     % (result["agg_verdict"],
                        result.get("agg_pooled_mean_clv", 0.0),
                        result.get("agg_n_games", 0)))
    lines += [
        "units             : probability (CLV -- calibration only, never dollars)",
        "edge_claimed      : False",
    ]
    return "\n".join(lines)


__all__ = [
    "BATCH_SIZE", "MIN_BATCH_FILL", "MIN_BATCHES", "DELTA_THRESH",
    "compute_trend", "trend_from_aggregate", "format_trend_report",
]
