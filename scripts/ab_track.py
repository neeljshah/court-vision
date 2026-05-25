"""scripts/ab_track.py — tier4-14 (loop 5).

CLI front-end for src.betting.ab_strategy: register strategies, place
strategy-tagged bets, and list current bankroll status.

Examples
--------
    python scripts/ab_track.py --register --name endQ3 --bankroll 1000 --max-bet-pct 0.05
    python scripts/ab_track.py --place --strategy endQ3 --game 0022500123 \\
        --player "Nikola Jokic" --stat pts --line 28.5 --side OVER \\
        --book DK --odds -115 --stake 25.0
    python scripts/ab_track.py --status
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.betting import ab_strategy as AB
from src.betting import pnl_ledger as PNL


def _cmd_register(args) -> None:
    rec = AB.register_strategy(args.name, args.bankroll, args.max_bet_pct)
    print(json.dumps(rec, indent=2))


def _cmd_place(args) -> None:
    bid = AB.place_strategy_bet(
        args.strategy,
        game_id=args.game or "",
        player=args.player,
        stat=args.stat,
        line=args.line,
        side=args.side.upper(),
        book=args.book,
        odds=args.odds,
        stake=args.stake,
        player_id=args.player_id or None,
        team=args.team or None,
        model_pred=args.model_pred,
        kelly_pct=args.kelly_pct,
    )
    print(json.dumps({"bet_id": bid, "strategy": args.strategy}, indent=2))


def _cmd_status(_args) -> None:
    rows = AB.list_strategies()
    if not rows:
        print("(no strategies registered)")
        return
    print(f"{'STRATEGY':<22}{'BANKROLL':>12}{'AVAIL':>12}"
          f"{'OPEN':>10}{'P&L':>12}{'ROI':>10}{'N':>6}")
    for r in rows:
        name = r["strategy"]
        try:
            s = AB.strategy_summary(name)
            print(f"{name:<22}{s['bankroll_cap']:>12.2f}{s['available']:>12.2f}"
                  f"{s['allocated_open']:>10.2f}{s['total_profit']:>12.2f}"
                  f"{s['roi']:>10.4f}{s['n_bets']:>6}")
        except Exception as e:
            print(f"{name:<22} ERROR: {e}")


def main() -> int:
    p = argparse.ArgumentParser(description="A/B strategy tracker")
    p.add_argument("--register", action="store_true")
    p.add_argument("--place",    action="store_true")
    p.add_argument("--status",   action="store_true")

    # register
    p.add_argument("--name")
    p.add_argument("--bankroll", type=float)
    p.add_argument("--max-bet-pct", type=float, default=0.05,
                   dest="max_bet_pct")

    # place
    p.add_argument("--strategy")
    p.add_argument("--game",   default="")
    p.add_argument("--player", default="")
    p.add_argument("--player-id", default="", dest="player_id")
    p.add_argument("--team",   default="")
    p.add_argument("--stat",   default="pts")
    p.add_argument("--line",   type=float)
    p.add_argument("--side",   default="OVER")
    p.add_argument("--book",   default="DK")
    p.add_argument("--odds",   type=int)
    p.add_argument("--stake",  type=float)
    p.add_argument("--model-pred", type=float, default=None, dest="model_pred")
    p.add_argument("--kelly-pct",  type=float, default=None, dest="kelly_pct")

    args = p.parse_args()
    if args.register:
        if not args.name or args.bankroll is None:
            p.error("--register needs --name and --bankroll")
        _cmd_register(args)
    elif args.place:
        for req in ("strategy", "player", "line", "odds", "stake"):
            if getattr(args, req) in (None, ""):
                p.error(f"--place needs --{req}")
        _cmd_place(args)
    elif args.status:
        _cmd_status(args)
    else:
        p.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
