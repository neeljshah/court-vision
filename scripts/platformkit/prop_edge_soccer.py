"""scripts.platformkit.prop_edge_soccer -- soccer_intl per-line edge (split from
prop_edge). Behavior is UNCHANGED from the original in-file path; only the location
moved so prop_edge stays sport-blind and under the LOC cap.

The leak-free levers (NB dispersion, club-season prior, opponent team_defense
multiplier) all live here. The confidence gate + EV helper are INJECTED from
prop_edge so a test monkeypatching prop_edge._confidence still takes effect and the
soccer + MLB EV math can never drift. NEVER raises.

Per-file test: python -m pytest scripts/platformkit/test_prop_edge.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from domains.soccer import dispersion as soccer_dispersion
from domains.soccer import prop_engine
from domains.soccer.ingest_espn_athlete import club_prior as load_club_prior
from scripts.platformkit import soccer_team_map
from scripts.platformkit.odds_provider.prop_base import PropLine, canon_stat

logger = logging.getLogger(__name__)


def _club_prior_for(player_id, stat_canon: str, priors_path) -> Optional[Dict[str, Any]]:
    """A player's club prior; None when unavailable / unknown. Never raises."""
    try:
        cp = load_club_prior(player_id, stat_canon, priors_path=priors_path)
        return cp if cp.get("status") == "ok" else None
    except Exception:  # noqa: BLE001
        return None


def edge_for_line_soccer(
    cfg, line: PropLine, df, as_of: str, index, *,
    confidence_fn: Callable[..., str], apply_ev: Callable[..., None],
    dispersions: Optional[Dict[str, Any]] = None, priors_path=None,
    team_abbrs=None, opp_cache: Optional[Dict[Any, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """Resolve + distribute + EV one soccer PropLine -> {"edge"|"unresolved"}.
    ``dispersions`` NB-widens Poisson; ``priors_path`` = club priors;
    ``team_abbrs``/``opp_cache`` = leak-free opponent lever. Never raises."""
    raw_name = getattr(line, "player", None)
    res = cfg.resolve_player(df, raw_name, team=getattr(line, "team", None),
                             index=index)
    if res.get("status") != "ok":
        return {"unresolved": {"player": raw_name, "stat": line.stat,
                               "reason": res.get("reason", "unresolved")}}
    player_id = res["player_id"]
    stat_c = canon_stat(line.stat)
    cp = _club_prior_for(player_id, stat_c, priors_path)

    # Leak-free per-stat dispersion (phi=var/mean before as_of): first pass Poisson
    # to learn lam, then re-distribute with r=lam/(phi-1) so NB var=lam*phi.
    phi = ((dispersions or {}).get(stat_c) or {}).get("phi")
    om = soccer_team_map.opp_mult_for_line(
        getattr(line, "match", None), getattr(line, "team", None), df, as_of,
        stat_c, team_abbrs or [], opp_cache if opp_cache is not None else {})
    base = prop_engine.prop_distribution(
        df, player_id, stat_c, as_of, opp_mult=om, club_prior=cp)
    lam = base.get("lam") if base.get("status") == "ok" else None
    r_row = soccer_dispersion.r_for_lam(phi, lam)
    dist = prop_engine.prop_distribution(
        df, player_id, stat_c, as_of, opp_mult=om, dispersion=r_row, club_prior=cp)
    p_over_fn = dist.get("p_over")
    if dist.get("status") != "ok" or not callable(p_over_fn):
        return {"unresolved": {"player": raw_name, "stat": line.stat,
                               "reason": "model_unknown"}}
    try:
        model_p_over = float(p_over_fn(line.line))
    except Exception:  # noqa: BLE001
        model_p_over = float("nan")
    if model_p_over != model_p_over:  # NaN guard
        return {"unresolved": {"player": raw_name, "stat": line.stat,
                               "reason": "model_unknown"}}

    side = "over" if model_p_over >= 0.5 else "under"
    conf = confidence_fn(df, player_id, stat_c, as_of, club_prior=cp)
    edge: Dict[str, Any] = {
        "player": raw_name, "matched_name": res["matched_name"],
        "match": line.match, "team": line.team, "stat": stat_c, "line": line.line,
        "model_p_over": round(model_p_over, 4),
        "model_lam": round(float(dist["lam"]), 4) if dist.get("lam") is not None else None,
        "side": side, "confidence": conf, "club_backed": cp is not None,
        "model": dist.get("model"),
        "opp_mult": round(float(om), 4),
        "dispersion_phi": round(float(phi), 4) if isinstance(phi, (int, float)) else None,
        "reliable": (conf == "ok"), "source": line.source,
        "payout_type": line.payout_type, "tier": "MODEL_VIEW",
        "as_of": as_of,
        "best_ev": None, "model_gap": None, "edge_basis": None, "ev_flag": None,
    }
    apply_ev(edge, line, model_p_over, conf)
    return {"edge": edge}


__all__ = ["edge_for_line_soccer"]
