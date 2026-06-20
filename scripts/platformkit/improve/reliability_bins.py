r"""scripts.platformkit.improve.reliability_bins -- per-market calibration curve emitter.

Computes binned reliability data (mean_pred, observed_freq, n_per_bin) per market
segment using the SAME bin convention as eval_gate.scoring.ece (equal-width
[lo,hi) with the last bin inclusive on both ends: [lo,hi]).

Output block is keyed by (market, ts) and carries a calibration!=edge note.
Thin bins (below MIN_BIN_N) are left as-is but flagged; empty bins are omitted.
If EVERY bin for a market is thin the whole block is INSUFFICIENT_DATA.

CONTRACT:
  - Read-only: never writes to disk; callers own persistence.
  - No dollar field: no key matching /(\$|roi|pnl|profit|edge)/ in any block.
  - INSUFFICIENT_DATA when all bins thin (no fabricated curve).
  - bins follow scoring.ece convention: 10 equal-width buckets, [lo,hi), last inclusive.
  - calibration != edge note in every block.
  - Never raises; errors returned as status=INSUFFICIENT_DATA with a reason field.

Usage:
  from scripts.platformkit.improve.reliability_bins import reliability_block
  block = reliability_block(market="nba:moneyline", rows=settled_rows, ts=ts)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from scripts.platformkit.eval_gate import scoring as S

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BINS: int = 10
"""Number of equal-width bins -- must match eval_gate.scoring.ece default."""

MIN_BIN_N: int = 5
"""Minimum observations per bin to call that bin reliable."""

MIN_MARKET_N: int = 30
"""Minimum settled rows per market; below -> INSUFFICIENT_DATA."""

CALIBRATION_NOTE: str = (
    "calibration != edge: better-calibrated probabilities do NOT imply "
    "beating the market close or a positive expected value"
)

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit|edge)", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _all_keys(obj: Any) -> List[str]:
    """Recursively collect all dict keys."""
    keys: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys(item))
    return keys


def _assert_no_banned_keys(block: Dict[str, Any]) -> None:
    for k in _all_keys(block):
        if _BANNED_KEY_RE.search(k):
            raise ValueError(
                f"Banned key '{k}' in reliability block violates no-dollar-field contract."
            )


# ---------------------------------------------------------------------------
# Core bin computation (mirrors scoring.ece bin edges exactly)
# ---------------------------------------------------------------------------


def _compute_bins(
    p: np.ndarray,
    y: np.ndarray,
    bins: int,
) -> List[Dict[str, Any]]:
    """Compute per-bin (mean_pred, observed_freq, n_per_bin) matching ece convention.

    Bin edges: np.linspace(0, 1, bins+1).
    Intervals: [lo, hi) for k < bins-1; [lo, hi] for the last bin (k == bins-1).
    Empty bins are omitted from output.
    """
    edges = np.linspace(0.0, 1.0, bins + 1)
    result: List[Dict[str, Any]] = []
    for k in range(bins):
        lo = float(edges[k])
        hi = float(edges[k + 1])
        if k < bins - 1:
            mask = (p >= lo) & (p < hi)
        else:
            mask = (p >= lo) & (p <= hi)
        n_k = int(mask.sum())
        if n_k == 0:
            continue
        mean_pred = float(p[mask].mean())
        obs_freq = float(y[mask].mean())
        bin_entry: Dict[str, Any] = {
            "bin_lo": round(lo, 4),
            "bin_hi": round(hi, 4),
            "mean_pred": round(mean_pred, 6),
            "observed_freq": round(obs_freq, 6),
            "n_per_bin": n_k,
            "thin": n_k < MIN_BIN_N,
        }
        result.append(bin_entry)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reliability_block(
    market: str,
    rows: Sequence[Dict[str, Any]],
    ts: Optional[str] = None,
    bins: int = DEFAULT_BINS,
) -> Dict[str, Any]:
    """Compute a reliability (calibration-curve) block for one market segment.

    Parameters
    ----------
    market:
        Market key, e.g. "nba:moneyline".
    rows:
        Settled rows, each must have p_raw (float in [0,1]) and y (0 or 1).
    ts:
        ISO timestamp string; defaults to now (UTC).
    bins:
        Bin count -- must match eval_gate.scoring.ece convention (default 10).

    Returns
    -------
    Dict with status in {"OK", "INSUFFICIENT_DATA"}.
    OK blocks carry a "curve" list of bin dicts.
    INSUFFICIENT_DATA blocks carry a "reason" field and no curve.
    All blocks carry market, ts, note, n, min_n, n_bins.
    Never raises; errors -> INSUFFICIENT_DATA with a reason.
    """
    ts = ts or _now_iso()
    base: Dict[str, Any] = {
        "market": market,
        "ts": ts,
        "n": len(rows),
        "min_n": MIN_MARKET_N,
        "n_bins": bins,
        "min_bin_n": MIN_BIN_N,
        "note": CALIBRATION_NOTE,
    }
    try:
        n = len(rows)
        if n < MIN_MARKET_N:
            block = {
                **base,
                "status": "INSUFFICIENT_DATA",
                "reason": (
                    f"only {n} settled rows for market '{market}'; "
                    f"need >= {MIN_MARKET_N} for a reliability curve. "
                    "No calibration claimed."
                ),
            }
            _assert_no_banned_keys(block)
            return block

        p = np.array([float(r["p_raw"]) for r in rows], dtype=float)
        y = np.array([float(r["y"]) for r in rows], dtype=float)

        bin_entries = _compute_bins(p, y, bins)

        # If every non-empty bin is thin -> INSUFFICIENT_DATA (no fabricated curve)
        non_empty = bin_entries  # empty bins already omitted
        all_thin = len(non_empty) > 0 and all(b["thin"] for b in non_empty)
        if len(non_empty) == 0:
            block = {
                **base,
                "status": "INSUFFICIENT_DATA",
                "reason": "all bins empty after filtering -- cannot draw a curve",
            }
            _assert_no_banned_keys(block)
            return block

        if all_thin:
            block = {
                **base,
                "status": "INSUFFICIENT_DATA",
                "reason": (
                    f"all non-empty bins have < {MIN_BIN_N} observations; "
                    "no reliable curve. No calibration claimed."
                ),
            }
            _assert_no_banned_keys(block)
            return block

        # Compute scalar ECE for reference (matches scoring.ece exactly)
        raw_ece = round(float(S.ece(p, y, bins)), 6)

        block = {
            **base,
            "status": "OK",
            "raw_ece": raw_ece,
            "curve": bin_entries,
            "n_bins_populated": len(bin_entries),
            "n_bins_thin": sum(1 for b in bin_entries if b["thin"]),
        }
        _assert_no_banned_keys(block)
        return block

    except Exception as exc:  # never raises; degrade to INSUFFICIENT_DATA
        block = {
            **base,
            "status": "INSUFFICIENT_DATA",
            "reason": f"internal error: {exc!s}",
        }
        # Best-effort banned-key check -- if it raises, swallow and return plain block
        try:
            _assert_no_banned_keys(block)
        except ValueError:
            pass
        return block


def reliability_blocks_for_segments(
    segments: Dict[str, List[Dict[str, Any]]],
    ts: Optional[str] = None,
    bins: int = DEFAULT_BINS,
) -> Dict[str, Dict[str, Any]]:
    """Compute reliability blocks for multiple market segments at once.

    Parameters
    ----------
    segments:
        Output of per_market_ledger.segment_by_market (market -> list of rows).
    ts:
        Shared ISO timestamp (defaults to now UTC).

    Returns
    -------
    Dict mapping market key -> reliability block.
    """
    ts = ts or _now_iso()
    out: Dict[str, Dict[str, Any]] = {}
    for market, rows in segments.items():
        out[market] = reliability_block(market, rows, ts=ts, bins=bins)
    return out


__all__ = [
    "reliability_block",
    "reliability_blocks_for_segments",
    "DEFAULT_BINS",
    "MIN_BIN_N",
    "MIN_MARKET_N",
    "CALIBRATION_NOTE",
]
