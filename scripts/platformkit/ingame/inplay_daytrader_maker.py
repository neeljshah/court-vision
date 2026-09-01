"""scripts.platformkit.ingame.inplay_daytrader_maker -- maker-fill ledger-row handling +
ENTER placement for inplay_daytrader.on_tick, split out under the <=300 LOC rail (pure
move, zero behavior change). Holds: (1) the maker-quote lifecycle branch (filled / expired
/ cancelled_suspended / still-resting) that turns a crossed resting quote into the ONE
paper_ingame ledger row, and (2) the ENTER branch that sizes + submits a NEW resting maker
quote. See inplay_daytrader.py's module docstring for the full day-trader contract.

Per-file test (exercised via the parent's suite; this module has no separate test file):
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_daytrader.py -q
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.platformkit.execution import ingame_exec_gate as _exec_gate
from scripts.platformkit.execution import sizing as _sizing
from scripts.platformkit.execution import writer_identity as _writer
from scripts.platformkit.execution.thresholds import ORDER_MODE
from scripts.platformkit.ingame import inplay_edge_signal as _sig
from scripts.platformkit.ingame import paper_ingame as _paper
from scripts.platformkit.ingame import quote_freshness as _freshness
from scripts.platformkit.pm_trading import policy as _policy

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def handle_maker_event(maker_event: Dict[str, Any], decision: Dict[str, Any],
                        position: Dict[str, Any], tick: Dict[str, Any], sport: str,
                        game_id: str, market: str,
                        ledger_path: Optional[Path]) -> Dict[str, Any]:
    """Turn ONE maker.advance() event (filled / expired / cancelled_suspended / still
    resting) into the final *decision* for this tick (mutated in place, also returned).
    Called only when *position* is a resting quote and maker.advance() returned non-None.

    filled -> ONE-WRITER gated paper_ingame.record_ingame_bet append (the only place a
    ledger row is ever written from a maker fill), building the exec audit trail.
    expired / cancelled_suspended -> position cleared, ledger untouched.
    otherwise -> still resting, decision reflects that (no ledger touch).
    """
    if maker_event["status"] == "filled":
        # ONE-WRITER (execution.writer_identity): only the sanctioned pod
        # paper node may append the SHARED default ledger. An explicitly
        # injected ledger_path (tests/scratch) is never gated.
        if ledger_path is None and not _writer.default_ledger_write_allowed():
            decision.update({"action": "no_bet", "reason": "not_ledger_writer",
                             "position": None})
            return decision
        quote, order = maker_event["quote"], maker_event["order"]
        audit = {**(position.get("exec_gate") or {}),
                 "execution_mode": "maker_only",
                 "clv_series": "paper_ingame_maker",
                 "maker_fee_units": quote["maker_fee_units"],
                 "order_lifecycle": list(order.history),
                 "order_state": order.state.value,
                 "order_id": order.order_id}
        fill_prob = order.avg_fill_price_cents / 100.0
        placement = _paper.record_ingame_bet(
            sport, game_id, market, position["side"], 1.0 / fill_prob,
            model_prob=position["model_prob"], stake=position["stake"],
            taken_book="paper_ingame_maker", path=ledger_path,
            signal_ts=tick.get("signal_ts"), exec_gate=audit,
            exec_depth=position.get("exec_depth"))
        decision.update({"action": "bet", "side": position["side"],
                         "units": quote["units"], "placement": placement,
                         "reason": "maker_fill_cross",
                         "position": {"status": "open", "side": position["side"],
                                      "tier": position["tier"],
                                      "model_prob": position["model_prob"],
                                      "edge_key": placement.get("edge_key"),
                                      "opened_ts": _now_iso()}})
        return decision
    if maker_event["status"] == "expired":
        decision.update({"action": "no_bet", "reason": "maker_ttl_expired",
                         "position": None})
        return decision
    if maker_event["status"] == "cancelled_suspended":
        # kickoff/void (paper_maker._market_suspended): the resting order
        # was cancelled, never filled retroactively. Ledger untouched.
        decision.update({"action": "no_bet", "reason": "maker_cancelled_suspended",
                         "position": None})
        return decision
    decision.update({"action": "resting",
                     "reason": "maker_" + str(maker_event.get("reason", "resting"))})
    return decision


def enter_new_position(ev: Dict[str, Any], tick: Dict[str, Any], sport: str,
                        game_id: str, nowdt: datetime, maker: Any, mp: Any,
                        decision: Dict[str, Any]) -> Dict[str, Any]:
    """ENTER: size (UNITS only) then paper-place (idempotent, executed=False). Bet the
    side the (now two-sided) signal chose -- may be AWAY, not just home -- using THAT
    side's model prob + obtainable decimal. The grade pair captured earlier stays
    home-aligned; only the placed bet's side/odds/prob reflect the chosen leg. Mutates
    and returns *decision*.
    """
    bet_side = ev.get("side", _sig.SIDE)
    bet_mp = ev.get("bet_model_prob", mp)
    dec_odds = ev.get("obtainable_decimal")

    # Expected-CLV + drift + max-spread placement gate (execution.ingame_exec_gate):
    # SUPPRESS-ONLY, never loosens the edge/liquidity/freshness gates already passed
    # above. Also builds the placement-time depth stamp (LEVER 1) threaded below.
    gr = _exec_gate.evaluate_placement(ev, tick, ticker=tick.get("ticker"), now=nowdt)
    decision["exec_gate"] = gr["exec_gate"]
    if gr["suppress"]:
        decision["reason"] = gr["reason"]
        logger.info("on_tick(%s/%s) suppressed reason=%s exec_gate=%s",
                    sport, game_id, gr["reason"], gr["exec_gate"])
        return decision

    units = _policy.stake_units(ev=ev["ev"], model_prob=bet_mp,
                                taken_decimal=dec_odds, tier=ev["tier"],
                                clv_is_proxy=ev["clv_is_proxy"])
    # LEVER 2 (tier-based sizing, team markets only, pre-registered 2026-07-15):
    # this channel trades only the anchor moneyline market (MARKET). CV_TIER_SIZING
    # off preserves the legacy flat-0.0 stake exactly (no behavior change if disabled).
    stake = (_sizing.stake_for(ev["tier"], "moneyline")
            if _sizing.tier_sizing_enabled() else 0.0)
    order_time = nowdt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state_age = _freshness.state_age_sec(order_time, [{"src_ts": tick.get("src_ts")}])
    stale_state = (state_age is not None and
                   state_age > _freshness.state_age_ceiling_sec(sport))
    if stale_state:
        decision.update({"action": "no_bet", "reason": "stale_state",
                         "state_age_sec": state_age, "position": None})
        return decision
    if ORDER_MODE != "maker_only":
        decision["reason"] = "unsupported_order_mode"
        return decision
    quote = maker.quote(sport, game_id, bet_side, bet_mp, units=units,
                        tick=tick, now=nowdt)
    if quote.get("status") != "resting":
        decision["reason"] = quote.get("reason", "maker_quote_rejected")
        return decision
    decision.update({
        "action": "resting", "side": bet_side, "units": units, "placement": quote,
        "reason": "maker_quote_submitted",
        "position": {"status": "resting", "side": bet_side, "tier": ev["tier"],
                     "model_prob": bet_mp, "stake": stake, "exec_gate": gr["exec_gate"],
                     "exec_depth": gr["exec_depth"], "maker_quote": quote,
                     "opened_ts": _now_iso()},
    })
    return decision
