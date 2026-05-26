"""L17_hedge_calculator.py — Hedge Calculator for live open bets.

Given an open bet and the current opposite-side market, computes the optimal
hedge stake and recommends a course of action (full hedge / partial hedge /
no hedge).

Public API
----------
    HedgeRecommendation         dataclass
    calculate_full_hedge(stake_original, odds_original, current_odds_opposite) -> float
    calculate_partial_hedge(stake_original, odds_original, current_odds_opposite,
                            target_lock_pct=0.5) -> float
    recommend_hedge(open_bet, live_market, mode="full") -> HedgeRecommendation | None

CLI
---
    python L17_hedge_calculator.py recommend \\
        --bet '{"bet_id":"X","side":"OVER","stake":100,"odds_american":-110,"status":"OPEN"}' \\
        --market '{"opposite_side":"UNDER","odds_american_opposite":200,"book":"DK"}'

Paper vs Live Mode (MODE GATING)
---------------------------------
This module is paper/live-mode-agnostic. It composes lower layers (L9-L12)
which control paper-vs-live behaviour individually. This module makes no
live API calls of its own — hedge math is pure arithmetic over input dicts
(open_bet, live_market) and does not touch any exchange client directly.

Live mode for downstream calls is enabled only when the per-exchange env var
(e.g. KALSHI_LIVE_ENABLED=1) is set on the underlying client; this module
defers to those defaults.

Environment Variables
---------------------
None. This module reads no environment variables directly. All paper/live
gating is delegated to the L9-L12 exchange clients it composes.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR))

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class HedgeRecommendation:
    original_bet_id: str
    hedge_side: str
    hedge_stake: float
    hedge_book: str
    locked_pnl_min: float
    locked_pnl_max: float
    decision: str   # "hedge_full" | "hedge_partial" | "no_hedge"
    note: str = field(default="")


# ---------------------------------------------------------------------------
# Odds conversion helpers
# ---------------------------------------------------------------------------
def _american_to_decimal(odds_american: float) -> float:
    """Convert American odds to decimal odds.

    Decimal odds = (1 + payout_per_unit).
    +200 → 3.00  (win 200 on 100, so 3.00 total returned)
    -110 → 1.909 (win 90.91 on 100, so 1.909 total returned)
    """
    if odds_american > 0:
        return 1.0 + odds_american / 100.0
    else:
        return 1.0 + 100.0 / abs(odds_american)


# ---------------------------------------------------------------------------
# Core hedge math — takes American odds, converts internally
# ---------------------------------------------------------------------------
def calculate_full_hedge(
    stake_original: float,
    odds_original: float,
    current_odds_opposite: float,
) -> float:
    """Compute the stake required for a full (equal-payout) hedge.

    Parameters
    ----------
    stake_original          : float — dollars wagered on the original bet
    odds_original           : float — American odds on the original bet
    current_odds_opposite   : float — American odds on the opposite side

    Returns
    -------
    float — hedge stake (dollars) needed so both outcomes yield equal profit.

    Raises
    ------
    ValueError if stake_original <= 0 or decimal_odds_opposite <= 1.0
    """
    if stake_original <= 0:
        raise ValueError(f"stake_original must be > 0, got {stake_original}")

    dec_original = _american_to_decimal(odds_original)
    dec_opposite = _american_to_decimal(current_odds_opposite)

    if dec_opposite <= 1.0:
        raise ValueError(
            f"decimal_odds_opposite must be > 1.0 (implied probability < 100%), "
            f"got {dec_opposite} from American odds {current_odds_opposite}"
        )

    # original_payout = total returned if original bet wins
    original_payout = stake_original * dec_original

    # Full hedge: place stake_opposite so that if opposite wins:
    #   stake_opposite * dec_opposite == original_payout
    # → both legs return the same total when their side wins, locking profit.
    hedge_stake = original_payout / dec_opposite
    return round(hedge_stake, 2)


def calculate_partial_hedge(
    stake_original: float,
    odds_original: float,
    current_odds_opposite: float,
    target_lock_pct: float = 0.5,
) -> float:
    """Compute a partial hedge stake targeting a fraction of the full hedge.

    Parameters
    ----------
    stake_original          : float — dollars on original bet
    odds_original           : float — American odds, original
    current_odds_opposite   : float — American odds, opposite side
    target_lock_pct         : float — fraction of full_hedge_stake to place (0 < x < 1)

    Returns
    -------
    float — partial hedge stake = full_hedge_stake * target_lock_pct
    """
    if stake_original <= 0:
        raise ValueError(f"stake_original must be > 0, got {stake_original}")
    if not (0 < target_lock_pct < 1):
        raise ValueError(f"target_lock_pct must be in (0, 1), got {target_lock_pct}")

    full_stake = calculate_full_hedge(stake_original, odds_original, current_odds_opposite)
    return round(full_stake * target_lock_pct, 2)


# ---------------------------------------------------------------------------
# PnL helpers — internal
# ---------------------------------------------------------------------------
def _compute_pnl_bounds(
    stake_original: float,
    dec_original: float,
    hedge_stake: float,
    dec_opposite: float,
) -> tuple[float, float]:
    """Return (pnl_if_original_wins, pnl_if_hedge_wins).

    Both are net P&L accounting for both stakes.
    pnl_min = min of the two, pnl_max = max of the two.
    """
    original_payout = stake_original * dec_original
    # If original wins: receive original_payout, lose hedge_stake
    net_original_wins = original_payout - stake_original - hedge_stake
    # If opposite wins: receive hedge_stake * dec_opposite, lose stake_original
    net_opposite_wins = hedge_stake * (dec_opposite - 1.0) - stake_original
    pnl_min = round(min(net_original_wins, net_opposite_wins), 4)
    pnl_max = round(max(net_original_wins, net_opposite_wins), 4)
    return pnl_min, pnl_max


# ---------------------------------------------------------------------------
# Main recommendation function
# ---------------------------------------------------------------------------
def recommend_hedge(
    open_bet: dict,
    live_market: Optional[dict],
    mode: str = "full",
) -> Optional[HedgeRecommendation]:
    """Recommend a hedge action for an open bet given a live opposite-side market.

    Parameters
    ----------
    open_bet    : dict with keys: bet_id, side, stake, odds_american, status, ...
    live_market : dict with keys: opposite_side, odds_american_opposite, book
                  or None if no live quote is available
    mode        : "full" (default) — uses full-hedge math before deciding;
                  partial overrides happen automatically when lock_ratio is low

    Returns
    -------
    HedgeRecommendation or None if live_market is missing / unusable.

    Decision rules
    --------------
    1. status == "settled"            → no_hedge, note="already_settled"
    2. live_market None / missing key → return None
    3. dec_opposite <= 1.0            → raise ValueError
    4. locked_pnl_min < 0            → no_hedge, note="negative_ev"
    5. lock_ratio > 0.5               → hedge_full
    6. lock_ratio <= 0.5              → hedge_partial (target_lock_pct=0.3)
    """
    bet_id = str(open_bet.get("bet_id", ""))
    status = str(open_bet.get("status", "OPEN")).upper()
    stake = float(open_bet.get("stake", 0.0))
    odds_american = float(open_bet.get("odds_american", 0.0))
    original_side = str(open_bet.get("side", ""))

    # Rule 1: already settled
    if status == "SETTLED":
        log.debug("Bet %s already settled — no hedge.", bet_id)
        return HedgeRecommendation(
            original_bet_id=bet_id,
            hedge_side="",
            hedge_stake=0.0,
            hedge_book="",
            locked_pnl_min=0.0,
            locked_pnl_max=0.0,
            decision="no_hedge",
            note="already_settled",
        )

    # Rule 2: live_market missing or missing required keys
    if live_market is None:
        log.debug("Bet %s: live_market is None — cannot recommend hedge.", bet_id)
        return None
    if "opposite_side" not in live_market or "odds_american_opposite" not in live_market:
        log.debug("Bet %s: live_market missing opposite_side or odds_american_opposite.", bet_id)
        return None

    opposite_side = str(live_market.get("opposite_side", ""))
    odds_opp_american = float(live_market.get("odds_american_opposite", 0.0))
    book = str(live_market.get("book", ""))

    # Rule 3: invalid odds
    dec_original = _american_to_decimal(odds_american)
    dec_opposite = _american_to_decimal(odds_opp_american)
    if dec_opposite <= 1.0:
        raise ValueError(
            f"decimal_odds_opposite must be > 1.0, got {dec_opposite} "
            f"(American={odds_opp_american})"
        )
    if stake <= 0:
        raise ValueError(f"stake_original must be > 0, got {stake}")

    # Compute full hedge stake and locked PnL
    full_hedge_stake = calculate_full_hedge(stake, odds_american, odds_opp_american)
    pnl_min_full, pnl_max_full = _compute_pnl_bounds(
        stake, dec_original, full_hedge_stake, dec_opposite
    )

    # For a perfect equal-payout hedge, pnl_min == pnl_max
    locked_pnl_min = pnl_min_full
    locked_pnl_max = pnl_max_full

    # Rule 4: negative EV — hedging would lock in a loss
    if locked_pnl_min < 0:
        log.info(
            "Bet %s: full hedge locks in negative PnL (%.4f) — no_hedge.",
            bet_id, locked_pnl_min,
        )
        return HedgeRecommendation(
            original_bet_id=bet_id,
            hedge_side=opposite_side,
            hedge_stake=full_hedge_stake,
            hedge_book=book,
            locked_pnl_min=locked_pnl_min,
            locked_pnl_max=locked_pnl_max,
            decision="no_hedge",
            note="negative_ev",
        )

    # Compute lock_ratio vs max possible win on original bet (no hedge)
    max_win_original = stake * (dec_original - 1.0)
    lock_ratio = locked_pnl_min / max_win_original if max_win_original > 0 else 0.0

    # Rule 5: high lock_ratio → hedge_full
    if lock_ratio > 0.5:
        log.info(
            "Bet %s: lock_ratio=%.3f > 0.5 → hedge_full, locked_pnl=%.4f",
            bet_id, lock_ratio, locked_pnl_min,
        )
        return HedgeRecommendation(
            original_bet_id=bet_id,
            hedge_side=opposite_side,
            hedge_stake=full_hedge_stake,
            hedge_book=book,
            locked_pnl_min=locked_pnl_min,
            locked_pnl_max=locked_pnl_max,
            decision="hedge_full",
            note=f"lock_ratio={lock_ratio:.3f}",
        )

    # Rule 6: low lock_ratio → hedge_partial at 30%
    partial_stake = calculate_partial_hedge(stake, odds_american, odds_opp_american, target_lock_pct=0.3)
    pnl_min_partial, pnl_max_partial = _compute_pnl_bounds(
        stake, dec_original, partial_stake, dec_opposite
    )
    log.info(
        "Bet %s: lock_ratio=%.3f <= 0.5 → hedge_partial (30%%), stake=%.2f pnl=[%.4f,%.4f]",
        bet_id, lock_ratio, partial_stake, pnl_min_partial, pnl_max_partial,
    )
    return HedgeRecommendation(
        original_bet_id=bet_id,
        hedge_side=opposite_side,
        hedge_stake=partial_stake,
        hedge_book=book,
        locked_pnl_min=pnl_min_partial,
        locked_pnl_max=pnl_max_partial,
        decision="hedge_partial",
        note=f"lock_ratio={lock_ratio:.3f},target_pct=0.30",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli_recommend(args: argparse.Namespace) -> None:
    try:
        open_bet = json.loads(args.bet)
    except json.JSONDecodeError as exc:
        print(f"[L17] ERROR parsing --bet JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        live_market = json.loads(args.market)
    except json.JSONDecodeError as exc:
        print(f"[L17] ERROR parsing --market JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        rec = recommend_hedge(open_bet, live_market, mode=args.mode)
    except ValueError as exc:
        print(f"[L17] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    if rec is None:
        print("[L17] No hedge recommendation — live market data unavailable or incomplete.")
        return

    print(f"[L17] Hedge Recommendation for bet {rec.original_bet_id}")
    print(f"  decision      : {rec.decision}")
    print(f"  hedge_side    : {rec.hedge_side}")
    print(f"  hedge_stake   : ${rec.hedge_stake:.2f}")
    print(f"  hedge_book    : {rec.hedge_book}")
    print(f"  locked_pnl    : ${rec.locked_pnl_min:.4f} .. ${rec.locked_pnl_max:.4f}")
    if rec.note:
        print(f"  note          : {rec.note}")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="L17_hedge_calculator")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("recommend", help="Recommend a hedge action")
    p_rec.add_argument("--bet", required=True, help="JSON string for open_bet dict")
    p_rec.add_argument("--market", required=True, help="JSON string for live_market dict")
    p_rec.add_argument("--mode", default="full", choices=["full", "partial"],
                       help="Hedge mode (default: full)")
    p_rec.set_defaults(func=_cli_recommend)

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
