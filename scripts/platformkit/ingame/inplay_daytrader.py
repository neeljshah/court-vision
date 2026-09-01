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
  * placement -> resting simulated maker quote -> paper_ingame.record_ingame_bet only
    after a subsequent captured-price cross.
  * grade     -> inplay_aggregate_grade.aggregate_grade (clustered two-arm CLV-vs-close).

ENTER / HOLD / EXIT (day-trader decision, per captured tick):
  * ENTER when inplay_edge_signal.evaluate -> action="bet" (justified + liquid + fresh +
    a tier floor) AND we are FLAT -> size + submit a simulated resting maker quote.
  * RE-ENTER on a side FLIP: if we hold one side and the live edge has flipped to the
    OTHER side and that side independently clears the same gate, ENTER the new side (a
    genuinely new +EV opportunity as the line moved). The old position stays open and
    grades at settle; the new side is a distinct edge_key. Bounded to one position PER
    SIDE per day by the ledger idempotency, so a thrashing tick stream cannot churn.
  * HOLD when we already hold the SAME side the edge still favours -> capture the tick,
    place nothing new (idempotent).
  * EXIT is PASSIVE in paper: the in-play "close" is a PROXY (clv_is_proxy=True); the
    position is GRADED at settle, never actively unwound. A below-floor / same-side tick
    is captured (for the grade series) but adds no new bet.

HONESTY (binding): PAPER-only -- executed is ALWAYS False; the real-money gate is a
separate human flip and DEFAULT-DENY. UNITS / probability only -- there is NO $ / roi /
pnl / stake$ field anywhere. edge_claimed is always False. A single game/tick is
INSUFFICIENT_DATA (one game is variance, not signal). LEAK-FREE: model_prob is computed
from state-as-of-this-tick by the injected model_fn; the close is the held-out yardstick,
never an input to enter/size. VENUE-GATED (binding): PAPER DECISIONS (enter/re-enter) are
Kalshi-only for now -- see DEFAULT_PAPER_VENUES / CV_PAPER_VENUES. capture_pair_once's
grade series stays venue-agnostic and is never gated by this.

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

from scripts.platformkit.claims import condition_tagger as _tagger
from scripts.platformkit.execution import ingame_exec_gate as _exec_gate
from scripts.platformkit.execution.paper_maker import PaperMakerAdapter
from scripts.platformkit.execution import writer_identity as _writer
from scripts.platformkit.ingame import ingame_clv_per_segment as _clvseg
from scripts.platformkit.ingame import latency_scoreboard as _latsb
from scripts.platformkit.ingame import ingame_segment_trust_multi as _trust_multi
from scripts.platformkit.ingame import inplay_edge_signal as _sig
from scripts.platformkit.ingame import live_grade as _lg
from scripts.platformkit.ingame.inplay_daytrader_gates import MARKET, apply_late_gates, grade
from scripts.platformkit.ingame.inplay_daytrader_maker import (
    enter_new_position, handle_maker_event)

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

# MARKET / DEFAULT_PAPER_VENUES / the venue-allowlist + late suppression-gate chain now
# live in inplay_daytrader_gates.py (split out under the <=300 LOC rail; pure move, zero
# behavior change -- see that module's docstring).
_PAPER_MAKER = PaperMakerAdapter()


def _state_summary_fn(tick: LiveTick) -> Dict[str, Any]:
    """Best-effort live-state dict for live_grade.capture_pair_once's state label."""
    st = tick.get("state")
    return st if isinstance(st, dict) else {k: tick.get(k) for k in (
        "home_score", "away_score", "minute", "inning", "half", "clock", "period")
        if tick.get(k) is not None}


# Sanctioned (sport -> {segment labels}) suppression targets, per
# docs/research/organization-sprint/PROPOSED_soccer_inplay_suppression.md section 5's
# scoping notes: "Strict SPORT+SEGMENT scoped (soccer_intl H1/H2)" and "Do NOT suppress
# on the UNK bucket ... it is a data-capture artifact, not a game-phase segment."
#
# EMPTY BY DESIGN today. The doc's own verdict (section 0/6) is that a real, non-UNK,
# ADVERSE-REPLICATED finding for soccer_intl H1/H2 exists ONLY on the BACKFILLED variant
# (the kickoff-derived tick_segment_backfill.json sidecar), which this runtime lookup
# does NOT compute -- build_trust_for_sport(sport) here reads the live RAW ops doc
# (data/frontend/ops/ingame_segment_trust_multi.json), where soccer_intl H1/H2 are
# NEUTRAL (INSUFFICIENT_DATA) and only the forbidden UNK bucket is ADVERSE. The doc's
# section 6 bottom line is explicit: "evidence bar met, human decision requested" --
# still unresolved, no Fable-APPROVED artifact exists anywhere under docs/research/. So
# this allowlist stays empty (suppression wired but inert) until a human populates it
# with a sport/segment pair actually backed by runtime-computable, non-UNK, cross-corpus
# ADVERSE evidence. Never edit this to include "UNK" for any sport.
_SANCTIONED_ADVERSE_SEGMENTS: Dict[str, frozenset] = {
    # "soccer_intl": frozenset({"H1", "H2"}),  # NOT enabled -- see comment above.
}


def _segment_is_adverse(sport: str, tick: LiveTick) -> bool:
    """True iff the CURRENT tick's segment is BOTH (a) sanctioned for this sport per
    _SANCTIONED_ADVERSE_SEGMENTS (never includes the UNK catch-all -- hard-excluded
    below regardless of allowlist contents) AND (b) reported cross-corpus ADVERSE by
    ingame_segment_trust_multi.build_trust_for_sport(sport).

    Reuses the exact same state_summary string pipeline live_grade.capture_pair_once
    already builds (_state_summary_fn -> live_grade._state_summary -> the same
    _infer_segment classifier ingame_outcome_verdict/ingame_segment_trust_multi score
    against), so the segment label looked up here always matches the label the trust
    doc was built from. Fail-open (queue item 8a): ANY exception (bad sport, missing
    trust doc, import hiccup) -> False, i.e. behave EXACTLY as before this suppression
    existed. MEASUREMENT-DRIVEN WITHHOLD ONLY -- never claims an edge, never raises.
    """
    try:
        seg_label = _clvseg._infer_segment(sport, _lg._state_summary(_state_summary_fn(tick)))
        if seg_label == "UNK":
            return False  # hard exclude: UNK is a missing-clock-state capture artifact,
            # never a tradeable game-phase segment (doc sections 2/5/6) -- regardless of
            # what any trust doc reports for the UNK bucket.
        sanctioned = _SANCTIONED_ADVERSE_SEGMENTS.get(sport) or frozenset()
        if seg_label not in sanctioned:
            return False  # only doc-sanctioned, non-UNK (sport, segment) pairs are eligible
        trust_doc = _trust_multi.build_trust_for_sport(sport)
        seg_trust = (trust_doc.get("segments", {}).get(seg_label) or {}).get("trust")
        return seg_trust == "ADVERSE"
    except Exception as exc:  # noqa: BLE001 -- fail-open: unchanged behavior on any error
        logger.warning("_segment_is_adverse(%s) failed: %s", sport, exc)
        return False


def on_tick(sport: str, game_id: str, tick: LiveTick, *,
            position: Optional[Dict[str, Any]] = None,
            now: Optional[datetime] = None,
            grade_dir: Optional[Path] = None,
            ledger_path: Optional[Path] = None,
            extra: Optional[Dict[str, Any]] = None,
            paper_venues: Optional[Any] = None,
            maker_adapter: Optional[PaperMakerAdapter] = None) -> Dict[str, Any]:
    """Process ONE live in-play tick: capture the pair, decide enter/hold/exit, size+place.

    *position* is the engine's open position for this game/side (None = FLAT). Returns a
    decision dict {action, tier, side, edge, units, captured, placement, reason, position}
    where ``position`` is the (possibly unchanged) open position to thread into the next
    tick. UNITS only -- no $ field. NEVER raises (a bad tick -> action="no_bet").

    *extra* (LANE 3 persistence, optional): forwarded verbatim to
    live_grade.capture_pair_once's `extra` kwarg -- additive enrichment fields merged
    into the persisted grade row. See that function's docstring for the additive-only
    (never-overwrites-core-keys) guarantee.

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
        maker = maker_adapter or _PAPER_MAKER
        maker_event = (maker.advance(position, tick, now=nowdt)
                       if position is not None and position.get("status") == "resting"
                       else None)
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
            # additive claim tags (TAG ONLY, zero behavior change) -> segment-key feed
            try:
                claim_tags = _tagger.tag(dict(tick), "ingame")
            except Exception:  # noqa: BLE001
                claim_tags = {}
            cap = _lg.capture_pair_once(
                sport, game_id, now=nowdt,
                live_state_fn=lambda s, g: _state_summary_fn(tick),
                model_fn=lambda st: mp,
                market_fetch_fn=lambda s, g: dp,
                out_dir=grade_dir, src_ts=tick.get("src_ts"),
                extra={**(extra or {}), "claim_tags": claim_tags,
                       "venue": tick.get("venue", "kalshi")})
            decision["captured"] = cap.get("status") == "captured"

        # A submitted maker quote is an honest paper fill only when THIS later
        # captured tick crossed it. The paper ledger is never touched at submit.
        # (ledger-row building + maker lifecycle branch -> inplay_daytrader_maker.py)
        if maker_event is not None:
            return handle_maker_event(maker_event, decision, position, tick,
                                       sport, game_id, MARKET, ledger_path)

        # 2b. SUPPRESSION (queue item 8a, conservative withhold -- mechanism only, currently
        # INERT: _SANCTIONED_ADVERSE_SEGMENTS is empty pending human authorization, see that
        # allowlist's docstring and docs/research/organization-sprint/
        # PROPOSED_soccer_inplay_suppression.md section 5/6, "human decision requested",
        # unresolved). Would-be sanctioned pairs are scoped SPORT+non-UNK-SEGMENT only; the
        # UNK bucket is hard-excluded in _segment_is_adverse regardless of allowlist state.
        # This only ever turns a would-be "bet" into "no_bet" -- it never manufactures a bet,
        # never claims an edge, and the pair captured above already ran regardless. Fail-open:
        # any trust-lookup exception -> _segment_is_adverse returns False -> unchanged behavior.
        if ev["action"] == "bet" and _segment_is_adverse(sport, tick):
            decision["reason"] = "segment_adverse_suppressed"
            return decision  # no_bet: captured above already ran; suppress the marginal entry

        # 2b2-2d. event-reactive / venue-allowlist / median-CLV-breaker suppression chain
        # -> inplay_daytrader_gates.apply_late_gates (suppress-only, fail-open; see that
        # function's docstring for the full per-gate rationale).
        if apply_late_gates(ev, tick, sport, nowdt, paper_venues, ledger_path, decision):
            return decision

        # 3. enter / hold / exit.
        if ev["action"] != "bet":
            return decision  # no_bet: captured (for grading) but nothing placed
        if position is not None and position.get("status") == "open":
            # HOLD only while the gated edge stays on the SAME side we already hold. If the
            # live edge has FLIPPED to the OTHER side (e.g. after a goal the market over-
            # reacts and the model now favours the opponent) and that side INDEPENDENTLY
            # clears the same gate (justified + liquid + fresh + tier floor), that is a
            # genuinely NEW +EV opportunity, not the same bet -> fall through and ENTER it.
            # The old position stays open and grades at settle; the new side is a distinct
            # edge_key, and the ledger's one-per-(game,side,day) idempotency BOUNDS this to
            # at most one position PER SIDE per day (so a thrashing tick stream cannot churn).
            if str(position.get("side")) == str(ev.get("side")):
                decision["action"] = "hold"  # same side -> HOLD, no new placement
                decision["reason"] = "hold_existing"
                return decision
            decision["reason"] = "edge_flipped_reenter"  # observable: a flip-side re-entry

        # ENTER: size (UNITS only) then paper-place (idempotent, executed=False) ->
        # inplay_daytrader_maker.enter_new_position (exec-gate + sizing + freshness +
        # maker-quote submission, verbatim logic, split out under the LOC rail).
        return enter_new_position(ev, tick, sport, game_id, nowdt, maker, mp, decision)
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
        "n_resting": sum(1 for d in decisions if d["action"] == "resting"),
        "n_holds": sum(1 for d in decisions if d["action"] == "hold"),
        "n_captured": sum(1 for d in decisions if d["captured"]),
        "position": pos,
        "units": "probability", "edge_claimed": False,
    }


__all__ = ["MARKET", "on_tick", "run_series", "grade"]
