"""predict_service.tennis_markets -- serve the FULL coherent tennis market surface.

ENGINE_COHERENCE_GAP lane. domains.tennis.markets.markets_for_matchup() already
prices ~9 standard tennis markets off ONE Monte Carlo finished-match matrix (the
serve holds predict() bisects to the calibrated Elo match-win). Until now
predict_service exposed only moneyline + total_games; the rest of that ALREADY-
COHERENT surface was computed and thrown away. This module reads markets_for_matchup()
and projects every derivable cell into provenance-stamped ProbEstimates -- so the
served surface is COHERENT with predict() by construction (read off the SAME matrix,
never recomputed inconsistently).

Pure STRUCTURAL exposure: NO new data, NO learned signal, NO leak risk, NO gate
needed (nothing is fed back into a model -- this only surfaces what the engine
already prices). Tie-break / within-set games are HONESTLY out of reach
(markets.POINT_MODEL_GAPS) and are NOT served.

HONESTY (enforced by shape): every served estimate is a ProbEstimate -> probability/
units only, NO $ field anywhere. vs_close is UNPROVEN (markets are efficient; no edge
is claimed). Provenance stamps model='tennis_mc_matrix', phase='pregame'.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $-edge fabrication; reuse domains.tennis.markets + registry verbatim.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from predict_service import registry
from predict_service.contracts import (
    HONEST_NOTE,
    SCHEMA_VERSION,
    VS_CLOSE_UNPROVEN,
    ProbEstimate,
    Provenance,
)

# All cells are read off the one MC finished-match matrix in markets_for_matchup().
_MODEL_ID = "tennis_mc_matrix"
_FUNNEL_DIR = os.path.join("data", "frontend", "funnel")
_VERDICT_NAME = "tennis_coherence.json"

# The coherent markets we SERVE (each genuinely produced by markets_for_matchup()).
SERVED_MARKETS = (
    "moneyline", "total_games", "total_sets", "set_handicap",
    "correct_set_score", "set_score_dist", "game_handicap",
    "per_set_winner", "first_set_winner",
)


def _prov() -> Provenance:
    """Provenance for every served cell: the MC matrix, pregame, no calibration tweak."""
    return Provenance(model=_MODEL_ID, signal="", calibration="elo_shin",
                      phase="pregame")


def _est(label: str, prob: float, market_type: str, side: str) -> ProbEstimate:
    """One provenance-stamped, no-$, units-only ProbEstimate read off the MC matrix."""
    return ProbEstimate(label=label, prob=round(float(prob), 6), provenance=_prov(),
                        interval=None, market_type=market_type, side=side)


def estimates_from_surface(surface: Dict[str, Any]) -> List[ProbEstimate]:
    """Project a markets_for_matchup() surface into provenance-stamped ProbEstimates.

    Reads each ALREADY-COHERENT cell off the SAME matrix the surface was built from --
    no recompute, no transform. Every estimate is probability/units only (no $);
    vs_close stays UNPROVEN by living as a ProbEstimate (which carries no edge field).
    """
    out: List[ProbEstimate] = []
    mw = surface.get("match_winner") or {}
    if "p1" in mw and "p2" in mw:
        out.append(_est("moneyline_p1", mw["p1"], "moneyline", "p1"))
        out.append(_est("moneyline_p2", mw["p2"], "moneyline", "p2"))

    ts = surface.get("total_sets") or {}
    if "over" in ts and "under" in ts:
        ln = ts.get("line")
        out.append(_est("total_sets_over_%s" % ln, ts["over"], "total_sets", "over"))
        out.append(_est("total_sets_under_%s" % ln, ts["under"], "total_sets", "under"))

    for h in surface.get("set_handicap") or []:
        ln = h.get("line")
        out.append(_est("set_handicap_p1_%s" % ln, h["cover"], "set_handicap",
                        "p1_%s" % ln))

    for k, v in (surface.get("set_score") or {}).items():
        out.append(_est("correct_set_score_%s" % k, v, "correct_set_score", k))

    ss = surface.get("straight_sets") or {}
    if "p1" in ss and "p2" in ss:
        out.append(_est("set_score_dist_straight_p1", ss["p1"], "set_score_dist", "p1"))
        out.append(_est("set_score_dist_straight_p2", ss["p2"], "set_score_dist", "p2"))

    for h in surface.get("game_handicap") or []:
        ln = h.get("line")
        out.append(_est("game_handicap_p1_%s" % ln, h["cover"], "game_handicap",
                        "p1_%s" % ln))

    psw = surface.get("per_set_winner") or {}
    if "p1" in psw and "p2" in psw:
        # per-set == first-set under the i.i.d.-set approximation the engine discloses.
        out.append(_est("per_set_winner_p1", psw["p1"], "per_set_winner", "p1"))
        out.append(_est("per_set_winner_p2", psw["p2"], "per_set_winner", "p2"))
        out.append(_est("first_set_winner_p1", psw["p1"], "first_set_winner", "p1"))
        out.append(_est("first_set_winner_p2", psw["p2"], "first_set_winner", "p2"))

    for ou in (surface.get("total_games") or {}).get("ou", []) or []:
        ln = ou.get("line")
        out.append(_est("total_games_over_%s" % ln, ou["over"], "total_games", "over"))
        out.append(_est("total_games_under_%s" % ln, ou["under"], "total_games", "under"))
    return out


def coherence_check(surface: Dict[str, Any], ests: List[ProbEstimate]) -> Dict[str, Any]:
    """Assert the served estimates are COHERENT with the underlying MC matrix.

    Checks read straight off markets_for_matchup() (no independent recompute):
      * served moneyline cells == surface match_winner (read off the SAME matrix)
      * correct-set-score distribution sums to ~1
      * P(2 total sets) == straight_sets_p1 + straight_sets_p2 (bo3 identity)
      * set_handicap -1.5 cover == straight_sets_p1 (engine invariant)
    Returns a dict of {check: bool}; the producer/test fail HARD on any False.
    """
    by_label = {e.label: e.prob for e in ests}
    checks: Dict[str, bool] = {}
    mw = surface.get("match_winner") or {}
    checks["moneyline_matches_matrix"] = (
        abs(by_label.get("moneyline_p1", -9) - float(mw.get("p1", 0))) < 1e-9 and
        abs(by_label.get("moneyline_p2", -9) - float(mw.get("p2", 0))) < 1e-9)
    ss = surface.get("set_score") or {}
    checks["set_score_sums_to_one"] = abs(sum(ss.values()) - 1.0) < 5e-3 if ss else False
    sts = surface.get("straight_sets") or {}
    ts = surface.get("total_sets") or {}
    p_two = float(sts.get("p1", 0)) + float(sts.get("p2", 0))
    checks["two_sets_eq_straight"] = abs(float(ts.get("under", -9)) - p_two) < 5e-3
    hcap = {h.get("line"): h.get("cover") for h in surface.get("set_handicap") or []}
    checks["set_hcap_m15_eq_straight_p1"] = (
        abs(float(hcap.get(-1.5, -9)) - float(sts.get("p1", 0))) < 5e-3)
    return {"all_ok": all(checks.values()), "checks": checks}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_tennis_coherence(
    p1: str = "Novak Djokovic", p2: str = "Carlos Alcaraz",
    surface: str = "Hard", *, n_sims: int = 8000, seed: int = 0,
) -> Dict[str, Any]:
    """Produce the served coherent tennis surface + coherence verdict (no persist).

    Builds the tennis predictor via the registry, prices markets_for_matchup() ONCE,
    projects it into served ProbEstimates, and runs the coherence check against the
    SAME matrix. Returns the JSON-able verdict envelope. status='unavailable' when
    the tennis corpus is absent (fresh clone) -- never fabricates a surface.
    """
    pred = registry.build_predictor("tennis")
    if pred is None:
        return {"status": "unavailable", "sport": "tennis",
                "schema_version": SCHEMA_VERSION, "generated_at": _now_iso(),
                "reason": "tennis corpus absent", "served_markets": list(SERVED_MARKETS),
                "estimates": [], "edge_claimed": False, "real_money_enabled": False}
    from domains.tennis.markets import markets_for_matchup  # noqa: PLC0415
    surf = markets_for_matchup(pred, p1, p2, surface, n_sims=n_sims, seed=seed)
    ests = estimates_from_surface(surf)
    coh = coherence_check(surf, ests)
    return {
        "status": "ok", "sport": "tennis", "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(), "lane": "ENGINE_COHERENCE_GAP",
        "matchup": {"p1": p1, "p2": p2, "surface": surface, "n_sims": n_sims},
        "served_markets": list(SERVED_MARKETS),
        "estimates": [e.to_dict() for e in ests],
        "coherence": coh,
        "provenance_model": _MODEL_ID,
        "vs_close": VS_CLOSE_UNPROVEN,
        "honest_note": HONEST_NOTE + (
            " Tennis surface read off ONE MC matrix; tie-break/within-set games are "
            "out of reach (POINT_MODEL_GAPS) and NOT served. Nothing here is fed back "
            "into a model -- pure structural exposure."),
        "edge_claimed": False, "real_money_enabled": False,
    }


def write_verdict(verdict: Dict[str, Any], *, out_dir: Optional[str] = None) -> str:
    """Persist the verdict to this lane's OWN JSON (no shared append -> no collisions)."""
    d = out_dir or _FUNNEL_DIR
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, _VERDICT_NAME)
    with open(path, "w", encoding="ascii") as fh:
        json.dump(verdict, fh, indent=2, sort_keys=True)
    return path


def produce_tennis_coherence(*, out_dir: Optional[str] = None, **kw: Any) -> str:
    """One cycle: build the coherent surface verdict and persist it. Returns the path."""
    return write_verdict(build_tennis_coherence(**kw), out_dir=out_dir)


__all__ = [
    "SERVED_MARKETS",
    "estimates_from_surface",
    "coherence_check",
    "build_tennis_coherence",
    "write_verdict",
    "produce_tennis_coherence",
]
