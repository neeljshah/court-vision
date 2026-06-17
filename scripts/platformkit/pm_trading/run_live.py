"""run_live.py -- forward-log model predictions on REAL games, constantly.

One tick: collect today's real games -> run the calibrated model -> append each
prediction to the REAL ledger with a forward pred_ts (the CLV/track-record
clock). Loop on an interval to run continuously. As games settle, the ledger is
graded for CLV + accuracy -- this is the multi-week forward record that the
go-live gate (step 5b) consumes.

PAPER + HONEST: no real keys, no real orders, no money. With no odds-API key
wired there is no market PRICE, so this logs predictions (trades=0). When a
price source is added, the same loop will route MarketStates to the PaperTrader.

CLI:
  python -m scripts.platformkit.pm_trading.run_live --sports mlb --once
  python -m scripts.platformkit.pm_trading.run_live --sports mlb,nba --interval 1800
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time
from datetime import datetime, timezone
from typing import Callable, List, Optional, Sequence

_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import live_feed as LF  # noqa: E402
import live_ingame as LI  # noqa: E402
from pnl import log_prediction  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_once(sources: Sequence[LF.GameSource],
             predict_fn: Optional[Callable[[str, str, str], dict]] = None,
             pred_ts: Optional[str] = None,
             ledger_dir: Optional[str] = None) -> dict:
    """Collect real games, predict, forward-log every prediction. Returns a
    summary (never raises on a single bad game / offline source)."""
    predict_fn = predict_fn or LF.make_default_predict_fn()
    pred_ts = pred_ts or _now_iso()
    games = LF.collect_games(sources)
    preds = LF.build_predictions(games, predict_fn, pred_ts)
    pred_ids: List[str] = []
    for p in preds:
        try:
            pid = log_prediction(
                p["sport"], p["market"], p["home"], p["away"],
                p["calibrated_prob"], p["pred_ts"], layer=p["layer"],
                strategy="live_feed", base_dir=ledger_dir,
                inputs=p["inputs"], game_id=p["game_id"],
                game_date=p["game_date"])
            pred_ids.append(pid)
        except Exception:
            continue
    return {
        "pred_ts": pred_ts,
        "sources": [s.name for s in sources],
        "games_found": len(games),
        "predictions_logged": len(pred_ids),
        "trades": 0,
        "note": "log-only: no market-price source wired (no odds key / exchange "
                "book). Predictions enter the CLV/track-record clock; trades=0.",
    }


def run_ingame_once(sources: Sequence[LF.GameSource],
                    predict_live_fn=None, pred_ts: Optional[str] = None,
                    ledger_dir: Optional[str] = None) -> dict:
    """IN-GAME tick: collect LIVE games' state -> predict_live -> forward-log
    layer='ingame'. This exercises the model's measured strength (the in-game
    conditioning layer) on games happening right now. Paper, no money."""
    predict_live_fn = predict_live_fn or LI.make_default_predict_live_fn()
    pred_ts = pred_ts or _now_iso()
    games = LF.collect_games(sources)
    preds = LI.build_ingame_predictions(games, predict_live_fn, pred_ts)
    pred_ids: List[str] = []
    for p in preds:
        try:
            pid = log_prediction(
                p["sport"], p["market"], p["home"], p["away"],
                p["calibrated_prob"], p["pred_ts"], layer="ingame",
                strategy="live_feed_ingame", base_dir=ledger_dir,
                inputs=p["inputs"], game_id=p["game_id"],
                game_date=p["game_date"])
            pred_ids.append(pid)
        except Exception:
            continue
    return {"pred_ts": pred_ts, "mode": "ingame", "live_games": len(games),
            "predictions_logged": len(pred_ids),
            "note": "in-game forward predictions (predict_live on live state); "
                    "paper, no money, no edge claimed."}


def loop(sources: Sequence[LF.GameSource], interval: int = 1800,
         max_ticks: int = 0, ledger_dir: Optional[str] = None,
         predict_fn=None, ingame: bool = False, verbose: bool = True) -> int:
    if predict_fn is None:
        predict_fn = (LI.make_default_predict_live_fn() if ingame
                      else LF.make_default_predict_fn())  # build corpus ONCE
    if verbose:
        print("LIVE %s-LOGGER -- PAPER/HONEST. Sources: %s | interval %ds"
              % ("INGAME" if ingame else "PREGAME",
                 ",".join(s.name for s in sources), interval))
    i = 0
    while max_ticks == 0 or i < max_ticks:
        s = (run_ingame_once(sources, predict_live_fn=predict_fn,
                             ledger_dir=ledger_dir) if ingame
             else run_once(sources, predict_fn=predict_fn, ledger_dir=ledger_dir))
        if verbose:
            cnt = s.get("games_found", s.get("live_games", 0))
            print("[%s] games=%d logged=%d  %s"
                  % (s["pred_ts"], cnt, s["predictions_logged"],
                     s["note"] if cnt == 0 else ""))
        i += 1
        if max_ticks and i >= max_ticks:
            break
        time.sleep(max(interval, 1))
    return i


def _build_sources(sports: Sequence[str], date: str) -> List[LF.GameSource]:
    src: List[LF.GameSource] = [LF.JSONFileSource()]
    if "nba" in sports:
        src.append(LF.NBAScoreboardSource())
    if "mlb" in sports:
        src.append(LF.MLBStatsAPISource(date=date))
    return src


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Live forward-logger (paper/honest)")
    ap.add_argument("--sports", default="mlb",
                    help="comma list: mlb,nba (summer-live: mlb)")
    ap.add_argument("--date", default="", help="YYYY-MM-DD (default: today)")
    ap.add_argument("--interval", type=int, default=1800, help="seconds")
    ap.add_argument("--once", action="store_true", help="single tick then exit")
    ap.add_argument("--max-ticks", type=int, default=0, help="0 = forever")
    ap.add_argument("--ingame", action="store_true",
                    help="forward-log IN-GAME predictions on live games")
    a = ap.parse_args(argv)
    ticks = 1 if a.once else a.max_ticks
    if a.ingame:
        sources = [LI.MLBLiveStateSource(date=a.date)]
        loop(sources, interval=a.interval, max_ticks=ticks, ingame=True)
    else:
        sports = [s.strip().lower() for s in a.sports.split(",") if s.strip()]
        loop(_build_sources(sports, a.date), interval=a.interval, max_ticks=ticks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
