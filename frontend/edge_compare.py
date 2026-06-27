"""frontend.edge_compare -- the per-(market_type, side) model-vs-best-market
comparison builder, split out of frontend.edge_api to keep each file <=300 LOC.

These are the pure helpers that turn a game's market rows + model probs + snapshot
EdgeRows into comparison rows. They live here (a sibling under frontend/) so the
assembler stays under the cap; edge_api re-imports them and the public shape is
unchanged.

HONESTY (enforced by shape): NO dollar / $edge / roi / pnl key ANYWHERE. The edge
is model_prob - market_prob (probability space) plus EV and the evidence tier. A
side with no devigged quote simply yields no comparison row -- we NEVER fabricate a
missing line, book, or price.

INVARIANTS: build only under frontend/; <=300 LOC; ASCII only; no $ key; no secrets.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def model_prob_for(probs: Dict[str, float], market_type: str,
                   side: str) -> Optional[float]:
    """Model probability for a (market_type, side): tries '<side>_<market_type>',
    '<side>_ml' (moneyline), then bare '<side>'. None when no key matches (never
    a fabricated value)."""
    if not isinstance(probs, dict):
        return None
    mt = str(market_type).lower()
    sd = str(side).lower()
    candidates = ["%s_%s" % (sd, mt), sd]
    if mt == "moneyline":
        candidates.insert(1, "%s_ml" % sd)
    for key in candidates:
        if key in probs and probs[key] is not None:
            try:
                return float(probs[key])
            except (TypeError, ValueError):
                return None
    return None


def best_quote(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Book with the LONGEST takeable price (highest decimal odds) for the bettor.

    The honest execution best-price is the longest DECIMAL ODDS the bettor can
    actually take -- that is the literal best obtainable quote, independent of any
    per-book devig noise. On a well-formed monotone book set (higher odds <-> lower
    devigged fair prob) max(odds) and min(devigged_prob) agree and this matches
    predict_service.assemble._market_consensus; when a fixture's devig is not
    monotone in odds, we still report the price the bettor truly gets (max odds),
    which is what the execution best-price claim depends on.

    Only rows with a real devigged_prob are eligible (a side with no fair quote
    yields no comparison row). The selection key is the takeable odds when present,
    else falls back to min(devigged_prob) so a missing price never fabricates a
    best. Returns None when nothing is eligible."""
    eligible = [r for r in rows if r.get("devigged_prob") is not None]
    if not eligible:
        return None
    priced = [r for r in eligible if r.get("odds") is not None]
    if priced:
        return max(priced, key=lambda r: float(r["odds"]))
    return min(eligible, key=lambda r: float(r["devigged_prob"]))


def edge_lookup(env: Any, game_id: str) -> Dict[Tuple[str, str], Any]:
    """Index the snapshot's EdgeRows by (market_type, side) for tier/EV reuse."""
    out: Dict[Tuple[str, str], Any] = {}
    for e in getattr(env, "edges", []) or []:
        if str(getattr(e, "game_id", "")) != game_id:
            continue
        out[(str(e.market_type), str(e.side))] = e
    return out


def comparison(markets: List[Dict[str, Any]], probs: Dict[str, float],
               edges: Dict[Tuple[str, str], Any]) -> List[Dict[str, Any]]:
    """One comparison row per (market_type, side): model vs best market price.
    market_prob is the BEST devigged prob across books; edge = model_prob -
    market_prob. ev/tier are reused from the snapshot EdgeRow when present (vetted
    upstream), else ev is recomputed from model_prob+best_odds and tier is None. A
    side with no devigged quote is skipped."""
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for m in markets:
        groups.setdefault((str(m.get("market_type")), str(m.get("side"))), []).append(m)

    rows: List[Dict[str, Any]] = []
    for (mtype, side), grp in groups.items():
        best = best_quote(grp)
        if best is None:
            continue
        market_prob = float(best["devigged_prob"])
        model_prob = model_prob_for(probs, mtype, side)
        edge_row = edges.get((mtype, side))
        if model_prob is None and edge_row is not None:
            try:
                model_prob = float(edge_row.model_prob)
            except (TypeError, ValueError):
                model_prob = None
        edge = (model_prob - market_prob) if model_prob is not None else None
        ev: Optional[float] = None
        tier: Optional[str] = None
        if edge_row is not None:
            ev = getattr(edge_row, "ev", None)
            tier = getattr(edge_row, "tier", None)
        elif model_prob is not None and best.get("odds"):
            try:
                ev = model_prob * float(best["odds"]) - 1.0
            except (TypeError, ValueError):
                ev = None

        rows.append({
            "market_type": mtype,
            "side": side,
            "model_prob": model_prob,
            "market_prob": market_prob,
            "best_book": best.get("book", ""),
            "best_odds": best.get("odds"),
            "line": best.get("line"),
            "edge": edge,
            "ev": ev,
            "tier": tier,
            "clv_is_proxy": bool(best.get("clv_is_proxy", False)),
        })
    return rows


__all__ = ["model_prob_for", "best_quote", "edge_lookup", "comparison"]
