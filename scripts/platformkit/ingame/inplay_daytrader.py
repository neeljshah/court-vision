"""scripts.platformkit.ingame.inplay_daytrader -- LIVE in-play paper DAY-TRADER engine.

The thin execution loop that closes the only structural gap in the in-game stack: it
pairs the leak-free in-game MODEL number (predictor.predict_live, read-only, injected as
model_fn) with the LIVE liquid in-play PRICE, decides enter/hold/exit at each captured
tick, sizes in CAPPED quarter-Kelly UNITS, appends to a PAPER in-play ledger, and -- on
settle -- hands the captured per-game series to the EXISTING leak-free CLV grader.

It REUSES, never rebuilds:
  * edge      -> inplay_edge_signal.evaluate (devig + gate + tier; PURE).
  * sizing    -> pm_trading.policy.stake_units (flat unit + capped quarter-Kelly UNITS).
  * capture   -> live_grade.capture_pair_once (atomic paired-row write -> the grade file
    the aggregate grader reads). model_prob is captured LIVE -> replay is leak-free.
  * placement -> paper_ingame.record_ingame_bet (idempotent by edge_key, executed=False).
  * grade     -> inplay_aggregate_grade.aggregate_grade (clustered two-arm CLV-vs-close).

ENTER / HOLD / EXIT (day-trader decision, per captured tick):
  * ENTER when inplay_edge_signal.evaluate -> action="bet" (justified + liquid + fresh +
    a tier floor) AND we are FLAT -> size + paper-place (idempotent: a 2nd ENTER for the
    same game/side/day is a no-op).
  * HOLD when we already hold the same side and the edge persists -> capture the tick,
    place nothing new (idempotent).
  * EXIT is PASSIVE in paper: the in-play "close" is a PROXY (clv_is_proxy=True); the
    position is GRADED at settle, never actively unwound. A sign flip / below-floor tick
    is captured (for the grade series) but adds no new bet.

HONESTY (binding): PAPER-only -- executed is ALWAYS False; the real-money gate is a
separate human flip and DEFAULT-DENY. UNITS / probability only -- there is NO $ / roi /
pnl / stake$ field anywhere. edge_claimed is always False. A single game/tick is
INSUFFICIENT_DATA (one game is variance, not signal). LEAK-FREE: model_prob is computed
from state-as-of-this-tick by the injected model_fn; the close is the held-out yardstick,
never an input to enter/size.

INVARIANTS: build only under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no
network at import; no data/registry write, no flag flip, no autostart; never edits
live_grade / inplay_edge_signal-as-pure / policy / paper_ingame / src / kernel.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_daytrader.py -q
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame import inplay_edge_signal as _sig
from scripts.platformkit.ingame import live_grade as _lg
from scripts.platformkit.ingame import paper_ingame as _paper
from scripts.platformkit.pm_trading import policy as _policy

logger = logging.getLogger(__name__)

# A tick the engine acts on. The CALLER (the live daemon) builds this from the live state
# + the liquid Kalshi pair; all fields are injected so the tested code needs no network.
#   model_prob            -- P(home win) from predict_live (read-only), leak-free as-of tick
#   yes_home_prob/away    -- the liquid Kalshi YES(home)/YES(away) implied probs
#   obtainable_decimal    -- the decimal price you could actually take (default = no-vig)
#   calibration_justified -- True iff the lean is the proven prior / a gate-passed layer
#   is_liquid / is_fresh  -- the inplay_kalshi.is_liquid + freshness flags
LiveTick = Dict[str, Any]
StateFn = Callable[[LiveTick], Optional[Dict[str, Any]]]

MARKET = "win_home"  # one anchor moneyline market per game (HOME side)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _state_summary_fn(tick: LiveTick) -> Dict[str, Any]:
    """Best-effort live-state dict for live_grade.capture_pair_once's state label."""
    st = tick.get("state")
    return st if isinstance(st, dict) else {k: tick.get(k) for k in (
        "home_score", "away_score", "minute", "inning", "half", "clock", "period")
        if tick.get(k) is not None}


def on_tick(sport: str, game_id: str, tick: LiveTick, *,
            position: Optional[Dict[str, Any]] = None,
            now: Optional[datetime] = None,
            grade_dir: Optional[Path] = None,
            ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """Process ONE live in-play tick: capture the pair, decide enter/hold/exit, size+place.

    *position* is the engine's open position for this game/side (None = FLAT). Returns a
    decision dict {action, tier, side, edge, units, captured, placement, reason, position}
    where ``position`` is the (possibly unchanged) open position to thread into the next
    tick. UNITS only -- no $ field. NEVER raises (a bad tick -> action="no_bet").

    Flow per tick:
      1. evaluate the edge (PURE, gated) via inplay_edge_signal.evaluate.
      2. ALWAYS capture the (model_prob, devigged_price) pair via live_grade.capture_pair_once
         so the grade series is complete (leak-free; model_prob is as-of this tick).
      3. if action="bet" AND FLAT -> size (policy.stake_units) + paper-place (idempotent).
         if already holding -> HOLD (capture only). exit is passive (graded at settle).
    """
    nowdt = now or datetime.now(timezone.utc)
    decision: Dict[str, Any] = {
        "action": "no_bet", "tier": None, "side": _sig.SIDE,
        "edge": None, "units": {"flat_unit": 0.0, "quarter_kelly": 0.0},
        "captured": False, "placement": None, "reason": "",
        "position": position, "edge_claimed": False,
    }
    try:
        ev = _sig.evaluate(
            model_prob=tick.get("model_prob"),
            yes_home_prob=tick.get("yes_home_prob"),
            yes_away_prob=tick.get("yes_away_prob"),
            obtainable_decimal=tick.get("obtainable_decimal"),
            calibration_justified=bool(tick.get("calibration_justified", False)),
            is_liquid=bool(tick.get("is_liquid", False)),
            is_fresh=bool(tick.get("is_fresh", True)),
            clv_is_proxy=bool(tick.get("clv_is_proxy", True)),
            min_ev=tick.get("min_ev_floor"),  # opt-in relaxed in-game floor (None = strict)
        )
        decision.update({"tier": ev["tier"], "edge": ev["edge"],
                         "reason": ev["reason"]})

        # 2. ALWAYS capture the pair for the leak-free grade series (even on no_bet ticks:
        #    a complete price+model series is what the CLV/outcome arms grade).
        mp, dp = ev.get("model_prob"), ev.get("devigged_price")
        if mp is not None and dp is not None:
            cap = _lg.capture_pair_once(
                sport, game_id, now=nowdt,
                live_state_fn=lambda s, g: _state_summary_fn(tick),
                model_fn=lambda st: mp,
                market_fetch_fn=lambda s, g: dp,
                out_dir=grade_dir)
            decision["captured"] = cap.get("status") == "captured"

        # 3. enter / hold / exit.
        if ev["action"] != "bet":
            return decision  # no_bet: captured (for grading) but nothing placed
        if position is not None and position.get("status") == "open":
            decision["action"] = "hold"  # already in this side -> HOLD, no new placement
            decision["reason"] = "hold_existing"
            return decision

        # ENTER: size (UNITS only) then paper-place (idempotent, executed=False).
        dec_odds = ev.get("obtainable_decimal")
        units = _policy.stake_units(ev=ev["ev"], model_prob=mp,
                                    taken_decimal=dec_odds, tier=ev["tier"],
                                    clv_is_proxy=ev["clv_is_proxy"])
        placement = _paper.record_ingame_bet(
            sport, game_id, MARKET, _sig.SIDE, float(dec_odds),
            model_prob=mp, stake=0.0, path=ledger_path)  # stake$ stays 0.0 -- units only
        decision.update({
            "action": "bet", "units": units, "placement": placement,
            "position": {"status": "open", "side": _sig.SIDE, "tier": ev["tier"],
                         "model_prob": mp, "devigged_price": dp,
                         "edge_key": placement.get("edge_key"), "opened_ts": _now_iso()},
        })
    except Exception as exc:  # noqa: BLE001 -- one bad tick must never sink the loop
        logger.warning("on_tick(%s/%s) failed: %s", sport, game_id, exc)
        decision["reason"] = "error: %s" % type(exc).__name__
    return decision


def run_series(sport: str, game_id: str, ticks: List[LiveTick], *,
               grade_dir: Optional[Path] = None,
               ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """Drive a full captured tick series through on_tick (threading the open position).

    A convenience for offline replay / tests: feeds each tick in order, carries the open
    position forward, and returns {decisions, n_bets, n_holds, n_captured, position}. The
    live daemon would call on_tick once per real tick instead. UNITS only -- no $.
    """
    pos: Optional[Dict[str, Any]] = None
    decisions: List[Dict[str, Any]] = []
    for t in ticks:
        d = on_tick(sport, game_id, t, position=pos,
                    grade_dir=grade_dir, ledger_path=ledger_path)
        pos = d["position"]
        decisions.append(d)
    return {
        "decisions": decisions,
        "n_bets": sum(1 for d in decisions if d["action"] == "bet"),
        "n_holds": sum(1 for d in decisions if d["action"] == "hold"),
        "n_captured": sum(1 for d in decisions if d["captured"]),
        "position": pos,
        "units": "probability", "edge_claimed": False,
    }


def grade(sport: Optional[str] = None, *,
          grade_dir: Optional[Path] = None,
          min_games: int = 5) -> Dict[str, Any]:
    """Grade the captured day-trader series via the EXISTING clustered aggregate grader.

    Pure pass-through to inplay_aggregate_grade.aggregate_grade -- the leak-free,
    two-arm, game-clustered CLV-vs-true-close pool (BEAT needs n>=5 games + >=40 ticks +
    BOTH arms). A single game/tick -> INSUFFICIENT_DATA. UNITS / probability only; never a
    $ figure; edge_claimed=False. Imported lazily so this module's import is network-free.
    """
    from scripts.platformkit.ingame import inplay_aggregate_grade as _agg
    return _agg.aggregate_grade(grade_dir, sport=sport, min_games=min_games)


__all__ = ["MARKET", "on_tick", "run_series", "grade"]
