"""scripts.platformkit.ingame.ingame_prop_dist_mlb -- pregame lam for live players, from the
MLB player-rate ENGINE (not the book catalog).

THE PROBLEM this solves: the in-game prop trader needs each player's pregame expected count
(lam) to re-price the remaining game. The obvious source -- the pregame prop board / snapshot
-- DROPS a game's players the moment it goes live (the book suspends pre-match props at first
pitch), so by the time a game is in-play its players are gone from the board. The player-rate
ENGINE (domains/mlb, season rates) has no such gap: it yields lam for ANY player in the
gamelog parquet, live or not.

For a single canonical stat we call cfg.engine_distribution directly. For the COMPOSITE
"Hits+Runs+RBIs" (the dominant live two-way market) the engine has no single stat, so we sum
the component lams (the mean is exactly additive; the re-price's freshness shrink on that mean
is the validated lever -- approximate by design, never fabricated).

HONEST RAILS: probability/units work happens downstream; this supplies lam only. A player /
stat the engine cannot resolve -> omitted (the trader then skips it). ASCII; <=300 LOC; never
raises. Per-file test: scripts/platformkit/ingame/test_ingame_prop_dist_mlb.py
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Iterable, Optional, Tuple

from scripts.platformkit.bestbets.prop_settler_mlb import _norm

logger = logging.getLogger(__name__)

# Composite stat -> the engine component stats whose lams sum to it.
_COMPOSITE: Dict[str, Tuple[str, ...]] = {
    "Hits+Runs+RBIs": ("Hits", "Runs", "RBIs"),
}

_CTX: Dict[str, Any] = {}  # sport -> (cfg, df, index); built once per process


def _load_ctx(sport: str) -> Optional[tuple]:
    """(cfg, df, index) for *sport*, cached. None if the engine/parquet is unavailable."""
    s = sport.lower()
    if s in _CTX:
        return _CTX[s]
    try:
        from scripts.platformkit import prop_edge_config
        import pandas as pd  # local: heavy import only when actually pricing live
        cfg = prop_edge_config.get_config(s)
        df = pd.read_parquet(cfg.parquet_path)
        index = cfg.build_name_index(df)
        _CTX[s] = (cfg, df, index)
        return _CTX[s]
    except Exception as exc:  # noqa: BLE001
        logger.warning("ingame_prop_dist_mlb: ctx load failed for %s: %s", sport, exc)
        _CTX[s] = None
        return None


def _engine_lam(cfg, df, index, player: str, stat: str, as_of: str
                ) -> Optional[Tuple[float, str]]:
    """(lam, model) for one (player, single canonical stat) via the engine, or None."""
    res = cfg.resolve_player(df, player, team=None, index=index)
    if not isinstance(res, dict) or res.get("status") != "ok":
        return None
    dist = cfg.engine_distribution(df, res["player_id"], stat, as_of, exposure=None)
    if not isinstance(dist, dict) or dist.get("status") != "ok":
        return None
    lam = dist.get("lam")
    if lam is None:
        return None
    try:
        return float(lam), str(dist.get("model") or "poisson")
    except (TypeError, ValueError):
        return None


def _lam_for(cfg, df, index, player: str, stat: str, as_of: str
             ) -> Optional[Tuple[float, str]]:
    """(lam, model) for a stat that may be a COMPOSITE (sum of component lams) or single."""
    if stat in _COMPOSITE:
        total = 0.0
        for comp in _COMPOSITE[stat]:
            got = _engine_lam(cfg, df, index, player, comp, as_of)
            if got is None:
                return None  # missing any component -> do not fabricate a partial sum
            total += got[0]
        return total, "poisson"  # sum of counts -> Poisson re-price on the additive mean
    return _engine_lam(cfg, df, index, player, stat, as_of)


def engine_dist_lookup(sport: str, pairs: Iterable[Tuple[str, str]], as_of: str,
                       *, ctx_loader: Optional[Callable[[str], Optional[tuple]]] = None
                       ) -> Dict[Tuple[str, str], Tuple[float, str]]:
    """{(player_norm, stat): (lam, model)} for each requested (raw_player, canonical_stat).

    Unresolvable pairs are simply omitted (the trader skips them). NEVER raises."""
    out: Dict[Tuple[str, str], Tuple[float, str]] = {}
    load = ctx_loader or _load_ctx
    ctx = load(sport)
    if ctx is None:
        return out
    cfg, df, index = ctx
    done: set = set()
    for raw, stat in pairs:
        if (raw, stat) in done:
            continue
        done.add((raw, stat))
        try:
            got = _lam_for(cfg, df, index, raw, stat, as_of)
        except Exception as exc:  # noqa: BLE001 -- one player must not sink the batch
            logger.debug("ingame_prop_dist_mlb: lam(%s,%s) failed: %s", raw, stat, exc)
            got = None
        if got is not None:
            out[(_norm(raw), stat)] = got
    return out


__all__ = ["engine_dist_lookup"]
