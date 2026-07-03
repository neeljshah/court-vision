"""scripts.platformkit.ingame.inplay_capture_loop -- MEASUREMENT-ONLY in-play capture daemon (W4).

The thin live daemon that closes the in-play measurement loop end-to-end by WIRING the four
in-game pieces together -- it adds NO new prediction / pricing / sizing math, it only
ORCHESTRATES the existing, tested chain on a cadence:

  per LIVE game, per tick:
    1. live state  -> ingame_live_state.live_state(sport, gid) returns
       (state_diff, frac_elapsed, p0) where p0 is AUTO-SUPPLIED from the leak-free pregame
       snapshot (P1 wire) -- so the served / paired model_prob CARRIES THE PROVEN PRIOR
       instead of silently degrading to BASE.
    2. model prob  -> model_fn(sport, state) wraps predictor.predict_live (read-only),
       returning P(home win) computed from state-as-of-this-tick (leak-free).
    3. live price  -> inplay_kalshi.fetch_inplay(sport) (W2: series_ticker=KX<league>GAME)
       gives the LIQUID per-game YES(home)/YES(away) implied probs; an illiquid / untraded
       market emits NOTHING (is_liquid gate) so we never pair against a fake price.
    4. pair+decide -> inplay_daytrader.on_tick: ALWAYS captures the (model_prob, devigged
       price) pair via live_grade.capture_pair_once -> data/cache/ingame_grade/<sport>/
       <game_id>.jsonl, and paper-decides enter/hold/exit in UNITS (idempotent).
    5. on FINAL    -> settle_stamp.stamp_final appends the held-out binary home_win LABEL
       (W3) so inplay_aggregate_grade's OUTCOME arm can fire once >=5 games settle.

Each tick writes a HEARTBEAT envelope (stale-never-green: an operator can see liveness; a
down feed yields zero live games + a clean heartbeat, never a fabricated game). Error
ISOLATION: one bad game's failure never stops the others; one bad tick never stops the loop.

HONESTY (binding): MEASUREMENT ONLY. PAPER / UNITS / probability -- there is NO $ / roi /
pnl / stake$ field anywhere; edge_claimed is always False; executed is always False (the
real-money gate is a SEPARATE human flip, DEFAULT-DENY). The daemon NEVER executes real
money, NEVER flips a flag, NEVER arms autostart. It is supervised-READY (heartbeat) but NOT
auto-armed -- the supervisor manifest wiring ships as a PROPOSED diff only. Bounded runs
ALWAYS stop (max_ticks / clock injected in tests). LEAK-FREE: p0 is pregame; model_prob is
as-of-tick; the close is the held-out yardstick; the outcome is a label stamped only at FINAL.

INVARIANTS: build only under scripts/platformkit/ingame/; <=300 LOC; ASCII only; no network
at import; no data/registry write, no flag flip, no autostart; never edits
ingame_live_state / inplay_daytrader / settle_stamp / inplay_kalshi / predict_service /
domains / src / kernel (all REUSED through injectable callbacks).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_inplay_capture_loop.py -q
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.ingame import inplay_daytrader as _dt
from scripts.platformkit.ingame import ingame_live_state as _ls
from scripts.platformkit.ingame import ingame_segment_trust as _segment_trust
from scripts.platformkit.ingame import settle_stamp as _settle

logger = logging.getLogger(__name__)

# __file__ = scripts/platformkit/ingame/inplay_capture_loop.py -> parents[3] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRADE_DIR = _REPO_ROOT / "data" / "cache" / "ingame_grade"
DEFAULT_HEARTBEAT = _REPO_ROOT / "data" / "cache" / "ingame_grade" / "_capture_heartbeat.json"

# Sports that have BOTH a KX<league>GAME in-play series (W2) and a predict_live model.
DEFAULT_SPORTS: List[str] = ["mlb", "soccer_intl"]

# RELAXED in-game EV floor per sport (opt-in): the strict pre-registered floor (policy tier C
# = +0.02 EV, +0.01 proxy = +0.03) rarely fires in-game because the calibrated model tracks
# an efficient market. A lower floor surfaces genuine smaller divergences (e.g. right after a
# goal, before the market fully re-prices) as LOWER-CONFIDENCE, honestly-CLV-graded paper
# bets -- NOT an edge claim. None/absent -> strict floor. Soccer/WC = +1% EV.
# Opt-in relaxed in-game EV floor per sport (paper/measurement; CLV grades the truth, never
# a $ edge claim). In-game model-vs-market divergences are small, so the strict pre-registered
# +2%/+3% policy floor rejects almost everything -> the channel placed ~nothing. A modest
# relaxed floor surfaces the marginal in-game edges (tier C) so the CLV corpus actually fills.
# MLB added 2026-06-29 (was soccer-only) so in-game places across sports, not just the WC.
_INGAME_RELAXED_EV_FLOOR: Dict[str, float] = {
    "soccer_intl": 0.01, "soccer": 0.01, "mlb": 0.01}

# Phase-aware cadence (seconds): poll fast while in-play games are live, slow when quiet.
LIVE_INTERVAL_SEC = 20.0
IDLE_INTERVAL_SEC = 120.0

# Injectable callbacks (all default to the real chains; tests inject offline stubs so the
# tested path needs NO network / NO predictor corpus / NO venue):
#   live_state_fn(sport, gid) -> dict | None   (ingame_live_state.live_state; p0 auto-supplied)
#   model_fn(sport, state)    -> float | None  (predict_live P(home win) as-of this tick)
#   inplay_fetch_fn(sport)    -> [tick,...]    (inplay_kalshi.fetch_inplay liquid YES ticks)
#   finals_fn(sport)          -> [game,...]    (settled_finals.settled_since-style FINAL games)
LiveStateFn = Callable[[str, str], Optional[Dict[str, Any]]]
ModelFn = Callable[[str, Dict[str, Any]], Optional[float]]
InplayFetchFn = Callable[[str], List[Dict[str, Any]]]
FinalsFn = Callable[[str], List[Dict[str, Any]]]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _prob01(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if 0.0 <= v <= 1.0 else None


def _default_inplay_fetch(sport: str) -> List[Dict[str, Any]]:
    """Default production fetch: inplay_kalshi.fetch_inplay (W2 per-game series). [] on error."""
    try:
        from scripts.platformkit.odds_provider import inplay_kalshi as _ik
        return list(_ik.fetch_inplay(sport))
    except Exception as exc:  # noqa: BLE001 -- a feed error is never fatal
        logger.warning("inplay_capture_loop fetch failed sport=%s: %s", sport, exc)
        return []


def _default_finals(sport: str) -> List[Dict[str, Any]]:
    """Default FINAL-games provider: settled_finals.settled_since (carries home/away)."""
    try:
        from scripts.platformkit.ingame import settled_finals as _sf
        return list(_sf.settled_since(sport))
    except Exception as exc:  # noqa: BLE001 -- a dead feed -> no finals, never a crash
        logger.warning("inplay_capture_loop finals failed sport=%s: %s", sport, exc)
        return []


def _default_model_fn(sport: str, state: Dict[str, Any]) -> Optional[float]:
    """Default model: route predict_live through live_board's resolved predictor chain.

    READ-only on domains/<sport>/predictor.py. Returns P(home win) as-of this tick or None.
    The live in-game number this produces carries the pregame prior because the repricer is
    anchored to it (coherence) AND state['p0'] is the leak-free P1 prior. Network/corpus
    only here -- the tested path injects a stub instead.
    """
    try:  # pragma: no cover -- exercised only in the live smoke, never in the offline test
        from scripts.platformkit.frontend import live_board as _lb
        return _prob01(_lb.live_model_home_prob(sport, state))  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 -- no live model wired -> skip the pair cleanly
        logger.debug("inplay_capture_loop model_fn(%s) unavailable: %s", sport, exc)
        return None


def _yes_pair(ticks: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Group liquid Kalshi MONEYLINE ticks by game_id -> {home_yes, away_yes} implied probs.

    Each liquid moneyline tick is one team's YES(win) prob; we pair the two team markets of
    a game. The home/away label comes from the daemon's state match (the caller knows the
    home team), so here we just keep BOTH sides keyed by their side label tail for the caller
    to align. We return up to two probs per game; a single-sided game keeps just the one (the
    devig fills the complement). Never raises.

    MARKET_TYPE FILTER (binding): inplay_kalshi.fetch_inplay now ALSO returns total/spread/
    team_total ticks whose "prob" is P(over line) / P(covers), never a team win-prob. Mixing
    those into this win-prob pairing would silently corrupt model_prob-vs-price grading (the
    devig, the CLV ledger, the tail gate all assume a win-prob pair) -- so every row here is
    filtered to market_type=="moneyline" before pairing. A row missing market_type (older
    cached shape) is treated as moneyline for back-compat.
    """
    by_game: Dict[str, Dict[str, float]] = {}
    for t in ticks:
        if not isinstance(t, dict):
            continue
        mt = t.get("market_type")
        if mt is not None and str(mt) != "moneyline":
            continue
        gid = str(t.get("game_id") or "")
        p = _prob01(t.get("prob"))
        if not gid or p is None:
            continue
        slot = by_game.setdefault(gid, {})
        # Keep the first two distinct legs; the daemon aligns home/away via team names.
        side = str(t.get("side") or "yes")
        slot[side] = p
    return by_game


def _align_home_yes(home_name: str, away_name: str,
                    legs: Dict[str, float]) -> Optional[Dict[str, Optional[float]]]:
    """Pick the YES(home) / YES(away) implied probs from a game's liquid legs by team name.

    Matches each side label (e.g. 'NYY', 'Yankees') against the home / away abbreviation or
    name (case-insensitive substring, either direction). Returns {'yes_home','yes_away'} with
    yes_away possibly None (the devig fills the complement). None if neither leg matches home
    (we never guess the home side -- a misaligned pair manufactures fake CLV).
    """
    hn, an = home_name.strip().lower(), away_name.strip().lower()
    yes_home = yes_away = None
    for label, prob in legs.items():
        lab = str(label).strip().lower()
        if hn and (hn in lab or lab in hn):
            yes_home = prob
        elif an and (an in lab or lab in an):
            yes_away = prob
    if yes_home is None:
        return None
    return {"yes_home": yes_home, "yes_away": yes_away}


def _team_in_legs(team: str, legs: Dict[str, float]) -> bool:
    """True iff a team name aligns with some leg label (case-insensitive, either direction)."""
    t = str(team or "").strip().lower()
    if not t:
        return False
    return any(t in str(lab).strip().lower() or str(lab).strip().lower() in t
               for lab in legs)


def _scan_live_by_legs(sport: str, legs: Dict[str, float]) -> Optional[Dict[str, Any]]:
    """Bridge a Kalshi-keyed game to its ESPN live state by TEAM.

    The capture loop keys games by their Kalshi ticker (e.g. KXWCGAME-26JUN22ARGAUT), which
    never equals the ESPN numeric event id -> live_state(sport, ticker) always misses. This
    scans every in-progress ESPN game and returns the one whose BOTH teams align with the
    legs' team-name labels. BOTH must match: a single shared team (e.g. a live ARG-AUT vs a
    future JOR-ARG market) would otherwise mis-bind two different games. No full match ->
    None (the caller skips; a misaligned pair manufactures fake CLV). Never raises."""
    try:
        for st in _ls.live_states(sport):
            if not isinstance(st, dict):
                continue
            home = str(st.get("home_display") or st.get("home") or "")
            away = str(st.get("away_display") or st.get("away") or "")
            if _team_in_legs(home, legs) and _team_in_legs(away, legs):
                return st
    except Exception as exc:  # noqa: BLE001 -- a scan error is no match, never a crash
        logger.debug("inplay_capture_loop scan-by-legs(%s) failed: %s", sport, exc)
    return None


def _draw_leg(legs: Dict[str, float]) -> Optional[float]:
    """The draw/tie leg prob of a 3-way (soccer) market, or None for a 2-way market."""
    for label, prob in legs.items():
        lab = str(label).strip().lower()
        if lab in ("tie", "draw", "x") or "draw" in lab or "tie" in lab:
            return _prob01(prob)
    return None


def _fold_draw_into_field(pair: Dict[str, Optional[float]],
                          legs: Dict[str, float]) -> Dict[str, Optional[float]]:
    """Soccer is 3-way (home/draw/away); the day-trader prices a 2-way home-WIN binary.

    Fold the draw leg into the not-home complement so yes_home + yes_field has a real
    overround and the 2-way devig yields the correct fair P(home win) = home/(home+draw+
    away). A 2-way market (no draw leg) is unchanged. Never raises."""
    draw = _draw_leg(legs)
    if draw is None:
        return pair
    yes_away = (pair.get("yes_away") or 0.0) + draw
    return {"yes_home": pair.get("yes_home"), "yes_away": yes_away}


def _build_tick(state: Dict[str, Any], model_p: float,
                pair: Dict[str, Optional[float]]) -> Dict[str, Any]:
    """Assemble the LiveTick the day-trader's on_tick consumes (UNITS only, no $).

    calibration_justified=True iff the live state carries the PROVEN prior (p0_source in
    {CALLER, PRIOR, PRIOR_TEAMS}) -- PRIOR_TEAMS is the SAME leak-free pregame prior, resolved
    by a unique team match when the live/snapshot ids differ. A BASE-fallback (no pregame
    snapshot) lean is NOT prior-justified, so it is captured for the grade series but NEVER
    traded. is_liquid=True (the price came from the is_liquid-gated fetch). model_prob is
    as-of this tick (leak-free).
    """
    p0_src = str(state.get("p0_source") or "")
    return {
        "model_prob": model_p,
        "yes_home_prob": pair.get("yes_home"),
        "yes_away_prob": pair.get("yes_away"),
        "calibration_justified": p0_src in ("CALLER", "PRIOR", "PRIOR_TEAMS"),
        "is_liquid": True,   # the price already cleared inplay_kalshi.is_liquid upstream
        "is_fresh": True,    # in-play ticks are fresh by construction; stale feeds emit []
        "clv_is_proxy": True,
        # opt-in relaxed floor for this sport (None -> strict policy floor in evaluate),
        # routed through the CROSS-CORPUS segment-trust gate: a segment PROVEN worse than
        # the venue price across independent corpora reverts to the strict floor (suppress
        # its marginal relaxed bets); trusted/neutral/unknown keep the relaxed floor. The
        # gate acts ONLY on replicated proof and is reversible (CV_INGAME_SEGMENT_TRUST=0),
        # so thin/unreplicated data changes nothing -- do-no-harm.
        "min_ev_floor": _segment_trust.floor_for_segment(
            str(state.get("sport") or "").lower(), state,
            _INGAME_RELAXED_EV_FLOOR.get(str(state.get("sport") or "").lower())),
        # Pass the FULL resolved state through to the grade row's state_summary: the score,
        # the segment fields (inning/half/period/minute/clock) AND the DEEP MLB base-out
        # (outs/base/bos/re/count, game_pk) the resolver merges in.  The old 7-key projection
        # dropped all of these -> every captured tick logged a bare "live".  These keys feed
        # ONLY live_grade._state_summary (the label); model/price/sizing read top-level tick
        # fields, so widening this is label-only and cannot change a decision.
        "state": {k: state.get(k) for k in (
            "home", "away", "state_diff", "frac_elapsed", "status", "p0", "p0_source",
            "home_score", "away_score", "inning", "half", "period", "minute", "clock",
            "outs", "base", "bos", "re", "count", "pitch_count", "tto",
            "game_pk") if k in state},
    }


def poll_once(*, sports: Optional[List[str]] = None,
              live_state_fn: Optional[LiveStateFn] = None,
              model_fn: Optional[ModelFn] = None,
              inplay_fetch_fn: Optional[InplayFetchFn] = None,
              finals_fn: Optional[FinalsFn] = None,
              deep_state_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
              grade_dir: Optional[Path] = None,
              ledger_path: Optional[Path] = None,
              heartbeat_path: Optional[Path] = None,
              positions: Optional[Dict[str, Dict[str, Any]]] = None,
              now: Optional[datetime] = None) -> Dict[str, Any]:
    """ONE measurement tick across *sports*: capture pairs, paper-decide, stamp finals.

    Reuses the existing chain end-to-end via injectable callbacks (default to the real ones).
    *positions* threads each game's open paper position across ticks (None -> fresh). Returns
    a heartbeat dict and writes it to disk (stale-never-green). UNITS only -- no $. Never raises.
    """
    sport_list = list(sports) if sports else list(DEFAULT_SPORTS)
    ls_fn = live_state_fn or (lambda s, g: _ls.live_state(s, g))
    md_fn = model_fn or _default_model_fn
    fetch_fn = inplay_fetch_fn or _default_inplay_fetch
    fin_fn = finals_fn or _default_finals
    pos_map = positions if positions is not None else {}
    nowdt = now or datetime.now(timezone.utc)

    n_live = n_pairs = n_bets = n_settled = 0
    games_seen: List[Dict[str, Any]] = []

    for sport in sport_list:
        try:
            ticks = fetch_fn(sport)
        except Exception as exc:  # noqa: BLE001 -- a feed error never sinks the tick
            logger.warning("inplay_capture_loop fetch error %s: %s", sport, exc)
            ticks = []
        legs_by_game = _yes_pair(list(ticks) if ticks else [])
        # DEEP enrichment is MLB-only (the base-out resolver); other sports pass through.
        sport_deep_fn = deep_state_fn if str(sport).lower() == "mlb" else None
        for gid, legs in legs_by_game.items():
            row = _process_game(sport, gid, legs, ls_fn, md_fn, pos_map,
                                grade_dir, ledger_path, nowdt, sport_deep_fn)
            games_seen.append(row)
            if row.get("paired"):
                n_live += 1
                n_pairs += 1
            if row.get("bet"):
                n_bets += 1
        # FINAL stamps (W3): append the held-out home_win label so the OUTCOME arm can fire.
        try:
            finals = fin_fn(sport)
        except Exception as exc:  # noqa: BLE001 -- finals failure never sinks the tick
            logger.warning("inplay_capture_loop finals error %s: %s", sport, exc)
            finals = []
        for g in finals or []:
            if _stamp_final(sport, g, grade_dir, nowdt):
                n_settled += 1

    heartbeat = {
        "as_of": _utc_iso(), "sports": sport_list, "n_live": n_live,
        "n_pairs": n_pairs, "n_bets": n_bets, "n_settled": n_settled,
        "games": games_seen, "measurement_only": True, "executed": False,
        "edge_claimed": False, "units": "probability",
        "_honest_note": (
            "In-play capture daemon heartbeat. Captures (model,devigged-price) pairs + paper "
            "UNIT decisions + settle labels; NO real money, NO flag flip, NO autostart. A down "
            "feed yields zero live games, never a fabricated one. CLV/outcome graded downstream."
        ),
    }
    _write_heartbeat(heartbeat, heartbeat_path)
    return heartbeat


def _process_game(sport: str, gid: str, legs: Dict[str, float],
                  ls_fn: LiveStateFn, md_fn: ModelFn,
                  pos_map: Dict[str, Dict[str, Any]],
                  grade_dir: Optional[Path], ledger_path: Optional[Path],
                  nowdt: datetime,
                  deep_state_fn: Optional[Callable[[str], Dict[str, Any]]] = None
                  ) -> Dict[str, Any]:
    """Capture + paper-decide ONE live game's tick. Per-game guarded: never raises."""
    row: Dict[str, Any] = {"sport": sport, "game_id": gid, "paired": False,
                           "bet": False, "reason": ""}
    try:
        state = ls_fn(sport, gid)
        if not isinstance(state, dict):
            # gid is a Kalshi ticker, not an ESPN id -> bridge to the live game by team.
            state = _scan_live_by_legs(sport, legs)
        if not isinstance(state, dict):
            row["reason"] = "no_live_state"
            return row
        state.setdefault("sport", sport)  # segment-trust floor lookup needs the sport
        # DEEP base-out enrichment (MLB): resolve gid (Kalshi ticker) -> statsapi gamePk ->
        # authoritative linescore base-out, MERGED onto the ESPN-resolved state so the active
        # series carries outs/base/bos/re/count + game_pk every tick (additive; never raises).
        if deep_state_fn is not None:
            try:
                deep = deep_state_fn(gid)
                if isinstance(deep, dict) and deep:
                    state = {**state, **deep}
            except Exception as exc:  # noqa: BLE001 -- deep state is additive, never fatal
                logger.debug("inplay_capture_loop deep(%s/%s) failed: %s", sport, gid, exc)
        model_p = _prob01(md_fn(sport, state))
        if model_p is None:
            row["reason"] = "no_model_prob"
            return row
        pair = _align_home_yes(str(state.get("home_display") or state.get("home") or ""),
                               str(state.get("away_display") or state.get("away") or ""), legs)
        if pair is None:
            row["reason"] = "no_home_leg"
            return row
        pair = _fold_draw_into_field(pair, legs)  # 3-way (soccer) -> 2-way home-vs-field
        tick = _build_tick(state, model_p, pair)
        pkey = "%s/%s" % (sport, gid)
        dec = _dt.on_tick(sport, gid, tick, position=pos_map.get(pkey),
                          now=nowdt, grade_dir=grade_dir, ledger_path=ledger_path)
        pos_map[pkey] = dec.get("position")
        row.update({
            "paired": bool(dec.get("captured")), "bet": dec.get("action") == "bet",
            "action": dec.get("action"), "tier": dec.get("tier"),
            "model_prob": model_p, "devigged_price": _devig_of(tick),
            "p0_source": state.get("p0_source"), "reason": dec.get("reason") or "ok",
        })
        # SHADOW MEASUREMENT ONLY, added AFTER dec is final -- never read by on_tick.
        row["model_prob_sp_shadow"] = _sp_shadow(sport, state.get("home_display") or state.get("home"),
            state.get("away_display") or state.get("away"), model_p, state.get("game_pk"))
    except Exception as exc:  # noqa: BLE001 -- one bad game never stops the others
        logger.warning("inplay_capture_loop game %s/%s failed: %s", sport, gid, exc)
        row["reason"] = "error:%s" % type(exc).__name__
    return row


def _sp_shadow(sport: str, home: Any, away: Any, model_p: float, game_pk: Any = None) -> Optional[float]:
    """SHADOW MEASUREMENT ONLY (logged, never decided on). All logic lives in
    ingame_sp_shadow.py; this wrapper only guarantees an exception here can never reach
    the capture path. None-safe."""
    try:
        from scripts.platformkit.ingame.ingame_sp_shadow import get_shadow
        return get_shadow().shadow_prob(sport, str(home or ""), str(away or ""), model_p,
                                        int(game_pk) if game_pk is not None else None)
    except Exception:  # noqa: BLE001 -- shadow measurement never affects the capture path
        return None


def _devig_of(tick: Dict[str, Any]) -> Optional[float]:
    """The no-vig fair P(home) for the heartbeat readout (reuses the signal's devig). None-safe."""
    try:
        from scripts.platformkit.ingame import inplay_edge_signal as _sig
        return _sig.devig_home_price(tick.get("yes_home_prob"), tick.get("yes_away_prob"))
    except Exception:  # noqa: BLE001
        return None


def _stamp_final(sport: str, game: Dict[str, Any],
                 grade_dir: Optional[Path], nowdt: datetime) -> bool:
    """Stamp a FINAL game's held-out home_win label (W3). True iff a fresh stamp landed."""
    try:
        gid = str(game.get("game_id") or "")
        if not gid:
            return False
        res = _settle.stamp_final(sport, gid, ev=game.get("event") or game,
                                  home_win=game.get("home_win"),
                                  now=nowdt, grade_dir=grade_dir)
        return res.get("status") == "stamped"
    except Exception as exc:  # noqa: BLE001 -- a stamp failure never sinks the loop
        logger.warning("inplay_capture_loop stamp %s failed: %s", sport, exc)
        return False


def _write_heartbeat(heartbeat: Dict[str, Any], heartbeat_path: Optional[Path]) -> None:
    """Best-effort heartbeat write (reuses live_grade's atomic .tmp+replace discipline)."""
    try:
        import json
        from scripts.platformkit.ingame import live_grade as _lg
        path = Path(heartbeat_path) if heartbeat_path is not None else DEFAULT_HEARTBEAT
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(heartbeat, ensure_ascii=True))
        import os
        os.replace(str(tmp), str(path))
        _ = _lg  # keep the import meaningful (same atomic discipline family)
    except Exception as exc:  # noqa: BLE001 -- heartbeat is observability, not critical
        logger.warning("inplay_capture_loop heartbeat write failed: %s", exc)


def _make_mlb_deep_fn(deep_state_fn: Optional[Callable[[str], Dict[str, Any]]]
                      ) -> Optional[Callable[[str], Dict[str, Any]]]:
    """Build the per-tick MLB deep-state enricher (LAZY: no candidate fetch until a game
    actually needs enriching, so a dead-feed tick stays offline).  An explicit
    deep_state_fn wins (tests inject an offline stub); otherwise the real statsapi resolver.
    Returns None if the resolver cannot be imported -- enrichment is then simply skipped."""
    if deep_state_fn is not None:
        return deep_state_fn
    try:
        from scripts.platformkit.ingame import ingame_id_resolver_mlb as _res
        return _res.make_tick_deep_fn()
    except Exception as exc:  # noqa: BLE001 -- no resolver -> shallow capture, never a crash
        logger.debug("inplay_capture_loop deep enricher unavailable: %s", exc)
        return None


def serve_forever(interval: Optional[float] = None, *,
                  clock: Optional[Callable[[float], None]] = None,
                  max_ticks: Optional[int] = None,
                  sports: Optional[List[str]] = None,
                  live_state_fn: Optional[LiveStateFn] = None,
                  model_fn: Optional[ModelFn] = None,
                  inplay_fetch_fn: Optional[InplayFetchFn] = None,
                  finals_fn: Optional[FinalsFn] = None,
                  mlb_deep: bool = False,
                  deep_state_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
                  grade_dir: Optional[Path] = None,
                  ledger_path: Optional[Path] = None,
                  heartbeat_path: Optional[Path] = None) -> int:
    """Drive poll_once on a cadence until *max_ticks* (or forever). Returns ticks executed.

    BOUNDED runs ALWAYS stop (max_ticks). *clock* is injectable so the tested path NEVER
    calls time.sleep. Positions are threaded across ticks. Never raises on a per-tick error.

    *mlb_deep* (default OFF) enables the statsapi base-out enricher so the captured MLB
    series carries the deep in-game state every tick; the production runner turns it ON.
    The enricher is rebuilt per tick (fresh live candidates) and LAZY (no fetch on a tick
    with no MLB game to enrich), so leaving it OFF -- or running with a dead feed -- needs
    no network.  *deep_state_fn* injects an offline enricher for the tested path.
    """
    sleep = clock if clock is not None else time.sleep
    positions: Dict[str, Dict[str, Any]] = {}
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        # Fresh per-tick enricher so the live candidate set tracks the slate (LAZY: built
        # only when mlb_deep is on; no candidate fetch until a real MLB game is enriched).
        tick_deep_fn = _make_mlb_deep_fn(deep_state_fn) if mlb_deep else None
        try:
            hb = poll_once(sports=sports, live_state_fn=live_state_fn, model_fn=model_fn,
                           inplay_fetch_fn=inplay_fetch_fn, finals_fn=finals_fn,
                           deep_state_fn=tick_deep_fn,
                           grade_dir=grade_dir, ledger_path=ledger_path,
                           heartbeat_path=heartbeat_path, positions=positions)
        except Exception as exc:  # noqa: BLE001 -- a tick error never stops the loop
            logger.warning("inplay_capture_loop tick error: %s", exc)
            hb = {"n_live": 0}
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            break
        wait = float(interval) if interval is not None else (
            LIVE_INTERVAL_SEC if hb.get("n_live") else IDLE_INTERVAL_SEC)
        try:
            sleep(wait)
        except Exception as exc:  # noqa: BLE001 -- a clock error never sinks the loop
            logger.warning("inplay_capture_loop sleep error: %s", exc)
    return ticks


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: a BOUNDED measurement run (default 1 tick). NOT auto-armed -- explicit invocation."""
    import argparse
    ap = argparse.ArgumentParser(prog="inplay_capture_loop")
    ap.add_argument("--max-ticks", type=int, default=1, help="bounded ticks (default 1)")
    ap.add_argument("--interval", type=float, default=None, help="poll interval seconds")
    ap.add_argument("--sports", default=",".join(DEFAULT_SPORTS), help="comma sports")
    args = ap.parse_args(argv)
    n = serve_forever(interval=args.interval, max_ticks=args.max_ticks,
                      sports=[s.strip() for s in args.sports.split(",") if s.strip()])
    print("inplay_capture_loop ran %d tick(s); measurement-only, paper, no $." % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_GRADE_DIR", "DEFAULT_SPORTS", "LIVE_INTERVAL_SEC", "IDLE_INTERVAL_SEC",
    "poll_once", "serve_forever",
]
