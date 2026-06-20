"""predict_service.surface -- the full per-sport market surface, contracted.

WAVE 3. Enumerates the complete market surface a sport exposes (from the
registry's declarative capability map) and projects a sport's latest snapshot
into a list of phase-LABELLED ProbEstimates across that surface. Every estimate
carries provenance (which model/signal/phase produced it); a merged pregame+
ingame number is LABELLED phase='merged' (never a silent average); an optional
held-out-residual interval may be attached. NO $ field anywhere.

This is a READ/projection layer -- it never builds a predictor or hits the
network. It reads the canonical store (a snapshot already produced) and the
registry capabilities, and assembles the contract face. A sport with no snapshot
returns an honest empty surface, never fabricated estimates.

INVARIANTS: build only under predict_service/; <=300 LOC; ASCII only; no secrets;
no $-edge fabrication; reuse registry/store/contracts/phase_merge verbatim.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from predict_service import registry, store
from predict_service.attribution import pregame_provenance
from predict_service.contracts import (
    HONEST_NOTE,
    SCHEMA_VERSION,
    ProbEstimate,
)
from predict_service.phase_merge import merged_estimate
from predict_service.surface_uniformity_annotate import annotate_surface_games
from predict_service.uncertainty import interval_from_residuals

# Map a stored pregame_probs key to (market_type, side, label). The label is the
# stored key itself so a consumer reads the exact market cell.
_PREGAME_KEY_MARKET = {
    "home_ml": ("moneyline", "home"),
    "away_ml": ("moneyline", "away"),
    "draw": ("moneyline", "draw"),
}


def market_catalog(sport: str) -> List[str]:
    """The declared market surface for *sport* (from the registry capabilities)."""
    caps = registry.capabilities(sport)
    return list(caps.get("markets", []) or [])


def _estimates_for_record(
    record,
    ingame_probs: Optional[Dict[str, float]] = None,
    residuals_by_label: Optional[Dict[str, Sequence[float]]] = None,
) -> List[ProbEstimate]:  # noqa: ANN001
    """Build phase-LABELLED ProbEstimates for one PredictionRecord.

    For each stored pregame_probs cell we emit a ProbEstimate. When an in-game
    number exists for that cell (ingame_probs[label]) the estimate is a phase
    LABELLED merge (phase='merged'), never a silent average. An interval is
    attached ONLY from held-out residuals supplied per label (leak-free).
    """
    ingame_probs = ingame_probs or {}
    residuals_by_label = residuals_by_label or {}
    out: List[ProbEstimate] = []
    pregame = getattr(record, "pregame_probs", None) or {}
    for label, p in pregame.items():
        mt, side = _PREGAME_KEY_MARKET.get(label, ("moneyline", label))
        try:
            pp = float(p)
        except (TypeError, ValueError):
            continue
        interval = interval_from_residuals(pp, residuals_by_label.get(label))
        ig = ingame_probs.get(label)
        est = merged_estimate(
            label=label, pregame_prob=pp,
            ingame_prob=(float(ig) if ig is not None else None),
            market_type=mt, side=side, interval=interval)
        if est is None:
            # No in-game and no usable pregame -> fall back to a bare pregame est.
            est = ProbEstimate(label=label, prob=round(pp, 6),
                               provenance=pregame_provenance(),
                               interval=interval, market_type=mt, side=side)
        out.append(est)
    return out


def build_surface(
    sport: str,
    *,
    out_dir: Optional[str] = None,
    ingame_by_game: Optional[Dict[str, Dict[str, float]]] = None,
    residuals_by_game: Optional[Dict[str, Dict[str, Sequence[float]]]] = None,
) -> Dict[str, Any]:
    """The full market surface for *sport* projected from the latest snapshot.

    Returns a JSON-able dict: {status, sport, schema_version, markets (the
    catalog), games:[{game_id, home, away, tipoff, estimates:[ProbEstimate...]}],
    honest_note, edge_claimed:False}. A missing snapshot yields status from the
    store sentinel and an empty games list -- never fabricated estimates.

    ingame_by_game / residuals_by_game are optional injection points (game_id ->
    label -> value); defaults emit pregame-only estimates with no interval. NO $
    field anywhere.
    """
    sport = sport.lower()
    ingame_by_game = ingame_by_game or {}
    residuals_by_game = residuals_by_game or {}
    env = store.read_latest(sport, out_dir=out_dir)
    games: List[Dict[str, Any]] = []
    if env.status == "ok":
        for rec in env.predictions:
            ests = _estimates_for_record(
                rec,
                ingame_probs=ingame_by_game.get(rec.game_id),
                residuals_by_label=residuals_by_game.get(rec.game_id))
            games.append({
                "game_id": rec.game_id,
                "home": rec.home,
                "away": rec.away,
                "tipoff": rec.tipoff,
                "estimates": [e.to_dict() for e in ests],
            })
    # Surface-level degenerate annotator: when MLB moneyline probs collapse to
    # <= 2 unique values (flat prior), every game record is stamped
    # degenerate_model=True + an honest note, and tier is nulled.  Non-MLB
    # sports and healthy diverse MLB surfaces are returned unchanged.
    annotate_surface_games(games, sport)

    return {
        "status": env.status,
        "sport": sport,
        "schema_version": SCHEMA_VERSION,
        "markets": market_catalog(sport),
        "generated_at": env.generated_at,
        "games": games,
        "honest_note": HONEST_NOTE,
        "edge_claimed": False,
        "real_money_enabled": False,
    }


__all__ = ["market_catalog", "build_surface"]
