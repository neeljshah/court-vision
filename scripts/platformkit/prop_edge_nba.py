"""scripts.platformkit.prop_edge_nba -- NBA prop board: price + tier injected lines.

Wires player_props.price_prop to the prop board pattern. For each PropLine:
  1. Resolve raw name -> player_id via player_boxscores.parquet.
  2. Canonicalize stat; unsupported stat -> unresolved bucket.
  3. price_prop -> model_p_over (insufficient_history -> unresolved bucket).
  4. EV-vs-priced via prop_edge._apply_ev; DFS pick'em -> model-view gap.
  5. Tier via prop_tiering.apply_tier with OOF-calibration cache (P0-1).
Board: each row has model_p_over + calibration label + tier. Unresolved = player
not found OR stat unsupported (never dropped, never assigned a fake edge).
CALIBRATION not $. Never raises.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_prop_edge_nba.py -q
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.odds_provider.prop_base import PropLine
from scripts.platformkit import prop_tiering

logger = logging.getLogger(__name__)

# PropLine.stat -> price_prop stat key. Only stats the engine can price; else unresolved.
# _canon_nba_stat tries exact then lowercase, so only title-case entries needed here.
_NBA_STAT_CANON: Dict[str, str] = {
    "Points": "pts", "Rebounds": "reb", "Assists": "ast",
    "Steals": "stl", "Blocks": "blk", "Turnovers": "tov",
    "3-PT Made": "fg3m", "3-pt made": "fg3m",
    "3pt made": "fg3m", "3 pointers made": "fg3m",
    "Pts+Reb+Ast": "pra", "Pts+Reb": "pr", "Pts+Ast": "pa", "Reb+Ast": "ra",
    "pts+reb+ast": "pra", "pts+reb": "pr", "pts+ast": "pa", "reb+ast": "ra",
}

_RELIABLE_N = 5  # minimum prior games to consider a line reliably priced

HONEST_NOTE = (
    "NBA prop board: model_p_over from recency-weighted Gaussian (player_props.price_prop);"
    " tier from OOS-calibration cache (props_eval_nba). CALIBRATION not $. Unresolved rows"
    " = player name not matched or stat unsupported. MODEL_VIEW default; CALIBRATION_PROVEN"
    " only if OOS-calibrated per P0-1. Never raises / never fabricates."
)


def _build_nba_name_index(df) -> Dict[str, int]:
    """Build {lowercase_name: player_id} from player_boxscores. Empty dict on fail."""
    try:
        index: Dict[str, int] = {}
        for _, row in df[["player_name", "player_id"]].drop_duplicates().iterrows():
            index[str(row["player_name"]).strip().lower()] = int(row["player_id"])
        return index
    except Exception as exc:  # noqa: BLE001
        logger.warning("nba_name_index: failed: %s", exc)
        return {}


def _resolve_nba_player(raw_name: Optional[str], index: Dict[str, int]) -> Optional[int]:
    """Case-insensitive exact match -> player_id. None = no match (bias false-negative)."""
    if not raw_name:
        return None
    return index.get(str(raw_name).strip().lower())


def _canon_nba_stat(stat: Optional[str]) -> Optional[str]:
    """Map PropLine stat -> price_prop key. None = unsupported (never guessed)."""
    if stat is None:
        return None
    # Try exact first; then title-case; then lowercase (provider label variety).
    return (_NBA_STAT_CANON.get(stat)
            or _NBA_STAT_CANON.get(stat.title())
            or _NBA_STAT_CANON.get(stat.lower()))


def _unresolved(raw_name: Optional[str], line: PropLine, reason: str) -> Dict[str, Any]:
    return {"unresolved": {"player": raw_name, "stat": line.stat,
                           "line": line.line, "reason": reason}}


def edge_for_line_nba(
    line: PropLine,
    df,
    as_of: str,
    index: Dict[str, int],
    *,
    apply_ev: Callable[..., None],
) -> Dict[str, Any]:
    """Price one NBA PropLine -> {"edge":{...}} or {"unresolved":{...}}. Never raises."""
    raw_name = getattr(line, "player", None)
    player_id = _resolve_nba_player(raw_name, index)
    if player_id is None:
        return _unresolved(raw_name, line, "player_not_found")
    stat_key = _canon_nba_stat(line.stat)
    if stat_key is None:
        return _unresolved(raw_name, line, "stat_unsupported")
    try:
        from domains.basketball_nba.player_props import price_prop
        res = price_prop(player_id, stat_key, float(line.line), as_of, df=df)
    except Exception as exc:  # noqa: BLE001
        logger.warning("price_prop failed for %s/%s: %s", raw_name, stat_key, exc)
        return _unresolved(raw_name, line, "price_prop_error")
    if not isinstance(res, dict):
        return _unresolved(raw_name, line, "model_unknown")
    status = res.get("status", "")
    if status == "insufficient_history":
        return _unresolved(raw_name, line, "insufficient_history")
    if status != "ok":
        return _unresolved(raw_name, line, "model_unknown")
    p_over = res.get("p_over")
    if p_over is None:
        return _unresolved(raw_name, line, "model_unknown")
    try:
        model_p_over = float(p_over)
    except (TypeError, ValueError):
        return _unresolved(raw_name, line, "model_unknown")
    if model_p_over != model_p_over:  # NaN guard
        return _unresolved(raw_name, line, "model_unknown")
    n_games = res.get("n_games")
    reliable = bool(n_games is not None and int(n_games) >= _RELIABLE_N)
    conf = "ok" if reliable else "thin"
    edge: Dict[str, Any] = {
        "player": raw_name, "player_id": player_id,
        "match": line.match, "team": line.team,
        "stat": stat_key, "stat_raw": line.stat, "line": float(line.line),
        "model_p_over": round(model_p_over, 4),
        "proj_mean": res.get("proj_mean"), "proj_sigma": res.get("proj_sigma"),
        "side": "over" if model_p_over >= 0.5 else "under",
        "n_games": n_games, "reliable": reliable, "confidence": conf,
        "source": line.source, "payout_type": line.payout_type,
        "tier": "MODEL_VIEW", "as_of": as_of,
        "best_ev": None, "model_gap": None, "edge_basis": None, "ev_flag": None,
    }
    apply_ev(edge, line, model_p_over, conf)
    return {"edge": edge}


def build_nba_prop_board(
    lines: List[PropLine],
    df,
    as_of: str,
    *,
    calibration_path: Optional[str] = None,
    apply_ev_fn: Optional[Callable[..., None]] = None,
) -> Dict[str, Any]:
    """Ranked, tiered NBA prop board from injected PropLines. Never raises.

    Returns {sport, as_of, status, honest_note, edges, unresolved,
    unresolved_count, calibration_labels}.
    apply_ev_fn: injected EV fn (default: prop_edge._apply_ev).
    calibration_path: OOS cache (absent -> all "unmeasured").
    """
    base: Dict[str, Any] = {
        "sport": "nba", "as_of": as_of, "status": "unknown",
        "honest_note": HONEST_NOTE, "edges": [], "unresolved": [],
        "unresolved_count": 0, "calibration_labels": {},
    }
    try:
        if apply_ev_fn is None:
            from scripts.platformkit.prop_edge import _apply_ev as _default_ev
            apply_ev_fn = _default_ev
        if df is None or len(df) == 0:
            base["status"] = "no_data"
            return base
        cal_path = calibration_path or os.path.join(
            "data", "cache", "props_eval_nba_calibration.json")
        calibration = _load_nba_calibration(cal_path)
        index = _build_nba_name_index(df)
        edges: List[Dict[str, Any]] = []
        unresolved: List[Dict[str, Any]] = []
        for line in lines:
            if not isinstance(line, PropLine):
                continue
            out = edge_for_line_nba(line, df, as_of, index, apply_ev=apply_ev_fn)
            if "edge" in out:
                edges.append(prop_tiering.apply_tier(out["edge"], calibration))
            else:
                unresolved.append(out["unresolved"])
        edges = sorted(edges, key=prop_tiering.calibration_rank_key)
        base["edges"] = edges
        base["unresolved"] = unresolved
        base["unresolved_count"] = len(unresolved)
        base["status"] = "ok"
        base["calibration_labels"] = prop_tiering.label_distribution(edges)
        return base
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_nba_prop_board failed: %s", exc)
        base["status"] = "error: %s" % type(exc).__name__
        return base


def _load_nba_calibration(path: str) -> Dict[str, Any]:
    """Load NBA OOS calibration (bypasses soccer staleness guard). {} on error."""
    try:
        from scripts.platformkit.props_eval_nba import load_nba_calibration
        return load_nba_calibration(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("_load_nba_calibration failed: %s", exc)
        return {}


__all__ = [
    "edge_for_line_nba", "build_nba_prop_board", "HONEST_NOTE",
    "_build_nba_name_index", "_resolve_nba_player", "_canon_nba_stat",
]
