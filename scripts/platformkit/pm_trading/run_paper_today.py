"""scripts.platformkit.pm_trading.run_paper_today -- PAPER trader on TODAY's slate.

Pulls today's REAL games + state (live_board.todays_live_games for ESPN-covered
sports; kalshi_listing.todays_kalshi_games -- PREGAME ONLY -- for npb/kbo, which
have no ESPN scoreboard; see default_live_fetch), builds each game's bet board
(bet_board.game_bet_board) priced off the aggregated odds slate, and:
  * PRICED row (real book price, mainly moneyline) -> EV, POLICY TIER + STAKE UNITS
    via pm_trading.policy; below-floor (tier None) rows skipped. RECORD to the CLV
    ledger (clv_ledger.record_bet) executed=False/channel="paper" for later settling.
  * UNPRICED row (derived markets) -> never fabricate a price; LOG the model view +
    a closing-line PROXY target to data/frontend/paper_predictions.jsonl for grading.

HONEST RAILS (binding -- can NEVER move real money): every ledger row is
executed=False / channel="paper"; policy tiers gate below-floor picks (tier=None);
each recorded row carries tier + flat_unit + quarter_kelly units (NOT dollars);
idempotent per MARKET (sport, matchup, line, day) -- only the model-backed side of a
symmetric two-way market records, never both; markets are efficient --
NO $ edge claimed. <=300 LOC; no secrets; no network in tests. Pure helpers + Ctx
live in the sibling paper_today_support module.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.execution import expected_clv_gate as _exec_gate
from scripts.platformkit.execution.thresholds import INGAME_EXPECTED_CLV_MIN_PCT
from scripts.platformkit.claims import condition_tagger as _tagger
from scripts.platformkit.frontend.bet_board import game_bet_board
from scripts.platformkit.frontend.live_board import todays_live_games
from scripts.platformkit.odds_provider.base import OddsEvent
from scripts.platformkit.odds_provider.kalshi_listing import todays_kalshi_games
from scripts.platformkit.eval_gate.shin import shin_devig_decimal
from scripts.platformkit.odds_shop import devig_twoway, ev_vs_price
from scripts.platformkit.pm_trading.paper_autobet import (
    AutoBetConfig, CHANNEL_PAPER)
from scripts.platformkit.pm_trading import paper_today_support as S
from scripts.platformkit.pm_trading import mlb_dh_stamp as _dh
from scripts.platformkit.pm_trading.paper_today_support import (
    Ctx, DEFAULT_PREDICTIONS, DEFAULT_SPORTS, PAPER_EV_FLOOR)

# Sports with NO ESPN scoreboard (live_board._ESPN_ROUTES has no entry) but a
# real Kalshi GAME-series listing (LANE 4): route these through the Kalshi
# ticker listing instead -- PREGAME ONLY (no live clock/score, no in-game
# model; see kalshi_listing.py module docstring). Additive: every other sport
# is UNCHANGED (still routes through todays_live_games/ESPN).
_KALSHI_LISTING_SPORTS = frozenset({"npb", "kbo"})

# Pregame execution-quality floor: reuse the SAME pre-registered expected-CLV bar
# as the in-game channel (thresholds.py, registered 2026-07-15, BEFORE measurement)
# -- one execution-quality bar across channels, not tuned post-hoc. Mirrors
# inplay_daytrader's use of expected_clv_gate.gate; here fair_prob = the calibrated
# model prob (the model IS the fair-value estimate). SUPPRESS-ONLY: an additional
# lower net below the EV floor + policy tier already applied; never loosens them.
# NOTE: ev_vs_price and expected_clv_pct are the SAME quantity (p*price-1), and the
# policy tier-C floor (ev>=0.02 = 2.0%) is STRICTER than this 1.0% floor, so under
# the current policy config the tier gate always dominates and this block never
# independently fires -- it is a genuine lower net that only activates if a future
# policy loosens the tier floors below 1%. The STAMP (exec_gate/latency on every
# placed row) is the load-bearing effect for the m44 exec-evidence reader.
_PREGAME_EXPECTED_CLV_MIN_PCT = INGAME_EXPECTED_CLV_MIN_PCT


def default_live_fetch(sport: str) -> Dict[str, Any]:
    """live_fetch dispatcher: ESPN-backed sports -> todays_live_games (ticks +
    in-game state); Kalshi-listing-only sports (npb/kbo, no ESPN feed) ->
    todays_kalshi_games (pregame listing only). Never raises."""
    if sport.lower() in _KALSHI_LISTING_SPORTS:
        return todays_kalshi_games(sport)
    return todays_live_games(sport)

# Policy tiering -- guarded so a missing import never breaks the paper cycle.
try:
    from scripts.platformkit.pm_trading import policy as _policy
    _POLICY_AVAILABLE = True
except Exception:  # noqa: BLE001
    _policy = None  # type: ignore[assignment]
    _POLICY_AVAILABLE = False

logger = logging.getLogger(__name__)

try:  # predict_service.store: canonical envelope source for board_fn
    from predict_service import store as _ps_store
except Exception:  # pragma: no cover - optional
    _ps_store = None


def make_store_board_fn(sport: str) -> Callable[..., Dict[str, Any]]:
    """Return a board_fn that reads from predict_service.store for *sport*.

    Same signature/shape as game_bet_board; falls back to game_bet_board when the store
    envelope is unavailable or the game is not found. NEVER raises.
    """
    env = None
    if _ps_store is not None:
        try:
            _env = _ps_store.read_latest(sport)
            if _env.status == "ok" and _env.predictions:
                env = _env
        except Exception:  # noqa: BLE001
            pass

    def _board_fn(sp: str, home: str, away: str,
                  odds_lookup: Any = None, live: Any = None,
                  **kw: Any) -> Dict[str, Any]:
        if env is not None:
            h_low, a_low = home.lower(), away.lower()
            for pred in env.predictions:
                if pred.home.lower() == h_low and pred.away.lower() == a_low:
                    rows = [{"group": "pregame", "selection": side,
                             "model_prob": prob, "best_price": None,
                             "best_book": None, "line": None, "fair_odds": None}
                            for side, prob in pred.pregame_probs.items()]
                    # Attach market prices from matching EdgeRows
                    emap = {e.side: e for e in env.edges
                            if e.game_id == pred.game_id}
                    for row in rows:
                        er = emap.get(row["selection"])
                        if er is not None and er.ev is not None:
                            row["best_price"] = round(1.0 / er.market_prob, 4) \
                                if er.market_prob else None
                            row["best_book"] = er.book
                    return {"sport": sp, "home": home, "away": away,
                            "status": "ok", "best_bets": rows, "groups": rows,
                            "served_from": "predict_service_store"}
        # Fallback: live bet_board (default behavior unchanged)
        return game_bet_board(sp, home, away, odds_lookup=odds_lookup,
                              live=live, **kw)

    return _board_fn


def _policy_tier_and_stake(ev: float, model_prob: float, price: float,
                            market_prob: Optional[float],
                            clv_is_proxy: bool = False,
                            ) -> Tuple[Optional[str], float, float]:
    """(tier, flat_unit, quarter_kelly); fallback to permissive if policy absent."""
    if _POLICY_AVAILABLE and _policy is not None:
        t = _policy.tier(ev=ev, model_prob=model_prob, market_prob=market_prob,
                         clv_is_proxy=clv_is_proxy)
        s = _policy.stake_units(ev=ev, model_prob=model_prob,
                                taken_decimal=price, tier=t,
                                clv_is_proxy=clv_is_proxy)
        return t, s["flat_unit"], s["quarter_kelly"]
    t_fb: Optional[str] = "C" if ev > 0.0 else None
    return t_fb, (1.0 if t_fb else 0.0), 0.0


def _record_priced(row, sport, matchup, meta, side, price, prob, selection,
                   ctx: Ctx, home: str = "", away: str = "") -> Optional[Dict[str, Any]]:
    """Record a priced two-way pick as a paper bet. None if dedup/below-floor.

    ONE POSITION PER MARKET: a symmetric two-way market (home ML AND away ML) must NOT
    record both sides (flat-staking both is nonsensical -- win/loss cancel minus vig --
    and double-counts as two bets). We record only the MODEL-BACKED side (model_prob
    >= 0.5) and dedup per market (sport, matchup, line, day), NOT per side, so the
    opposing side cannot also land. A distinct market (different line) keeps its key.
    """
    _t0 = time.perf_counter()  # placement-path latency clock (stamped in ms below)
    market_key = (sport, matchup, row.get("line"), ctx.day)
    if market_key in ctx.ledger_keys or float(prob) < 0.5:
        return None  # already placed this market, or the side the model does not back
    ev = ev_vs_price(prob, price)
    if ev <= PAPER_EV_FLOOR:
        return None
    book = row.get("best_book") or "aggregate"

    # Policy gate: tier + dual-stake units (no $/dollar fields)
    market_prob: Optional[float] = row.get("market_prob")
    clv_is_proxy: bool = bool(row.get("clv_is_proxy", False))
    tier_label, flat_unit, quarter_kelly = _policy_tier_and_stake(
        ev, float(prob), float(price), market_prob, clv_is_proxy)
    # Below-floor (tier None) -> do not place this paper record.
    if tier_label is None:
        return None

    # UNITS-ONLY STAKE (the accuracy fix): stake at exactly the policy flat_unit (1.0
    # for any tiered bet), NOT the legacy dollar-Kelly size_stake magnitude that leaked
    # in as stake_units and produced e.g. -500u losses. unit_result then settles in
    # [-1, dec-1] and the bankroll curve reconciles. quarter_kelly is a measurement
    # field only (never the staked magnitude here).
    stake_units = float(flat_unit)  # 1.0 for any A/B/C tier, else 0.0 (already gated)
    # additive claim tags (TAG ONLY, zero behavior change): as-of state at this call
    # site is whatever's already in row/meta -- a card whose trigger needs a field not
    # present here just tags False, never errors (see condition_tagger.tag).
    try:
        claim_tags = _tagger.tag({**row, **meta}, "pregame")
    except Exception:  # noqa: BLE001
        claim_tags = {}
    # D6 fix: MLB doubleheader-date exposure -- stamp game_number/game_pk at
    # placement time so a DH day can be disambiguated at settle time. {} (no
    # stamp) on any non-mlb sport, unresolved lookup, or genuine ambiguity --
    # fail-closed, never guessed; historical rows are untouched.
    dh_stamp: Dict[str, Any] = {}
    if sport == "mlb" and ctx.dh_stamp_fn is not None:
        dh_stamp = ctx.dh_stamp_fn(home, away, ctx.day, meta.get("commence_time")) or {}
    # Execution-quality gate (pregame twin of inplay_daytrader's exec_gate). fair_prob
    # = calibrated model prob. BLOCK on gate fail -> mirror the in-game SUPPRESS policy
    # (an additional lower net below the EV floor + tier above). CRASH-SAFE: a gate
    # error records the row UNGATED with an exec_gate_error note, never blocks m1_paper.
    exec_gate: Optional[Dict[str, Any]] = None
    exec_gate_error: Optional[str] = None
    try:
        exec_gate = _exec_gate.gate(taken_decimal=float(price), fair_prob=float(prob),
                                    threshold_pct=_PREGAME_EXPECTED_CLV_MIN_PCT)
        if not exec_gate.get("passed", False):
            return None  # below expected-CLV floor -> suppress (mirror in-game)
    except Exception as exc:  # noqa: BLE001 -- gate must NEVER block a placement row
        exec_gate, exec_gate_error = None, type(exc).__name__
    placement_latency_ms = (time.perf_counter() - _t0) * 1000.0
    saved = _clv.record_bet(sport, matchup, side, book, float(price),
                            model_prob=float(prob), stake_units=stake_units,
                            event_id=meta["event_id"],
                            game_number=dh_stamp.get("game_number"),
                            game_pk=dh_stamp.get("game_pk"), path=ctx.lpath,
                            claim_tags=claim_tags, exec_gate=exec_gate,
                            placement_latency_ms=placement_latency_ms,
                            exec_gate_error=exec_gate_error)
    assert saved["executed"] is False  # honesty invariant, belt-and-braces
    assert float(saved.get("stake_units", 0.0)) == stake_units  # units, never $
    ctx.ledger_keys.add(market_key)
    bet_row = {
        "sport": sport, "matchup": matchup, "selection": selection, "side": side,
        "model_prob": round(float(prob), 6), "price": round(float(price), 4),
        "book": book, "ev_pct": round(ev * 100.0, 3),
        "stake_units": round(stake_units, 6),
        "would_pass_real_gate": False,  # paper-only; real money stays default-DENY
        "executed": False, "channel": CHANNEL_PAPER, "event_id": meta["event_id"],
        "commence_time": meta["commence_time"],
        # Policy stamps: tier + unit sizing (NOT dollars)
        "tier": tier_label, "flat_unit": flat_unit,
        "quarter_kelly": round(quarter_kelly, 8),
        "claim_tags": claim_tags,
    }
    if dh_stamp.get("game_number") is not None:
        bet_row["game_number"] = dh_stamp["game_number"]
    if dh_stamp.get("game_pk") is not None:
        bet_row["game_pk"] = dh_stamp["game_pk"]
    return {"kind": "bet", "row": bet_row, "stake_units": stake_units}


def _log_unpriced(row, sport, matchup, home, away, meta, close, prob, selection,
                  ctx: Ctx, *, draw: Optional[float] = None
                  ) -> Optional[Dict[str, Any]]:
    """Log an unpriced model prediction + closing-line proxy. None if deduped.

    *draw* is the captured draw-leg decimal (soccer 1X2 only; None for every
    two-way sport, unchanged behavior). When present, devigs all THREE legs
    together (see PROPOSED_soccer_1x2_close_proxy_devig.md) instead of the
    two-way devig -- stripping the draw leg out first would leave a booksum<1
    remainder that the Shin arb guard rejects on every single soccer row.
    """
    # event day, NOT log day (see prediction_event_day); unresolved event_id
    # falls back to ctx.day, exactly matching the pre-fix behavior for that case.
    event_day = S.prediction_event_day(meta, fallback_day=ctx.day)
    pred_key = (sport, matchup, str(selection), event_day)
    if pred_key in ctx.pred_keys:
        return None
    proxy, side = None, S.side_of(selection, home, away)
    if close is not None and side is not None:
        proxy = {"close_decimal_home": round(close[0], 4),
                 "close_decimal_away": round(close[1], 4), "fair_close_prob": None}
        if draw is not None:
            proxy["close_decimal_draw"] = round(draw, 4)
        try:  # devig only when the line is a real vigged book (booksum>=1)
            if draw is not None:
                probs, _z = shin_devig_decimal([close[0], draw, close[1]])
                fh, fa = probs[0], probs[2]  # order matches [home, draw, away]
            else:
                if (1.0 / close[0] + 1.0 / close[1]) < 1.0 - 1e-9:
                    # booksum<=1: devig_twoway now normalizes instead of raising
                    # (634fdd1a); a degenerate proxy must keep fair=None as before.
                    raise ValueError("degenerate close pair")
                fh, fa = devig_twoway(close[0], close[1])
            proxy["fair_close_prob"] = round(fh if side == "home" else fa, 6)
        except Exception:  # noqa: BLE001 -- arb/degenerate proxy -> fair stays None
            pass
    pred = {
        "logged_at": S.now_iso(), "sport": sport, "matchup": matchup,
        "group": row.get("group"), "selection": selection,
        "model_prob": round(float(prob), 6), "line": row.get("line"),
        "fair_odds": row.get("fair_odds"), "price": None, "close_proxy": proxy,
        "would_pass_real_gate": False, "executed": False, "channel": CHANNEL_PAPER,
        "event_id": meta["event_id"], "commence_time": meta["commence_time"],
        "note": "model view, no tradeable book price; logged for accuracy/CLV grading",
    }
    S.log_prediction(pred, path=ctx.ppath)
    ctx.pred_keys.add(pred_key)
    return {"kind": "prediction", "row": pred}


def _handle_row(row, sport, matchup, home, away, meta, close, ctx: Ctx, *,
                draw: Optional[float] = None,
                game_state: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Record a priced two-way row as a paper bet, else log a model prediction.

    *game_state* gates the PREGAME-PREDICTION path only (_log_unpriced):
    a game not in state 'pre' skips it -- a finished game re-appearing on the
    feed must never re-log as a "fresh" pregame model view (see LANE 4
    prediction-logger-hygiene fix). The priced-bet path (_record_priced) is
    the DESIGNED whole-slate in-game/CLV logging behavior and is UNCHANGED --
    it never checks game_state.
    """
    prob, selection = row.get("model_prob"), row.get("selection")
    if not isinstance(prob, (int, float)) or prob <= 0.0 or prob >= 1.0:
        return None
    price, side = row.get("best_price"), S.side_of(selection, home, away)
    # A priced two-way row belongs to the BET path exclusively (recorded, or
    # skipped on dedup / below the permissive EV floor) -- never also logged.
    if price is not None and side is not None:
        return _record_priced(row, sport, matchup, meta, side, price, prob,
                              selection, ctx, home=home, away=away)
    if game_state is not None and game_state != "pre":
        return None  # not a pregame model view -- never log a stale/finished one
    return _log_unpriced(row, sport, matchup, home, away, meta, close, prob,
                         selection, ctx, draw=draw)


def _market_ledger_keys(rows: Sequence[Dict[str, Any]]) -> set:
    """Per-MARKET (sport, matchup, line, day) keys already in the CLV ledger.

    The placement dedup is now per market, NOT per side (S.ledger_keys keys on side and
    would let both sides of a symmetric two-way market record). One market that already
    has a placed side blocks the opposing side from also landing.
    """
    out: set = set()
    for r in rows:
        day = str(r.get("settled_at") or r.get("ts") or "")[:10]
        out.add((str(r.get("sport")), str(r.get("matchup")), r.get("line"), day))
    return out


def run_paper_cycle(
    sports: Sequence[str] = DEFAULT_SPORTS,
    ledger_path: Optional[Path] = None,
    *,
    predictions_path: Optional[Path] = None,
    cfg: Optional[AutoBetConfig] = None,
    live_fetch: Callable[..., Dict[str, Any]] = default_live_fetch,
    board_fn: Callable[..., Dict[str, Any]] = game_bet_board,
    odds_index: Callable[[str], Tuple[Any, List[OddsEvent]]] = S.odds_index,
    dh_stamp_fn: Callable[..., Dict[str, Any]] = _dh.mlb_dh_stamp,
) -> Dict[str, Any]:
    """Run one PAPER cycle on TODAY's real slate across *sports*.

    Pulls each sport's games + state, builds each priced bet board, RECORDS priced
    picks to the CLV ledger (executed=False, channel="paper") and LOGS unpriced model
    predictions. Idempotent per MARKET (sport, matchup, line, day) for placed bets (only
    the model-backed side of a symmetric two-way market records, never both) and per
    (sport, matchup, selection, day) for predictions. Never raises on a bad game/sport.
    """
    lpath = Path(ledger_path) if ledger_path is not None else _clv.DEFAULT_LEDGER
    ppath = Path(predictions_path) if predictions_path is not None else DEFAULT_PREDICTIONS
    ctx = Ctx(cfg=cfg or AutoBetConfig(), day=S.today_key(), lpath=lpath, ppath=ppath,
              ledger_keys=_market_ledger_keys(_clv.load_ledger(lpath)),
              pred_keys=S.prediction_keys(S.load_predictions(ppath)),
              dh_stamp_fn=dh_stamp_fn)

    out: Dict[str, Any] = {
        "as_of": S.now_iso(), "channel": CHANNEL_PAPER, "executed_any": False,
        "day": ctx.day, "sports": {}, "bets": [], "predictions": [],
        "n_recorded": 0, "n_logged": 0, "staked_total_units": 0.0,
        "honest_note": ("PAPER measurement only -- executed=False, channel=paper, "
                        "no real orders, no $ edge claimed. Markets efficient."),
    }
    staked = 0.0
    for sport in sports:
        s = sport.lower()
        try:
            live = live_fetch(s)
        except Exception as exc:  # noqa: BLE001
            out["sports"][s] = {"status": "error", "note": str(exc)}
            continue
        games = live.get("games") or []
        if not games:
            out["sports"][s] = {"status": live.get("status", "no_games"),
                                "n_games": 0, "note": live.get("note", "no games today")}
            continue
        lookup, events = odds_index(s)
        n_rec = n_log = 0
        for g in games:
            home, away = g.get("home"), g.get("away")
            if not home or not away:
                continue
            matchup = "%s@%s" % (away, home)
            try:
                board = board_fn(s, home, away, odds_lookup=lookup, live=S.live_state(g))
            except Exception as exc:  # noqa: BLE001 -- one bad game never sinks the cycle
                logger.warning("board failed %s %s: %s", s, matchup, exc)
                continue
            if board.get("status") != "ok":
                continue
            meta = S.event_meta(events, s, home, away)
            book_prices = lookup(s, home, away)
            close = S.close_proxy_decimals(book_prices, home, away)
            draw = S.close_proxy_draw_decimal(book_prices)
            for row in S.iter_rows(board):
                rec = _handle_row(row, s, matchup, home, away, meta, close, ctx,
                                  draw=draw, game_state=g.get("state"))
                if rec is None:
                    continue
                if rec["kind"] == "bet":
                    staked += rec["stake_units"]
                    out["bets"].append(rec["row"])
                    n_rec += 1
                else:
                    out["predictions"].append(rec["row"])
                    n_log += 1
        out["sports"][s] = {"status": "ok", "n_games": len(games),
                            "n_recorded": n_rec, "n_logged": n_log}
        out["n_recorded"] += n_rec
        out["n_logged"] += n_log
    out["staked_total_units"] = round(staked, 6)
    out["clv_summary"] = _clv.clv_summary(_clv.load_ledger(lpath))
    return out


def _main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="PAPER trader on today's real slate.")
    ap.add_argument("--sports", default=",".join(DEFAULT_SPORTS),
                    help="comma-separated sport ids")
    a = ap.parse_args(argv)
    sports = tuple(s.strip() for s in a.sports.split(",") if s.strip())
    out = run_paper_cycle(sports)
    print("PAPER CYCLE (NOT a real result -- executed_any=%s, channel=%s)"
          % (out["executed_any"], out["channel"]))
    print("  recorded=%d logged=%d staked=%.2fu (UNITS, never $)"
          % (out["n_recorded"], out["n_logged"], out["staked_total_units"]))
    for sport, info in out["sports"].items():
        print("  %-12s %s" % (sport, info))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
