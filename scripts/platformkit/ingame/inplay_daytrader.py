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
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.claims import condition_tagger as _tagger
from scripts.platformkit.execution import ingame_exec_gate as _exec_gate
from scripts.platformkit.execution import sizing as _sizing
from scripts.platformkit.ingame import ingame_clv_per_segment as _clvseg
from scripts.platformkit.ingame import ingame_segment_trust_multi as _trust_multi
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

# PAPER-DECISION venue allowlist: Kalshi-only for now. Gates ENTER/RE-ENTER ONLY --
# capture_pair_once's grade series stays venue-agnostic (unaffected). Override via env
# CV_PAPER_VENUES (comma-separated) or on_tick(paper_venues=..., tests only). A tick
# with no "venue" field defaults to "kalshi" (today's only wired price source; see
# inplay_capture_loop._default_inplay_fetch), not to a silent block.
DEFAULT_PAPER_VENUES = ("kalshi",)


def _paper_venue_allowlist() -> frozenset:
    """DEFAULT_PAPER_VENUES, overridable via CV_PAPER_VENUES (comma-separated). Never raises."""
    raw = os.environ.get("CV_PAPER_VENUES", "")
    if not raw.strip():
        return frozenset(v.lower() for v in DEFAULT_PAPER_VENUES)
    return frozenset(v.strip().lower() for v in raw.split(",") if v.strip())


def _venue_allowed(tick: LiveTick, paper_venues: Optional[Any]) -> bool:
    """True iff this tick's venue (default 'kalshi' -- see DEFAULT_PAPER_VENUES docstring)
    is in the effective allowlist (*paper_venues* override, else CV_PAPER_VENUES env,
    else DEFAULT_PAPER_VENUES)."""
    venue = str(tick.get("venue", "kalshi")).strip().lower()
    allowed = (frozenset(str(v).strip().lower() for v in paper_venues)
              if paper_venues is not None else _paper_venue_allowlist())
    return venue in allowed


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
            paper_venues: Optional[Any] = None) -> Dict[str, Any]:
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
                out_dir=grade_dir, extra={**(extra or {}), "claim_tags": claim_tags})
            decision["captured"] = cap.get("status") == "captured"

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

        # 2c. PAPER VENUE ALLOWLIST (binding: Kalshi-only paper decisions for now -- see
        # DEFAULT_PAPER_VENUES). Capture above already ran regardless -- this only ever
        # turns a would-be "bet" into "no_bet"; it never manufactures a bet.
        if ev["action"] == "bet" and not _venue_allowed(tick, paper_venues):
            decision["reason"] = "venue_not_allowed:%s" % str(tick.get("venue", "kalshi")).strip().lower()
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

        # ENTER: size (UNITS only) then paper-place (idempotent, executed=False).
        # Bet the side the (now two-sided) signal chose -- may be AWAY, not just home --
        # using THAT side's model prob + obtainable decimal. The grade pair captured above
        # stays home-aligned; only the placed bet's side/odds/prob reflect the chosen leg.
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
        placement = _paper.record_ingame_bet(
            sport, game_id, MARKET, bet_side, float(dec_odds),
            model_prob=bet_mp, stake=stake, path=ledger_path,  # units, never $
            signal_ts=tick.get("signal_ts"), exec_gate=gr["exec_gate"],
            exec_depth=gr["exec_depth"])
        decision.update({
            "action": "bet", "side": bet_side, "units": units, "placement": placement,
            "position": {"status": "open", "side": bet_side, "tier": ev["tier"],
                         "model_prob": bet_mp, "devigged_price": ev.get("bet_devigged_price", dp),
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
