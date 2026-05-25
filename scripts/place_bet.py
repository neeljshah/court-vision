"""place_bet.py — record a manually-placed sportsbook bet in the P&L ledger.

Usage:
    python scripts/place_bet.py --game 0022500123 --player "Nikola Jokic" \\
        --stat pts --line 28.5 --side OVER --book DK --odds -115 --stake 50

Optional model context (gets stamped on the row for later EV analysis):
    --model-pred 31.2 --model-prob 0.62 --kelly-pct 4.5 \\
    --player-id 203999 --team DEN --bankroll-before 1000
"""
from __future__ import annotations

import argparse
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.betting.pnl_ledger import place_bet, current_bankroll  # noqa: E402
from src.betting import ab_strategy as _AB  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game",   required=True, help="NBA game_id")
    ap.add_argument("--player", required=True, help="player full name")
    ap.add_argument("--stat",   required=True, help="pts|reb|ast|fg3m|stl|blk|tov")
    ap.add_argument("--line",   required=True, type=float)
    ap.add_argument("--side",   required=True, choices=["OVER", "UNDER", "over", "under"])
    ap.add_argument("--book",   required=True, help="DK|FD|MGM|BR|...")
    ap.add_argument("--odds",   required=True, type=int, help="American odds, e.g. -115")
    ap.add_argument("--stake",  required=True, type=float, help="$ wagered")
    ap.add_argument("--model-pred", type=float, default=None)
    ap.add_argument("--model-prob", type=float, default=None)
    ap.add_argument("--kelly-pct",  type=float, default=None)
    ap.add_argument("--player-id",  default=None)
    ap.add_argument("--team",       default=None)
    ap.add_argument("--bankroll-before", type=float, default=None,
                    help="Seed the bankroll log with this starting balance "
                         "(only used when no prior bankroll entries exist).")
    ap.add_argument("--strategy", default=None,
                    help="Tag this bet with an A/B strategy name (cycle b489a241). "
                         "If set and the strategy is registered, the bet is routed "
                         "through ab_strategy.place_strategy_bet for bankroll caps.")
    args = ap.parse_args()

    if args.strategy:
        known = {r.get("strategy") for r in _AB.list_strategies()}
        if args.strategy in known:
            bet_id = _AB.place_strategy_bet(
                args.strategy,
                game_id=args.game,
                player=args.player,
                stat=args.stat,
                line=args.line,
                side=args.side.upper(),
                book=args.book,
                odds=args.odds,
                stake=args.stake,
                model_pred=args.model_pred,
                model_prob=args.model_prob,
                kelly_pct=args.kelly_pct,
                player_id=args.player_id,
                team=args.team,
                bankroll_before=args.bankroll_before,
            )
            print(f"  bet_id           = {bet_id}")
            print(f"  player           = {args.player}")
            print(f"  {args.stat.upper():4s} {args.side.upper()} {args.line}  @ {args.odds:+d}  stake ${args.stake:.2f}")
            print(f"  strategy         = {args.strategy}")
            print(f"  bankroll_after   = ${current_bankroll():.2f}")
            return 0
        # Unknown strategy -> fall through to plain place_bet but tag the row.
        bet_id = place_bet(
            game_id=args.game,
            player=args.player,
            stat=args.stat,
            line=args.line,
            side=args.side.upper(),
            book=args.book,
            odds=args.odds,
            stake=args.stake,
            model_pred=args.model_pred,
            model_prob=args.model_prob,
            kelly_pct=args.kelly_pct,
            player_id=args.player_id,
            team=args.team,
            bankroll_before=args.bankroll_before,
            strategy=args.strategy,
        )
        print(f"  bet_id           = {bet_id}")
        print(f"  player           = {args.player}")
        print(f"  {args.stat.upper():4s} {args.side.upper()} {args.line}  @ {args.odds:+d}  stake ${args.stake:.2f}")
        print(f"  strategy         = {args.strategy} (unregistered -- tagged only)")
        print(f"  bankroll_after   = ${current_bankroll():.2f}")
        return 0

    bet_id = place_bet(
        game_id=args.game,
        player=args.player,
        stat=args.stat,
        line=args.line,
        side=args.side.upper(),
        book=args.book,
        odds=args.odds,
        stake=args.stake,
        model_pred=args.model_pred,
        model_prob=args.model_prob,
        kelly_pct=args.kelly_pct,
        player_id=args.player_id,
        team=args.team,
        bankroll_before=args.bankroll_before,
    )
    print(f"  bet_id           = {bet_id}")
    print(f"  player           = {args.player}")
    print(f"  {args.stat.upper():4s} {args.side.upper()} {args.line}  @ {args.odds:+d}  stake ${args.stake:.2f}")
    print(f"  bankroll_after   = ${current_bankroll():.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
