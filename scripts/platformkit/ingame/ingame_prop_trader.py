"""scripts.platformkit.ingame.ingame_prop_trader -- IN-GAME player-prop paper trader.

As a game unfolds, re-price each player prop on the REALIZED state (running tally + how much
of the game is gone), compare to the book's LIVE two-way; where our number diverges past the
floor AND the edge clears the live vig, record a paper position. UNITS only; CLV judges; no $
edge. Sport-blind per-sport box adapter: mlb -> ingame_box_mlb (statsapi); soccer_intl ->
ingame_box_soccer (ESPN keyEvents; goals/assists/cards). reprice -> devig -> vig gate -> edge
-> tier/units -> one idempotent row (channel=paper_ingame_prop) the EXISTING settler grades.
HONEST RAILS: paper only (executed=False), edge_claimed=False, real-money DENY; validated
lever = freshness re-price (NOT $ edge); NEVER fabricates; ASCII; never raises.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.bestbets.prop_settler_mlb import _norm
from scripts.platformkit.ingame import ingame_box_mlb as _box_mlb
from scripts.platformkit.ingame import ingame_box_soccer as _box_soccer
from scripts.platformkit.ingame.ingame_prop_repricer import reprice_prop
from scripts.platformkit.odds_shop import devig_twoway, ev_vs_price

logger = logging.getLogger(__name__)

# sport -> realized-state adapter; a sport absent here is "unsupported" (clean no-op).
_BOX_BY_SPORT = {"mlb": _box_mlb, "soccer_intl": _box_soccer, "soccer": _box_soccer}

_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_LEDGER = _REPO / "data" / "frontend" / "clv_ledger.jsonl"
_SNAPSHOT_DIR = _REPO / "data" / "frontend" / "snapshots"

CHANNEL = "paper_ingame_prop"
_TIER_RANK = {"A": 0, "B": 1, "C": 2}
# Freshness band: too early = ~pregame; too late = ~nothing left / books pull lines.
_MIN_FRAC, _MAX_FRAC = 0.08, 0.90
_MIN_MKT_P, _MAX_MKT_P = 0.03, 0.97  # plausibility guards (drop degenerate/stale quotes)
_MAX_EV = 1.0  # ev > 100% on a liquid in-play line = stale/fat-finger -> skip
# VIG GATE (in-game-prop CLV-bleed fix): the live two-way's round-trip hold is the
# dominant CLV cost on this channel (~ -16% mean CLV). ev>0 only clears OUR half of the
# vig by our noisy in-game model -> require the edge over the DEVIGGED fair to clear the
# FULL hold, and skip absurdly-wide markets. Env-tunable; STRICTER-only (arms nothing).
_VIG_EDGE_MULT = float(os.environ.get("CV_INGAME_PROP_VIG_EDGE_MULT", "1.0") or 1.0)
_MAX_VIG = float(os.environ.get("CV_INGAME_PROP_MAX_VIG", "0.20") or 0.20)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_et() -> str:
    try:
        from scripts.platformkit.paper.et_day import now_et_day
        return now_et_day()
    except Exception:  # noqa: BLE001
        return datetime.now(timezone.utc).date().isoformat()


def dist_lookup_from_snapshot(sport: str,
                              *, path: Optional[Path] = None
                              ) -> Dict[Tuple[str, str], Tuple[float, str]]:
    """{(player_norm, stat): (lam, model)} from the refreshed prop-board snapshot.

    Reads data/frontend/snapshots/<sport>.json props.edges (each carries model_lam +
    model). Empty on any failure -- the trader then simply places nothing (honest)."""
    p = Path(path) if path is not None else (_SNAPSHOT_DIR / ("%s.json" % sport.lower()))
    out: Dict[Tuple[str, str], Tuple[float, str]] = {}
    try:
        edges = ((json.loads(p.read_text(encoding="utf-8")) or {})
                 .get("props", {}) or {}).get("edges", []) or []
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_prop_trader: snapshot read failed %s: %s", sport, exc)
        return out
    for e in edges:
        lam = e.get("model_lam")
        name = e.get("matched_name") or e.get("player")
        stat = e.get("stat")
        if lam is None or not name or not stat:
            continue
        try:
            out[(_norm(name), str(stat))] = (float(lam), str(e.get("model") or "poisson"))
        except (TypeError, ValueError):
            continue
    return out


def _live_index(live: List[Dict[str, Any]],
                box_fn: Callable[..., Dict[str, Any]]
                ) -> Tuple[Dict[str, Tuple[dict, dict]], Dict[str, Dict[str, Any]]]:
    """Across all live games build {player_norm: (batting,pitching)} and
    {player_norm: {frac, matchup, game_pk}} so a prop maps to its live game in O(1)."""
    stat_map: Dict[str, Tuple[dict, dict]] = {}
    meta: Dict[str, Dict[str, Any]] = {}
    for g in live:
        pk = g.get("game_pk")
        smap = box_fn(pk)
        frac = float(g.get("frac_elapsed") or 0.0)
        matchup = "%s @ %s" % (g.get("away") or "", g.get("home") or "")
        for pkey, entry in smap.items():
            stat_map[pkey] = entry
            meta[pkey] = {"frac": frac, "matchup": matchup, "game_pk": str(pk)}
    return stat_map, meta


def _price_one(sport: str, prop: Any, dist: Dict[Tuple[str, str], Tuple[float, str]],
               stat_map: Dict[str, Any], meta: Dict[str, Dict[str, Any]],
               day: str, min_tier: str, box: Any) -> Optional[Dict[str, Any]]:
    """One live prop -> a tiered in-game placement row, or None (skip on any gap)."""
    player = str(getattr(prop, "player", "") or "").strip()
    stat = str(getattr(prop, "stat", "") or "").strip()
    line = getattr(prop, "line", None)
    over_p = getattr(prop, "over_price", None)
    under_p = getattr(prop, "under_price", None)
    if not player or not stat or line is None:
        return None
    if not box.is_known_stat(stat):
        return None
    pkey = _norm(player)
    if pkey not in stat_map:           # player not currently in a live game -> skip
        return None
    lm = dist.get((pkey, stat))
    if lm is None:                     # no pregame distribution for this prop -> skip
        return None
    lam, model = lm
    realized = box.realized_for(stat, stat_map, player)
    if realized is None:
        return None
    frac = float(meta[pkey]["frac"])
    if not (_MIN_FRAC <= frac <= _MAX_FRAC):
        return None                    # outside the tradeable freshness band
    try:
        over_f, under_f = float(over_p), float(under_p)
    except (TypeError, ValueError):
        return None
    if over_f <= 1.0 or under_f <= 1.0:
        return None
    p_over = reprice_prop(lam_full=lam, line=float(line), frac_elapsed=frac,
                          realized_so_far=realized, model=model, stat_canonical=stat)
    if p_over is None or not (0.0 < p_over < 1.0):
        return None
    fair_over, fair_under = devig_twoway(over_f, under_f)
    side = "over" if p_over >= fair_over else "under"
    model_p = p_over if side == "over" else (1.0 - p_over)
    market_p = fair_over if side == "over" else fair_under
    price = over_f if side == "over" else under_f
    if not (_MIN_MKT_P <= market_p <= _MAX_MKT_P):
        return None
    edge = model_p - market_p
    if edge <= 0.0:                    # only place where OUR number sees value
        return None
    vig = (1.0 / over_f + 1.0 / under_f) - 1.0
    if vig <= 0.0:
        # arb/degenerate pair (booksum<=1): un-devigable, not tradeable. Pre-634fdd1a
        # devig RAISED here (row skipped); the shared guard now returns a synthesized
        # fair, so this gate must refuse explicitly (opus judge 2026-07-12 BLOCKER 1).
        return None
    if vig > _MAX_VIG or edge < _VIG_EDGE_MULT * vig:
        return None                    # market too wide, or edge doesn't clear the vig
    ev = ev_vs_price(model_p, price)
    if ev <= 0.0 or ev > _MAX_EV:      # below floor or implausible stale quote
        return None
    from scripts.platformkit.pm_trading import policy as _policy
    tier = _policy.tier(ev=ev, model_prob=model_p, market_prob=market_p, clv_is_proxy=True)
    if tier is None:
        return None
    if _TIER_RANK.get(str(tier), 9) > _TIER_RANK.get(str(min_tier), -1):
        return None
    stakes = _policy.stake_units(ev=ev, model_prob=model_p, taken_decimal=price,
                                 tier=tier, clv_is_proxy=True)
    book = str(getattr(prop, "source", "") or "draftkings").lower()
    return {
        "ts": _now_iso(), "sport": sport, "matchup": meta[pkey]["matchup"],
        "side": "home" if side == "over" else "away",  # binary-leg encoding
        "taken_book": book, "taken_decimal": round(price, 6),
        "model_prob": round(model_p, 6), "stake_units": float(stakes["flat_unit"]),
        "quarter_kelly": float(stakes["quarter_kelly"]), "status": "open",
        "executed": False, "channel": CHANNEL, "is_pm": False,
        "market": "prop|%s|%s|%s|%s" % (player, stat, line, side),
        "market_type": "prop", "prop_player": player, "prop_stat": stat,
        "prop_side": side, "line": line, "tier": str(tier),
        "market_prob": round(market_p, 6), "edge": round(edge, 6),
        "ev": round(ev, 6), "clv_is_proxy": True, "clv_status": "INSUFFICIENT_DATA",
        "game_date": day, "frac_elapsed": round(frac, 4),
        "realized_so_far": realized, "ingame": True, "edge_claimed": False,
        "bet_id": "ingame_prop|%s|%s|%s|%s|%s|%s|%s"
                  % (day, sport, player, stat, line, side, book),
    }


def _existing_ids(ledger_path: Path) -> set:
    try:
        from scripts.platformkit import clv_ledger as _clv
        return {str(r.get("bet_id")) for r in _clv.load_ledger(ledger_path)
                if r.get("bet_id")}
    except Exception:  # noqa: BLE001
        return set()


def _append(row: Dict[str, Any], ledger_path: Path) -> bool:
    try:
        from scripts.platformkit.clv_ledger_io import append_row as _ar
        _ar(row, path=ledger_path)
        return True
    except Exception:  # noqa: BLE001
        try:
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with ledger_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("ingame_prop_trader: append failed: %s", exc)
            return False


def run(sport: str = "mlb", *, max_per_game: int = 12, min_tier: str = "B",
        ledger_path: Optional[Path] = None, prop_provider: Any = None,
        dist: Optional[Dict[Tuple[str, str], Tuple[float, str]]] = None,
        live_games_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
        box_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        gate: Optional[Callable[[Dict[str, Any]], bool]] = None) -> Dict[str, Any]:
    """One in-game prop tick for *sport*. Records new tiered paper positions; idempotent.

    All deps injectable for offline tests. Returns a summary; NEVER raises."""
    out: Dict[str, Any] = {"status": "ok", "sport": sport, "placed": 0,
                           "live_games": 0, "channel": CHANNEL, "edge_claimed": False}
    try:
        box = _BOX_BY_SPORT.get(sport.lower())
        if box is None:
            out["status"] = "unsupported"          # no realized-state adapter for this sport
            return out
        is_soccer = box is _box_soccer
        ledger = Path(ledger_path) if ledger_path is not None else _DEFAULT_LEDGER
        # soccer adapters take the sport (to pick the ESPN league path); mlb is keyless-fixed.
        lg = live_games_fn or ((lambda: box.live_games(sport)) if is_soccer
                               else box.live_games)
        bx = box_fn or ((lambda pk: box.boxscore_stat_map(pk, sport=sport)) if is_soccer
                        else box.boxscore_stat_map)
        live = lg() or []
        out["live_games"] = len(live)
        if not live:
            out["reason"] = "no live games"
            return out
        if prop_provider is None:
            # LIVE in-play props (DK event endpoint; the pregame catalog suspends at start).
            # Soccer has no wired live two-way source yet -> fetch_props -> unavailable (no-op).
            from scripts.platformkit.odds_provider.prop_draftkings_live import (
                DraftKingsLivePropProvider)
            prop_provider = DraftKingsLivePropProvider()
        props = prop_provider.fetch_props(sport)
        if not isinstance(props, list):
            out["status"] = "no_prices"
            out["reason"] = str(props)
            return out
        stat_map, meta = _live_index(live, bx)
        day = _today_et()
        # Pregame lam per (player,stat): soccer = prop SNAPSHOT (model_lam); mlb = player-rate
        # ENGINE. Only resolve props joining a live-box player + known stat; tests inject dist.
        if dist is not None:
            lookup = dist
        elif is_soccer:
            lookup = dist_lookup_from_snapshot(sport)
        else:
            from scripts.platformkit.ingame.ingame_prop_dist_mlb import engine_dist_lookup
            pairs = [(str(getattr(p, "player", "")), str(getattr(p, "stat", "")))
                     for p in props
                     if _norm(str(getattr(p, "player", ""))) in stat_map
                     and box.is_known_stat(str(getattr(p, "stat", "")))]
            lookup = engine_dist_lookup(sport, pairs, day)
        if not lookup:
            out["reason"] = "no pregame distribution for live players"
            out["candidates"] = 0
            return out
        placements: List[Dict[str, Any]] = []
        for prop in props:
            row = _price_one(sport, prop, lookup, stat_map, meta, day, min_tier, box)
            if row is not None and (gate is None or gate(row)):  # in-game calib gate (opt)
                placements.append(row)
        # highest-EV first, cap per game (flood-bound; a position re-opens only next day)
        placements.sort(key=lambda r: r.get("ev", 0.0), reverse=True)
        per_game: Dict[str, int] = {}
        seen = _existing_ids(ledger)
        n = 0
        for row in placements:
            if row["bet_id"] in seen:
                continue
            gk = row["matchup"]
            if per_game.get(gk, 0) >= max_per_game:
                continue
            if _append(row, ledger):
                seen.add(row["bet_id"])
                per_game[gk] = per_game.get(gk, 0) + 1
                n += 1
        out["placed"] = n
        out["candidates"] = len(placements)
        return out
    except Exception as exc:  # noqa: BLE001 -- a tick must never crash the loop
        logger.warning("ingame_prop_trader.run failed: %s", exc)
        return {"status": "error", "reason": "%s: %s" % (type(exc).__name__, exc),
                "sport": sport, "placed": 0, "channel": CHANNEL}


__all__ = ["run", "dist_lookup_from_snapshot"]
