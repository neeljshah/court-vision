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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from scripts.platformkit.execution import expected_clv_gate as _exec_gate
from scripts.platformkit.execution.thresholds import INGAME_EXPECTED_CLV_MIN_PCT
from scripts.platformkit.pm_trading.pm_game_date_guard import _et_date_candidates, _name_matches
from scripts.platformkit.pm_trading.pm_game_match import (
    _split_sides, group_by_game, match_hits, match_model_game, route_for,
)

logger = logging.getLogger(__name__)

DEFAULT_PM_GAME_SPORTS = ("mlb", "soccer_intl")
_REPO = Path(__file__).resolve().parents[3]
_DEFAULT_LEDGER = _REPO / "data" / "frontend" / "clv_ledger.jsonl"
_TIER_RANK = {"A": 0, "B": 1, "C": 2}
_MIN_MKT, _MAX_MKT, _MAX_PLAUSIBLE_EV = 0.05, 0.95, 1.0  # plausibility band (stale-quote guard)

_HONEST_NOTE = (
    "Paper-placed Kalshi/Polymarket GAME moneyline (UNITS not $). market_prob = devigged "
    "exchange price; model_prob = calibrated pregame prob; edge_claimed=False; real-money DENY."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _f(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


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
    # ADDITIVE realistic-fill stamp (fill_prob/n_filled/slippage_prob/
    # book_age_sec/fill_quality) priced against the captured Kalshi depth
    # sidecar; no captured book -> fill_quality="no_book" (bet still written
    # at the snapshot price, honestly stamped unsimulated). Never raises.
    from scripts.platformkit.pm_trading.fill_sim import stamp_fill as _stamp
    row = _stamp(str(p.get("ticker") or ""), "yes", float(p["flat_unit"]),
                 sport=str(p.get("sport") or "") or None)
    row.update({
        "ts": _now_iso(), "sport": str(p["sport"]),
        "matchup": str(p.get("matchup") or ""), "side": str(p["side"]),
        "taken_book": venue, "taken_decimal": float(p["taken_decimal"]),
        "model_prob": float(p["model_prob"]), "market_prob": float(p["market_prob"]),
        "stake_units": float(p["flat_unit"]), "quarter_kelly": float(p["quarter_kelly"]),
        "status": "open", "executed": False, "channel": "paper_pm", "is_pm": True,
        "venue": venue, "market_id": mid, "market_type": "moneyline",
        # game_id IS the Kalshi event_ticker (inplay_kalshi sets it so); stamp it as
        # event_id so close_capture._kalshi_close can resolve this row's settled close
        # -> the paper_pm channel finally becomes CLV-measurable (was event_id=None).
        "event_id": str(p.get("game_id") or ""),
        "ev": float(p["ev"]), "tier": str(p["tier"]),
        "edge": round(float(p["model_prob"]) - float(p["market_prob"]), 6),
        "clv_is_proxy": True, "clv_status": "INSUFFICIENT_DATA",
        "edge_claimed": False, "bet_id": "pm|%s|%s|%s" % (venue, p["game_id"], p["side"]),
    })
    return row


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
                        "pregame_probs": dict(getattr(p, "pregame_probs", {}) or {}),
                        "date_candidates": _et_date_candidates(getattr(p, "tipoff", None))})
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
    n_games = n_matched = n_placed = n_dup = n_capped = n_ambiguous = n_suppressed = 0
    for sport in sports:
        games = group_by_game(_feed(sport))
        model_games = _model(sport)
        n_games += len(games)
        cands: List[Dict[str, Any]] = []
        s_matched = s_ambiguous = 0
        for gid, g in games.items():
            teams, _tie = _split_sides(g.get("sides") or {})
            hits = match_hits(teams, model_games, kalshi_date=g.get("date"),
                              ticker=gid, sport=sport)
            if len(hits) != 1:
                if len(hits) > 1:  # phantom-matchup guard: counted skip, never a guess
                    s_ambiguous += 1
                    n_ambiguous += 1
                continue
            s_matched += 1
            cands.extend(placements_from_game(g, hits[0], min_tier=min_tier))
        cands.sort(key=lambda c: float(c.get("ev", 0.0)), reverse=True)
        n_matched += s_matched
        s_placed = s_dup = s_capped = s_suppressed = 0
        for p in cands:
            _t0 = time.perf_counter()  # placement-path latency clock (ms, stamped below)
            # Execution-quality gate (pregame twin of run_paper_today / inplay exec_gate):
            # fair_prob = calibrated model prob; taken_decimal = 1/devigged exchange price.
            # SUPPRESS on fail (mirror the pregame/in-game block; behavior-neutral under the
            # current policy since the tier floor already dominates the 1% exec floor).
            # CRASH-SAFE: a gate error records the row UNGATED with an exec_gate_error note,
            # never blocks m1_paper. The STAMP is the load-bearing effect for m44.
            exec_gate: Optional[Dict[str, Any]] = None
            exec_gate_error: Optional[str] = None
            try:
                exec_gate = _exec_gate.gate(taken_decimal=float(p["taken_decimal"]),
                                            fair_prob=float(p["model_prob"]),
                                            threshold_pct=INGAME_EXPECTED_CLV_MIN_PCT)
                if not exec_gate.get("passed", False):
                    s_suppressed += 1
                    n_suppressed += 1
                    continue  # below expected-CLV floor -> suppress
            except Exception as exc:  # noqa: BLE001 -- gate must NEVER block a placement row
                exec_gate, exec_gate_error = None, type(exc).__name__
            row = _ledger_row(p)
            if exec_gate is not None:
                row["exec_gate"] = exec_gate
            if exec_gate_error is not None:
                row["exec_gate_error"] = exec_gate_error
            row["placement_latency_ms"] = (time.perf_counter() - _t0) * 1000.0
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
                           "placed": s_placed, "dup_skipped": s_dup, "capped": s_capped,
                           "suppressed": s_suppressed,
                           "ambiguous_skipped": s_ambiguous, "matcher": route_for(sport)}
    return {"ts": _now_iso(), "n_games": n_games, "n_matched": n_matched,
            "n_placed": n_placed, "n_dup_skipped": n_dup, "n_capped": n_capped,
            "n_ambiguous_skipped": n_ambiguous, "n_suppressed": n_suppressed,
            "by_sport": by_sport, "placed_bet_ids": placed, "place": bool(place),
            "executed": False, "edge_claimed": False, "honest_note": _HONEST_NOTE}


__all__ = ["DEFAULT_PM_GAME_SPORTS", "group_by_game", "match_model_game", "placements_from_game", "run"]
