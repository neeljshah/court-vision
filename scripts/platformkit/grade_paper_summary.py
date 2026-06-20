"""scripts.platformkit.grade_paper_summary -- UNITS-ONLY scoreboard over graded rows.

Split out of grade_paper.py to keep each file <=300 LOC. This module owns the pure
summary math: per-bucket hit-rate, UNIT record (never dollars), and CLV stats, plus
the top-level grade_summary() that buckets by sport and market.

HONESTY (binding): UNITS ONLY. There is NO dollar pnl / total_pnl / total_stake /
paper_roi field anywhere here -- ``unit_result`` is a pure unit count at the taken
price. Void rows are excluded from the decided sample and surfaced separately so a
missing result never inflates a win. CLV (better-number-than-close) is the yardstick.

INVARIANTS: build only under scripts/platformkit/; <=300 LOC; ASCII; no secrets;
no $-edge claim.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/test_grade_paper_summary.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit import clv_ledger as _clv


def row_market(row: Dict[str, Any]) -> str:
    """Market label for a row: explicit market/market_type, else 'moneyline'.

    A team bet that carries no market field is moneyline by construction (the only
    team market this engine records); we read the stored field when present rather
    than silently overriding a real spread/total label.
    """
    return str(row.get("market") or row.get("market_type") or "moneyline")


def grade_bucket(rows_in: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Hit-rate / UNIT-record / CLV stats over a set of graded rows. Pure.

    UNITS ONLY -- there is NO dollar pnl / roi / stake field. ``unit_result`` is a
    pure unit count at the taken price (never money). Void rows are excluded from
    the decided sample and surfaced separately so a missing result never inflates a
    win. Each denominator is stated explicitly (n_total / n_decided / n_with_clv).
    """
    void = [r for r in rows_in if r.get("outcome") == "void"]
    dec = [r for r in rows_in if r.get("outcome") in ("win", "loss")]
    w = sum(1 for r in dec if r.get("outcome") == "win")
    units = [float(r["unit_result"]) for r in rows_in
             if r.get("unit_result") is not None]
    cv = [float(r["clv_pct"]) for r in rows_in if r.get("clv_pct") is not None]
    return {
        "n_total": len(rows_in),
        "n_void": len(void),
        "n_decided": len(dec),
        "n_wins": w,
        "n_losses": len(dec) - w,
        "hit_rate": round(100.0 * w / len(dec), 4) if dec else None,
        # unit record at the taken price -- units, not dollars; never an ROI %.
        "net_units": round(sum(units), 6) if units else None,
        "n_priced_units": len(units),
        "n_with_clv": len(cv),
        "mean_clv_pct": round(sum(cv) / len(cv), 6) if cv else None,
        "pct_beat_close": (round(100.0 * sum(1 for c in cv if c > 0) / len(cv), 4)
                           if cv else None),
    }


def grade_summary(ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """Honest scoreboard over GRADED rows (graded=True): hit-rate, UNIT record, CLV,
    %-beat-close, by sport + market. UNITS ONLY -- no dollar pnl / roi / stake."""
    target = Path(ledger_path) if ledger_path else _clv.DEFAULT_LEDGER
    rows = [r for r in _clv.load_ledger(target) if r.get("graded")]
    if not rows:
        return {"n_total": 0, "hit_rate": None, "net_units": None,
                "mean_clv_pct": None, "pct_beat_close": None,
                "by_sport": {}, "by_market": {}}
    out = dict(grade_bucket(rows))
    out["by_sport"] = {
        sp: grade_bucket([r for r in rows if str(r.get("sport")) == sp])
        for sp in sorted({str(r.get("sport", "unknown")) for r in rows})}
    out["by_market"] = {
        mk: grade_bucket([r for r in rows if row_market(r) == mk])
        for mk in sorted({row_market(r) for r in rows})}
    out["honest_note"] = (
        "Paper track record, UNITS ONLY (no $ / pnl / roi). The unit record is "
        "small-N paper, a hypothesis to forward-test -- NOT a proven edge. CLV "
        "(better-number-than-close) is the yardstick.")
    return out


__all__ = ["row_market", "grade_bucket", "grade_summary"]
