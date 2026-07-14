"""scripts.platformkit.live_edge.shadow.shadow_ledger -- LIVE-EDGE D1 shadow
prediction ledger + CLV grader.

Append-only rows via the shared io_atomic helper (reused, not reinvented) to
data/omni/live_edge/shadow/<date>.jsonl -- own namespace, never the claims
journal (this lane never calls claims_ledger). SHADOW ONLY: no bet-path
change, no $/ROI/stake fields -- edge_claimed is always False, CLV is
reported in probability UNITS only.

Grading happens after settle: join a row's own captured book/price to the
real close via omni.close_lookup.pregame_close, then compute CLV-in-units for
BOTH the conditioned and unconditioned prediction against that SAME close
(the point of D1 -- prove, don't assume, whether conditioning helps).
is_clv_suspect flags cross-venue comparisons (crossvenue CLV is basis, not
edge -- memory reference_crossvenue_clv_basis_2026_07_06): True whenever the
row's own book differs from the close's resolved source venue.

INVARIANTS: stdlib + io_atomic only; ASCII stdout; <=300 LOC; never writes
data/registry/ or the claims journal; no $/edge claims.
"""
from __future__ import annotations

import pathlib
from typing import Any, Dict, Optional

from scripts.platformkit.io_atomic import append_jsonl_atomic

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_SHADOW_DIR = _REPO_ROOT / "data" / "omni" / "live_edge" / "shadow"


def shadow_path(date: str, *, shadow_dir: pathlib.Path = _SHADOW_DIR) -> pathlib.Path:
    """data/omni/live_edge/shadow/<date>.jsonl for a YYYY-MM-DD date string."""
    return shadow_dir / f"{date}.jsonl"


def make_shadow_row(
    *, ts: str, sport: str, game: str, market: str, book: str,
    unconditioned_pred: float, conditioned_pred: float, market_price: float,
    mechanism_applied: Optional[str] = None,
) -> Dict[str, Any]:
    """Build one pre-settle shadow row. is_clv_suspect and the close fields
    are unknown until settle -- grade_row() fills those in."""
    return {
        "ts": ts, "sport": sport, "game": game, "market": market, "book": book,
        "unconditioned_pred": float(unconditioned_pred),
        "conditioned_pred": float(conditioned_pred),
        "market_price": float(market_price),
        "mechanism_applied": mechanism_applied,
        "is_clv_suspect": None,
        "edge_claimed": False,
    }


def append_shadow_row(
    row: Dict[str, Any], *, date: Optional[str] = None, shadow_dir: pathlib.Path = _SHADOW_DIR,
) -> Dict[str, Any]:
    """Append one row to its date's shadow ledger file. date defaults to
    row["ts"]'s own UTC date (YYYY-MM-DD prefix), matching bus.py's convention."""
    d = date or str(row["ts"])[:10]
    append_jsonl_atomic(shadow_path(d, shadow_dir=shadow_dir), row, encoding="utf-8")
    return row


def grade_row(row: Dict[str, Any], close: Dict[str, Any]) -> Dict[str, Any]:
    """Grade ONE settled shadow row against its close (the dict
    close_lookup.pregame_close returns: {"prob_home_devig", "source", "ts"}).

    CLV_units convention: did our prediction point in the direction the
    market later moved, and by how much, relative to the price we actually
    captured? sign = sign(close_prob - market_price); clv_units(pred) =
    (pred - market_price) * sign. Calibration is also reported (squared error
    vs the eventual close) -- both fields, NO $/ROI, never fabricated."""
    close_prob = float(close["prob_home_devig"])
    market_price = float(row["market_price"])
    market_move = close_prob - market_price
    sign = 1.0 if market_move > 0 else (-1.0 if market_move < 0 else 0.0)

    def _clv_units(pred: float) -> float:
        return (pred - market_price) * sign

    unconditioned_pred = float(row["unconditioned_pred"])
    conditioned_pred = float(row["conditioned_pred"])
    return {
        **row,
        "close_prob": close_prob,
        "close_source": close.get("source"),
        "is_clv_suspect": bool(row.get("book") != close.get("source")),
        "unconditioned_clv_units": _clv_units(unconditioned_pred),
        "conditioned_clv_units": _clv_units(conditioned_pred),
        "unconditioned_sq_err_vs_close": (unconditioned_pred - close_prob) ** 2,
        "conditioned_sq_err_vs_close": (conditioned_pred - close_prob) ** 2,
        "edge_claimed": False,
    }


__all__ = ["shadow_path", "make_shadow_row", "append_shadow_row", "grade_row"]
