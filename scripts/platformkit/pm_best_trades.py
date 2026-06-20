"""scripts.platformkit.pm_best_trades -- "best trades it would have made" + CLV grade.

Ranks historical paper trades by calibrated divergence (model_prob vs market-implied
probability) joined to their CLV grade from the CLV ledger.

HONESTY CONTRACT (binding):
  * divergence = model_prob - market_implied_prob (always positive when model agrees
    with the direction of the taken side).
  * grade_available = True ONLY when status=settled AND clv_status=true_close
    (settled on a real, devigged closing line -- not a proxy).
  * pct_beat_close is computed from real CLV rows only (grade_available=True);
    None when no such rows exist.
  * Proxy CLV (clv_is_proxy=True): clv_pct reported as 0.0 (honest zero, not
    fabricated signal) and grade_available=False.
  * No $ / dollar / roi / profit / pnl field on any row or summary.
  * executed always False (paper only).
  * NEVER mutates the append-only ledger.
  * <=300 LOC; ASCII only; no secrets; no network.

Build-on:
  pm_trail_browse.best_pm_trades  -- PM-only venue filter (reference pattern)
  clv_ledger.load_ledger          -- raw JSONL rows
  clv_ledger.clv_summary          -- aggregate CLV stats
  clv_ledger_enrich.enrich_rows   -- tier/venue/flat_unit gap-fill
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.clv_ledger import load_ledger, clv_summary
from scripts.platformkit.clv_ledger_enrich import enrich_rows

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HONEST_NOTE = (
    "Best trades ranked by calibrated divergence (model_prob - market_implied_prob). "
    "grade_available=True only on settled rows with a real devigged true_close. "
    "Proxy CLV reported as 0.0 (not fabricated signal). "
    "No $ edge claimed. executed=False (paper only)."
)

_TIER_RANK: Dict[Optional[str], int] = {"A": 0, "B": 1, "C": 2, None: 3}

_DEFAULT_LEDGER = (
    Path(__file__).resolve().parents[2] / "data" / "frontend" / "clv_ledger.jsonl"
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _market_implied_prob(taken_decimal: Optional[float]) -> Optional[float]:
    """Return 1/taken_decimal (market-implied probability), or None if invalid."""
    if taken_decimal is None:
        return None
    try:
        d = float(taken_decimal)
        if d > 1.0:
            return 1.0 / d
    except (TypeError, ValueError):
        pass
    return None


def _divergence(row: Dict[str, Any]) -> Optional[float]:
    """Compute model_prob minus market_implied_prob for one enriched row.

    Positive divergence = model is MORE confident than the market on this side.
    Returns None when either component is unavailable.
    """
    model_prob = row.get("model_prob")
    if model_prob is None:
        return None
    try:
        mp = float(model_prob)
    except (TypeError, ValueError):
        return None
    mip = _market_implied_prob(row.get("taken_decimal"))
    if mip is None:
        return None
    return round(mp - mip, 6)


def _grade_available(row: Dict[str, Any]) -> bool:
    """True only when settled on a REAL devigged true-close (not proxy, not no_close)."""
    if str(row.get("status", "")).lower() != "settled":
        return False
    clv_status = str(row.get("clv_status") or "").lower()
    if clv_status != "true_close":
        return False
    # Double-check: proxy flag must not be set
    if bool(row.get("clv_is_proxy", False)):
        return False
    # Must have an actual non-null clv_pct
    return row.get("clv_pct") is not None


def _clv_pct_honest(row: Dict[str, Any]) -> Optional[float]:
    """Return CLV pct honestly.

    Proxy CLV -> 0.0 (honest zero, not signal).
    True-close CLV -> actual value.
    No close at all -> None (INSUFFICIENT_DATA).
    """
    if bool(row.get("clv_is_proxy", False)):
        return 0.0
    raw = row.get("clv_pct")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _sort_key(div: Optional[float], tier: Optional[str],
              model_prob: Optional[float]) -> tuple:
    """Sort key: divergence desc, tier rank asc, model_prob desc."""
    d = -(div if div is not None else -999.0)
    t = _TIER_RANK.get(str(tier).upper() if tier else None, 3)
    mp = -(float(model_prob) if model_prob is not None else 0.0)
    return (d, t, mp)


def _shape_row(row: Dict[str, Any], div: Optional[float]) -> Dict[str, Any]:
    """Shape one enriched ledger row for best-trades output.

    No $ / dollar / roi / profit / pnl field is ever included.
    """
    ga = _grade_available(row)
    clv_val = _clv_pct_honest(row)
    tier = row.get("tier")
    return {
        "bet_id": row.get("bet_id"),
        "ts": row.get("ts"),
        "settled_at": row.get("settled_at"),
        "sport": row.get("sport"),
        "matchup": row.get("matchup"),
        "side": row.get("side"),
        "market_type": row.get("market_type") or row.get("market"),
        "venue": row.get("venue", "unknown"),
        "taken_book": row.get("taken_book"),
        "taken_decimal": row.get("taken_decimal"),
        "market_implied_prob": _market_implied_prob(row.get("taken_decimal")),
        "model_prob": row.get("model_prob"),
        "divergence": div,
        "tier": tier,
        "flat_unit": row.get("flat_unit"),
        "stake_units": row.get("stake_units") or row.get("stake"),
        "status": row.get("status", "open"),
        "outcome": row.get("outcome"),
        "grade_available": ga,
        "clv_pct": clv_val if ga else (0.0 if bool(row.get("clv_is_proxy", False)) else None),
        "beat_close": row.get("beat_close") if ga else None,
        "clv_status": row.get("clv_status"),
        "clv_is_proxy": bool(row.get("clv_is_proxy", False)),
        "executed": False,
    }


def _compute_pct_beat_close(
    shaped_rows: List[Dict[str, Any]]
) -> Optional[float]:
    """Fraction of grade_available rows where beat_close is True.

    Returns None (INSUFFICIENT_DATA) when no grade_available rows exist.
    """
    graded = [r for r in shaped_rows if r.get("grade_available")]
    if not graded:
        return None
    beats = sum(1 for r in graded if r.get("beat_close") is True)
    return round(100.0 * beats / len(graded), 4)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def best_trades(
    ledger_path: Optional[Path] = None,
    *,
    top_n: int = 20,
    min_divergence: Optional[float] = None,
    sport: Optional[str] = None,
    settled_only: bool = False,
) -> Dict[str, Any]:
    """Rank historical paper trades by calibrated divergence + CLV grade.

    Returns top_n trades sorted by divergence (model vs market) descending,
    then by tier (A>B>C>None), then model_prob descending.

    grade_available is True only on true-close settled rows.
    pct_beat_close is computed from real CLV (None = INSUFFICIENT_DATA).
    No $ / pnl / profit field anywhere.

    Args:
        ledger_path: Override path to clv_ledger.jsonl (default = data/frontend/).
        top_n:       Max rows to return (1..500).
        min_divergence: Optional floor on divergence to filter noisy rows.
        sport:       Optional sport filter ("nba", "mlb", "soccer", "tennis").
        settled_only: If True, only include rows with status=settled.
    """
    top_n = min(max(1, top_n), 500)

    raw = load_ledger(ledger_path)
    enriched = enrich_rows(raw)

    # Apply filters
    if sport:
        s = sport.lower()
        enriched = [r for r in enriched if str(r.get("sport") or "").lower() == s]
    if settled_only:
        enriched = [r for r in enriched if r.get("status") == "settled"]

    # Compute divergence for every row
    with_div: List[tuple] = []
    for row in enriched:
        div = _divergence(row)
        if min_divergence is not None and (div is None or div < min_divergence):
            continue
        with_div.append((row, div))

    # Sort by divergence desc, tier, model_prob desc
    with_div.sort(
        key=lambda pair: _sort_key(
            pair[1],
            pair[0].get("tier"),
            pair[0].get("model_prob"),
        )
    )

    top_pairs = with_div[:top_n]
    shaped = [_shape_row(row, div) for row, div in top_pairs]
    pct_beat = _compute_pct_beat_close(shaped)

    # Summary from real CLV ledger (aggregate)
    summary = clv_summary(raw)

    return {
        "status": "ok",
        "count": len(shaped),
        "top_n": top_n,
        "trades": shaped,
        "pct_beat_close": pct_beat,
        "grade_available_n": sum(1 for r in shaped if r.get("grade_available")),
        "clv_summary": summary,
        "honest_note": _HONEST_NOTE,
    }


__all__ = ["best_trades"]
