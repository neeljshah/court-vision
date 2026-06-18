"""scripts.platformkit.pm_trading.run_paper_today -- PAPER trader on TODAY's slate.

Pulls today's REAL games + state (live_board.todays_live_games), builds each game's
bet board (bet_board.game_bet_board) priced off the aggregated odds slate, and:
  * PRICED row (real book price, mainly moneyline) -> EV, size via paper_autobet,
    RECORD to the CLV ledger (clv_ledger.record_bet) executed=False/channel="paper",
    with the as_of price/book + event_id + commence_time for later settling.
  * UNPRICED row (derived markets) -> never fabricate a price; LOG the model view +
    a closing-line PROXY target to data/frontend/paper_predictions.jsonl for grading.

HONEST RAILS (binding -- can NEVER move real money): every ledger row is
executed=False / channel="paper"; PERMISSIVE policy (record picks to GATHER CLV
data, do NOT require BEATS_CLOSE) but each row is TAGGED would_pass_real_gate (EV>0
at a book price); idempotent per (sport, matchup, side/selection, day); markets are
efficient -- NO $ edge claimed. <=300 LOC; no secrets; no network in tests (the
live feed / board / odds index are all injectable). Pure helpers + Ctx live in the
sibling paper_today_support module.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from scripts.platformkit import clv_ledger as _clv
from scripts.platformkit.frontend.bet_board import game_bet_board
from scripts.platformkit.frontend.live_board import todays_live_games
from scripts.platformkit.odds_provider.base import OddsEvent
from scripts.platformkit.odds_shop import devig_twoway, ev_vs_price
from scripts.platformkit.pm_trading.paper_autobet import (
    AutoBetConfig, CHANNEL_PAPER, EdgeCandidate, size_stake)
from scripts.platformkit.pm_trading import paper_today_support as S
from scripts.platformkit.pm_trading.paper_today_support import (
    Ctx, DEFAULT_PREDICTIONS, DEFAULT_SPORTS, PAPER_EV_FLOOR)

logger = logging.getLogger(__name__)


def _record_priced(row, sport, matchup, meta, side, price, prob, selection,
                   ctx: Ctx) -> Optional[Dict[str, Any]]:
    """Record a priced two-way pick as a paper bet. None if dedup/-EV."""
    bet_key = (sport, matchup, side, ctx.day)
    if bet_key in ctx.ledger_keys:
        return None
    ev = ev_vs_price(prob, price)
    if ev <= PAPER_EV_FLOOR:
        return None
    book = row.get("best_book") or "aggregate"
    cand = EdgeCandidate(sport, matchup, side, float(price), float(prob),
                         taken_book=book, event_id=meta["event_id"])
    stake = size_stake(cand, ctx.cfg) if ev > 0 else 0.0
    saved = _clv.record_bet(sport, matchup, side, book, float(price),
                            model_prob=float(prob), stake=stake, path=ctx.lpath)
    assert saved["executed"] is False  # honesty invariant, belt-and-braces
    ctx.ledger_keys.add(bet_key)
    bet_row = {
        "sport": sport, "matchup": matchup, "selection": selection, "side": side,
        "model_prob": round(float(prob), 6), "price": round(float(price), 4),
        "book": book, "ev_pct": round(ev * 100.0, 3), "stake": round(stake, 2),
        "would_pass_real_gate": bool(ev > 0.0), "executed": False,
        "channel": CHANNEL_PAPER, "event_id": meta["event_id"],
        "commence_time": meta["commence_time"],
    }
    return {"kind": "bet", "row": bet_row, "stake": stake}


def _log_unpriced(row, sport, matchup, home, away, meta, close, prob, selection,
                  ctx: Ctx) -> Optional[Dict[str, Any]]:
    """Log an unpriced model prediction + closing-line proxy. None if deduped."""
    pred_key = (sport, matchup, str(selection), ctx.day)
    if pred_key in ctx.pred_keys:
        return None
    proxy, side = None, S.side_of(selection, home, away)
    if close is not None and side is not None:
        proxy = {"close_decimal_home": round(close[0], 4),
                 "close_decimal_away": round(close[1], 4), "fair_close_prob": None}
        try:  # devig only when the two-way line is a real vigged book (booksum>=1)
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


def _handle_row(row, sport, matchup, home, away, meta, close, ctx: Ctx
                ) -> Optional[Dict[str, Any]]:
    """Record a priced two-way row as a paper bet, else log a model prediction."""
    prob, selection = row.get("model_prob"), row.get("selection")
    if not isinstance(prob, (int, float)) or prob <= 0.0 or prob >= 1.0:
        return None
    price, side = row.get("best_price"), S.side_of(selection, home, away)
    # A priced two-way row belongs to the BET path exclusively (recorded, or
    # skipped on dedup / below the permissive EV floor) -- never also logged.
    if price is not None and side is not None:
        return _record_priced(row, sport, matchup, meta, side, price, prob,
                              selection, ctx)
    return _log_unpriced(row, sport, matchup, home, away, meta, close, prob,
                         selection, ctx)


def run_paper_cycle(
    sports: Sequence[str] = DEFAULT_SPORTS,
    ledger_path: Optional[Path] = None,
    *,
    predictions_path: Optional[Path] = None,
    cfg: Optional[AutoBetConfig] = None,
    live_fetch: Callable[..., Dict[str, Any]] = todays_live_games,
    board_fn: Callable[..., Dict[str, Any]] = game_bet_board,
    odds_index: Callable[[str], Tuple[Any, List[OddsEvent]]] = S.odds_index,
) -> Dict[str, Any]:
    """Run one PAPER cycle on TODAY's real slate across *sports*.

    Pulls each sport's games + state, builds each priced bet board, RECORDS priced
    picks to the CLV ledger (executed=False, channel="paper") and LOGS unpriced
    model predictions. Idempotent per (sport, matchup, side/selection, day). Never
    raises on a single bad game/sport.
    """
    lpath = Path(ledger_path) if ledger_path is not None else _clv.DEFAULT_LEDGER
    ppath = Path(predictions_path) if predictions_path is not None else DEFAULT_PREDICTIONS
    ctx = Ctx(cfg=cfg or AutoBetConfig(), day=S.today_key(), lpath=lpath, ppath=ppath,
              ledger_keys=S.ledger_keys(_clv.load_ledger(lpath)),
              pred_keys=S.prediction_keys(S.load_predictions(ppath)))

    out: Dict[str, Any] = {
        "as_of": S.now_iso(), "channel": CHANNEL_PAPER, "executed_any": False,
        "day": ctx.day, "sports": {}, "bets": [], "predictions": [],
        "n_recorded": 0, "n_logged": 0, "staked_total": 0.0,
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
            close = S.close_proxy_decimals(lookup(s, home, away), home, away)
            for row in S.iter_rows(board):
                rec = _handle_row(row, s, matchup, home, away, meta, close, ctx)
                if rec is None:
                    continue
                if rec["kind"] == "bet":
                    staked += rec["stake"]
                    out["bets"].append(rec["row"])
                    n_rec += 1
                else:
                    out["predictions"].append(rec["row"])
                    n_log += 1
        out["sports"][s] = {"status": "ok", "n_games": len(games),
                            "n_recorded": n_rec, "n_logged": n_log}
        out["n_recorded"] += n_rec
        out["n_logged"] += n_log
    out["staked_total"] = round(staked, 6)
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
    print("  recorded=%d logged=%d staked=$%.2f"
          % (out["n_recorded"], out["n_logged"], out["staked_total"]))
    for sport, info in out["sports"].items():
        print("  %-12s %s" % (sport, info))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
