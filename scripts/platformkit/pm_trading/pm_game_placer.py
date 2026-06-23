"""scripts.platformkit.pm_trading.pm_game_placer -- paper-trade Kalshi / Polymarket
GAME (head-to-head moneyline) markets into the unified units ledger.

THE GAP: the M12 PM tick used a PREGAME endpoint that returns 0 game markets + Polymarket
only surfaced un-modelable OUTRIGHTS -> 0 PM paper bets. The keyless Kalshi exchange feed
(inplay_kalshi.fetch_inplay) DOES expose liquid game moneyline (WC 3-way + MLB 2-way) with
a real YES price. This prices each with OUR calibrated model, devigs the exchange price,
tiers via pm_trading.policy, and records a paper bet.

HONEST FRAMING: market_prob = devigged exchange price (2-way normalize; 3-way fold the Tie
into the field); model_prob = our pregame home_ml/away_ml; edge = model - market (prob
space). No model match / OUTRIGHTS -> NO bet (never guessed). Implausible thin/stale quotes
are skipped (plausibility band). is_pm=True; venue in {kalshi,polymarket}; channel=paper_pm;
clv_is_proxy=True; executed=False; edge_claimed=False; real-money default-DENY. bet_id=
pm|venue|game_id|side (idempotent). RAILS: scripts/platformkit only; ASCII; public fns NEVER
raise. Test: scripts/platformkit/pm_trading/test_pm_game_placer.py
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

DEFAULT_PM_GAME_SPORTS = ("mlb", "soccer_intl")
_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_LEDGER = _REPO / "data" / "frontend" / "clv_ledger.jsonl"
_TIER_RANK = {"A": 0, "B": 1, "C": 2}
_TIE_TOKENS = frozenset({"tie", "draw"})
_MIN_MKT, _MAX_MKT, _MAX_PLAUSIBLE_EV = 0.05, 0.95, 1.0  # plausibility band (stale-quote guard)

_HONEST_NOTE = (
    "Paper-placed Kalshi/Polymarket GAME moneyline (UNITS not $). market_prob = devigged "
    "exchange price; model_prob = calibrated pregame prob; edge_claimed=False; real-money DENY."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: Any) -> str:
    """Lowercase alphanumeric token (drops spaces/punct) for loose team matching."""
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _name_matches(a: str, b: str) -> bool:
    """Loose match: one normalized name is a substring of the other (>=3 chars).
    Bridges Kalshi city sides ('Toronto') to model full names ('Toronto Blue Jays')."""
    na, nb = _norm(a), _norm(b)
    if len(na) < 3 or len(nb) < 3:
        return na == nb and bool(na)
    return na in nb or nb in na


def group_by_game(rows: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """fetch_inplay rows -> {game_id: {'sides': {side_name: (prob, ticker)}, 'venue': v}}.
    Keeps the most recent prob per side; ignores rows missing a game_id/side/prob."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        gid = str(r.get("game_id") or "").strip()
        side = str(r.get("side") or "").strip()
        prob = _f(r.get("prob"))
        if not gid or not side or prob is None or not (0.0 < prob < 1.0):
            continue
        g = out.setdefault(gid, {"sides": {}, "venue": str(r.get("venue") or "kalshi")})
        g["sides"][side] = (prob, str(r.get("ticker") or ""))
    return out


def _split_sides(sides: Dict[str, Any]) -> Tuple[List[str], Optional[float]]:
    """Return (team_side_names, tie_prob). Tie/draw side is pulled out of the field."""
    teams: List[str] = []
    tie_prob: Optional[float] = None
    for name, (prob, _t) in sides.items():
        if _norm(name) in _TIE_TOKENS:
            tie_prob = prob
        else:
            teams.append(name)
    return teams, tie_prob


def match_model_game(team_sides: Sequence[str],
                     model_games: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find the model game whose {home,away} uniquely map to the two Kalshi team sides.
    Returns the model rec with an added side->role map, or None (no/ambiguous match)."""
    if len(team_sides) != 2:
        return None
    for g in model_games:
        home, away = str(g.get("home") or ""), str(g.get("away") or "")
        roles: Dict[str, str] = {}
        for side in team_sides:
            if _name_matches(side, home) and not _name_matches(side, away):
                roles[side] = "home"
            elif _name_matches(side, away) and not _name_matches(side, home):
                roles[side] = "away"
        if set(roles.values()) == {"home", "away"}:
            out = dict(g)
            out["_roles"] = roles
            return out
    return None


def _devig(side_prob: float, other_prob: float,
           tie_prob: Optional[float]) -> Optional[float]:
    """Fair P(this side wins): normalize YES prices (fold Tie into the field for 3-way)."""
    total = side_prob + other_prob + (tie_prob or 0.0)
    if total <= 0.0:
        return None
    return side_prob / total


def placements_from_game(game: Dict[str, Any], model: Dict[str, Any],
                         *, min_tier: Optional[str] = None) -> List[Dict[str, Any]]:
    """Build tiered home/away PM placements for one matched game (the +EV side(s)).
    Skips a side with no model prob, no fair price, or below the tier floor."""
    from scripts.platformkit.pm_trading import policy as _policy
    sides = game.get("sides") or {}
    teams, tie_prob = _split_sides(sides)
    roles = model.get("_roles") or {}
    probs = dict(model.get("pregame_probs") or {})
    by_role = {roles.get(n): (n, sides[n][0], sides[n][1]) for n in teams if n in roles}
    if "home" not in by_role or "away" not in by_role:
        return []
    out: List[Dict[str, Any]] = []
    for role, ml_key in (("home", "home_ml"), ("away", "away_ml")):
        name, yes_prob, ticker = by_role[role]
        other = by_role["away" if role == "home" else "home"][1]
        market_prob = _devig(yes_prob, other, tie_prob)
        model_prob = _f(probs.get(ml_key))
        if market_prob is None or model_prob is None:
            continue
        # plausibility: thin/stale quote outside the band fabricates a fake huge edge -> skip.
        if not (_MIN_MKT <= market_prob <= _MAX_MKT):
            continue
        ev = round(model_prob / market_prob - 1.0, 6)
        if ev > _MAX_PLAUSIBLE_EV:
            continue  # >100% EV is never a real liquid edge -> stale market / model error
        taken_decimal = round(1.0 / market_prob, 6)
        tier = _policy.tier(ev=ev, model_prob=model_prob, market_prob=market_prob,
                            clv_is_proxy=True)
        if tier is None:
            continue
        if min_tier is not None and _TIER_RANK.get(tier, 9) > _TIER_RANK.get(min_tier, -1):
            continue
        stakes = _policy.stake_units(ev=ev, model_prob=model_prob,
                                     taken_decimal=taken_decimal, tier=tier,
                                     clv_is_proxy=True)
        out.append({
            "venue": str(game.get("venue") or "kalshi"),
            "game_id": str(model.get("game_id") or game.get("game_id") or ""),
            "ticker": ticker, "side": role, "team": name,
            "matchup": "%s vs %s" % (model.get("home"), model.get("away")),
            "sport": str(model.get("sport") or ""),
            "model_prob": round(model_prob, 6), "market_prob": round(market_prob, 6),
            "taken_decimal": taken_decimal, "ev": ev, "tier": tier,
            "flat_unit": float(stakes["flat_unit"]),
            "quarter_kelly": float(stakes["quarter_kelly"]),
        })
    return out


def _ledger_row(p: Dict[str, Any]) -> Dict[str, Any]:
    venue = str(p["venue"])
    mid = str(p.get("ticker") or "%s-%s" % (p["game_id"], p["side"]))
    return {
        "ts": _now_iso(), "sport": str(p["sport"]),
        "matchup": str(p.get("matchup") or ""), "side": str(p["side"]),
        "taken_book": venue, "taken_decimal": float(p["taken_decimal"]),
        "model_prob": float(p["model_prob"]), "market_prob": float(p["market_prob"]),
        "stake_units": float(p["flat_unit"]), "quarter_kelly": float(p["quarter_kelly"]),
        "status": "open", "executed": False, "channel": "paper_pm", "is_pm": True,
        "venue": venue, "market_id": mid, "market_type": "moneyline",
        "ev": float(p["ev"]), "tier": str(p["tier"]),
        "edge": round(float(p["model_prob"]) - float(p["market_prob"]), 6),
        "clv_is_proxy": True, "clv_status": "INSUFFICIENT_DATA",
        "edge_claimed": False, "bet_id": "pm|%s|%s|%s" % (venue, p["game_id"], p["side"]),
    }


def _model_games(sport: str) -> List[Dict[str, Any]]:
    """Our calibrated slate from the predict store (home/away + pregame_probs). [] on miss."""
    try:
        from predict_service.store import read_latest
        env = read_latest(str(sport))
        if getattr(env, "status", "") != "ok":
            return []
        out = []
        for p in env.predictions or []:
            out.append({"sport": sport, "game_id": str(getattr(p, "game_id", "")),
                        "home": getattr(p, "home", ""), "away": getattr(p, "away", ""),
                        "pregame_probs": dict(getattr(p, "pregame_probs", {}) or {})})
        return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("pm_game_placer: model store(%s) failed: %s", sport, exc)
        return []


def _kalshi_feed(sport: str) -> List[Dict[str, Any]]:
    try:
        from scripts.platformkit.odds_provider.inplay_kalshi import fetch_inplay
        rows = fetch_inplay(str(sport))
        return [r if isinstance(r, dict) else dict(r) for r in (rows or [])]
    except Exception as exc:  # noqa: BLE001
        logger.debug("pm_game_placer: kalshi feed(%s) failed: %s", sport, exc)
        return []


def _existing_bet_ids(ledger_path: Path) -> set:
    try:
        from scripts.platformkit import clv_ledger as _clv
        return {str(r.get("bet_id")) for r in _clv.load_ledger(ledger_path) if r.get("bet_id")}
    except Exception:  # noqa: BLE001
        return set()


def _append(row: Dict[str, Any], ledger_path: Path) -> bool:
    try:
        from scripts.platformkit.clv_ledger_io import append_row as _ar
        _ar(row, path=ledger_path)
        return True
    except Exception:  # noqa: BLE001
        try:
            import json
            ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with ledger_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
            return True
        except Exception:  # noqa: BLE001
            return False


def run(sports: Sequence[str] = DEFAULT_PM_GAME_SPORTS, *,
        ledger_path: Optional[Path] = None,
        feed_fn: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
        model_fn: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
        place: bool = True, max_per_sport: Optional[int] = None,
        min_tier: Optional[str] = None) -> Dict[str, Any]:
    """Price live Kalshi (+PM) game markets with our model and paper-place the +EV sides.
    Never raises. Idempotent (bet_id dedup). UNITS only; is_pm=True; real-money DENY."""
    _ledger = Path(ledger_path) if ledger_path else _DEFAULT_LEDGER
    _feed = feed_fn or _kalshi_feed
    _model = model_fn or _model_games
    seen = _existing_bet_ids(_ledger) if place else set()
    by_sport: Dict[str, Dict[str, int]] = {}
    placed: List[str] = []
    n_games = n_matched = n_placed = n_dup = n_capped = 0
    for sport in sports:
        games = group_by_game(_feed(sport))
        model_games = _model(sport)
        n_games += len(games)
        cands: List[Dict[str, Any]] = []
        s_matched = 0
        for g in games.values():
            teams, _tie = _split_sides(g.get("sides") or {})
            model = match_model_game(teams, model_games)
            if model is None:
                continue
            s_matched += 1
            cands.extend(placements_from_game(g, model, min_tier=min_tier))
        cands.sort(key=lambda c: float(c.get("ev", 0.0)), reverse=True)
        n_matched += s_matched
        s_placed = s_dup = s_capped = 0
        for p in cands:
            row = _ledger_row(p)
            if row["bet_id"] in seen:
                s_dup += 1
                n_dup += 1
                continue
            if max_per_sport is not None and s_placed >= max_per_sport:
                s_capped += 1
                n_capped += 1
                continue
            if not place or _append(row, _ledger):
                seen.add(row["bet_id"])
                placed.append(row["bet_id"])
                s_placed += 1
                n_placed += 1
        by_sport[sport] = {"games": len(games), "matched": s_matched,
                           "placed": s_placed, "dup_skipped": s_dup, "capped": s_capped}
    return {"ts": _now_iso(), "n_games": n_games, "n_matched": n_matched,
            "n_placed": n_placed, "n_dup_skipped": n_dup, "n_capped": n_capped,
            "by_sport": by_sport, "placed_bet_ids": placed, "place": bool(place),
            "executed": False, "edge_claimed": False, "honest_note": _HONEST_NOTE}


__all__ = ["DEFAULT_PM_GAME_SPORTS", "group_by_game", "match_model_game", "placements_from_game", "run"]
