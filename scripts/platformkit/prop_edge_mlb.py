"""scripts.platformkit.prop_edge_mlb -- MLB per-line edge (split from prop_edge).

prop_edge.build_prop_board dispatches the MLB branch here. The MLB engine
(domains/mlb/prop_engine_mlb) PROJECTS exposure itself (exposure=None on the live
board) and models its own width, so the soccer-only dispersion / club-prior /
opponent levers are NOT used. The shared EV helper + reliability gate are INJECTED
from prop_edge so the soccer + MLB EV math can never drift and there is no import
cycle.

HONESTY (binding): the join key is the player NAME -- a wrong match fabricates a
fake edge -- so a line is left UNRESOLVED rather than mispriced when (a) the name
is ambiguous (resolver bias to false-negative), (b) its canonical stat is outside
the engine's set, or (c) the engine has no leak-free prior. tier is "MODEL_VIEW"
unless OOS-calibration promotes it (cache absent -> "unmeasured"). NEVER raises.

Per-file test: python -m pytest scripts/platformkit/test_prop_edge.py -q
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from scripts.platformkit.odds_provider.prop_base import PropLine, canon_stat


def _unresolved(raw_name, line, reason) -> Dict[str, Any]:
    return {"unresolved": {"player": raw_name, "stat": line.stat, "reason": reason}}


def edge_for_line_mlb(
    cfg, line: PropLine, df, as_of: str, index, *,
    apply_ev: Callable[..., None], reliable_n: int,
    rate_cache: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve + distribute + EV one MLB PropLine -> {"edge": {...}} or
    {"unresolved": {...}}. ``apply_ev`` attaches EV-vs-priced (two-way book) / model-
    view fields + ev_flag; ``reliable_n`` is the leak-free prior-exposure gate.
    ``rate_cache`` (optional): a per-SCORE-CYCLE memo dict (same instance for every
    line dispatched from one build_prop_board call) that lets the engine reuse the
    as_of-only-dependent leak-guard mask + league baseline across lines instead of
    recomputing them per line (m13 prop-edge-budget lane; ~53% of cycle time before
    this). None reproduces the prior uncached behavior exactly. Never raises."""
    raw_name = getattr(line, "player", None)
    res = cfg.resolve_player(df, raw_name, team=getattr(line, "team", None),
                             index=index)
    if res.get("status") != "ok":
        return _unresolved(raw_name, line, res.get("reason", "unresolved"))
    player_id = res["player_id"]
    stat_c = canon_stat(line.stat)
    if cfg.canonical_stats and stat_c not in cfg.canonical_stats:
        return _unresolved(raw_name, line, "stat_unsupported")

    dist = cfg.engine_distribution(df, player_id, stat_c, as_of, exposure=None,
                                   cache=rate_cache)
    p_over_fn = dist.get("p_over")
    if dist.get("status") != "ok" or not callable(p_over_fn):
        return _unresolved(raw_name, line, "model_unknown")
    try:
        model_p_over = float(p_over_fn(line.line))
    except Exception:  # noqa: BLE001
        model_p_over = float("nan")
    if model_p_over != model_p_over:  # NaN guard
        return _unresolved(raw_name, line, "model_unknown")

    side = "over" if model_p_over >= 0.5 else "under"
    n = dist.get("n")
    try:
        reliable = bool(n is not None and int(n) >= int(reliable_n))
    except (TypeError, ValueError):
        reliable = False
    conf = "ok" if reliable else "thin"
    lam = dist.get("lam")
    edge: Dict[str, Any] = {
        "player": raw_name, "matched_name": res["matched_name"],
        "match": line.match, "team": line.team, "stat": stat_c, "line": line.line,
        "model_p_over": round(model_p_over, 4),
        "model_lam": round(float(lam), 4) if lam is not None else None,
        "side": side, "confidence": conf, "club_backed": False,
        "model": dist.get("model"), "opp_mult": None, "dispersion_phi": None,
        "exposure": dist.get("exposure"), "n": n,
        "reliable": reliable, "source": line.source,
        "payout_type": line.payout_type, "tier": "MODEL_VIEW", "as_of": as_of,
        "best_ev": None, "model_gap": None, "edge_basis": None, "ev_flag": None,
    }
    apply_ev(edge, line, model_p_over, conf)
    return {"edge": edge}


__all__ = ["edge_for_line_mlb"]
