"""live_hedge.py -- tier2-6 (loop 5). Mid-game hedge math for placed bets.

Once a cycle-88-driven bet is placed pre-game and the line moves in-play, the
operator wants a quick lock-in calculator:

  - The original bet S_open at A_open (American) has a known payout.
  - The opposite side is now offered at A_live (also American).
  - How much H to stake on the opposite side to either:
        (a) lock identical profit either way (equal-profit hedge), or
        (b) keep some upside if the original still has positive live edge
            (partial hedge), or
        (c) maximize EV given a live win probability the operator believes
            (optimal_hedge_given_live_prob).

This file is PURE MATH -- no sportsbook integration, no model imports. The
CLI in scripts/live_hedge_calc.py wraps it for interactive use.

Sign convention: every function returns NON-NEGATIVE hedge stakes. A
negative recommendation (i.e. "you'd hedge yourself MORE on the original
side") is clamped to 0 with the note that no hedge is warranted -- consistent
with the project rule against recommending negative-EV actions by default.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


# ---------------------------------------------------------------------------
# Odds helpers
# ---------------------------------------------------------------------------

def american_to_decimal(american: float) -> float:
    """Convert American odds to decimal odds (includes stake return).

    -110 -> 1.9090909..., +130 -> 2.30, +100 -> 2.00.
    Zero is illegal in American convention; raise.
    """
    a = float(american)
    if a == 0:
        raise ValueError("American odds cannot be zero")
    if a > 0:
        return 1.0 + (a / 100.0)
    return 1.0 + (100.0 / -a)


def decimal_to_american(decimal_odds: float) -> float:
    """Convert decimal odds to American. Inverse of american_to_decimal.

    decimal >= 2.0 -> positive American (underdog); decimal < 2.0 -> negative.
    decimal == 2.0 -> +100 exactly.
    """
    d = float(decimal_odds)
    if d <= 1.0:
        raise ValueError("Decimal odds must be > 1.0")
    if d >= 2.0:
        return round((d - 1.0) * 100.0, 4)
    return round(-100.0 / (d - 1.0), 4)


def payout(american: float, stake: float = 1.0) -> float:
    """Net profit on `stake` at American odds (does NOT include stake return).

    payout(-110, 100) == 90.9090..., payout(+130, 100) == 130.0.
    """
    a = float(american)
    s = float(stake)
    if a == 0:
        raise ValueError("American odds cannot be zero")
    if a > 0:
        return s * (a / 100.0)
    return s * (100.0 / -a)


# ---------------------------------------------------------------------------
# Hedge primitives
# ---------------------------------------------------------------------------

@dataclass
class EqualProfitHedge:
    hedge_stake: float
    guaranteed_profit: float


def equal_profit_hedge(stake_open: float, odds_open: float,
                       odds_live: float) -> Dict[str, float]:
    """Stake on the opposite side that locks identical profit either way.

    Derivation: let S = stake_open, b_o = payout(odds_open) (net per $1),
    b_l = payout(odds_live), H = hedge stake. Both scenarios identical:
        S * b_o - H        ==  H * b_l - S
    Solve for H: H * (1 + b_l) = S * (1 + b_o)
        H = S * (1 + b_o) / (1 + b_l)
    Equivalently with decimal odds D_o = 1+b_o, D_l = 1+b_l: H = S * D_o / D_l.

    Returned profit is the guaranteed lock-in (same in both branches). If the
    live odds are so much worse than the open odds that the guaranteed profit
    is negative, we still return the math (it's a guaranteed LOSS, the
    operator may still want to limit downside in some scenarios) -- the CLI
    layer flags this.
    """
    if stake_open < 0:
        raise ValueError("stake_open must be >= 0")
    d_open = american_to_decimal(odds_open)
    d_live = american_to_decimal(odds_live)
    h = stake_open * d_open / d_live
    # Both scenarios yield the same profit by construction; compute the
    # "original wins" branch for clarity.
    win_branch_profit = stake_open * payout(odds_open, 1.0) - h
    return {"hedge_stake": round(h, 4),
            "guaranteed_profit": round(win_branch_profit, 4)}


def partial_hedge(stake_open: float, odds_open: float, odds_live: float,
                  hedge_pct: float) -> Dict[str, float]:
    """Hedge a fraction (0-1) of the equal-profit stake, keeping upside.

    hedge_pct == 0.0  -> no hedge (full upside on original).
    hedge_pct == 1.0  -> equivalent to equal_profit_hedge.
    Anything between scales the hedge linearly; win_profit and lose_profit
    diverge proportionally.

    Returns:
        hedge_stake   -- $ to lay on opposite side
        win_profit    -- profit if original wins (hedge loses)
        lose_profit   -- profit if original loses (hedge wins)

    Both profit numbers can be negative (lose_profit at low hedge_pct, etc.)
    -- that's the point of "partial" hedging: you preserve some downside in
    exchange for keeping upside.
    """
    if not (0.0 <= hedge_pct <= 1.0):
        raise ValueError("hedge_pct must be in [0.0, 1.0]")
    if stake_open < 0:
        raise ValueError("stake_open must be >= 0")
    base = equal_profit_hedge(stake_open, odds_open, odds_live)
    h = base["hedge_stake"] * hedge_pct
    win_profit = stake_open * payout(odds_open, 1.0) - h
    lose_profit = h * payout(odds_live, 1.0) - stake_open
    return {"hedge_stake": round(h, 4),
            "win_profit": round(win_profit, 4),
            "lose_profit": round(lose_profit, 4)}


def optimal_hedge_given_live_prob(stake_open: float, odds_open: float,
                                  odds_live: float,
                                  live_win_prob: float) -> Dict[str, float]:
    """EV-maximizing hedge given the operator's live win-prob for the ORIGINAL.

    Profit as a function of hedge stake H:
        win_branch_profit  = S * b_o - H
        lose_branch_profit = H * b_l - S
    EV(H) = p * (S*b_o - H) + (1-p) * (H*b_l - S)
          = p*S*b_o - p*H + (1-p)*H*b_l - (1-p)*S
          = const + H * [(1-p)*b_l - p]

    EV is LINEAR in H, so the optimum is a CORNER:
        - If (1-p)*b_l > p  -> hedge is +EV per dollar -> H = equal_profit
          stake (maximum risk-free hedge; going larger flips risk to the
          hedge side and is no longer "locked").
        - If (1-p)*b_l < p  -> hedge is -EV per dollar -> H = 0 (let it ride).
        - If equal                                    -> H = 0 (indifferent).

    Capping H at the equal-profit stake matches operator intent: we hedge to
    REDUCE risk, not to flip the position. Going past equal-profit means
    you're now net-long the LIVE side, which is a different bet.

    Returns:
        hedge_stake     -- recommended $ (0 if hedging is -EV)
        expected_profit -- EV of the combined position at the recommended H
    """
    if not (0.0 <= live_win_prob <= 1.0):
        raise ValueError("live_win_prob must be in [0.0, 1.0]")
    if stake_open < 0:
        raise ValueError("stake_open must be >= 0")
    b_o = payout(odds_open, 1.0)
    b_l = payout(odds_live, 1.0)
    p = float(live_win_prob)

    hedge_marginal_ev = (1.0 - p) * b_l - p
    if hedge_marginal_ev <= 0:
        # Don't hedge -- expected loss per hedge dollar.
        ev = p * stake_open * b_o - (1.0 - p) * stake_open
        return {"hedge_stake": 0.0,
                "expected_profit": round(ev, 4)}

    # Hedge is +EV; cap at equal-profit stake to keep position risk-reducing.
    cap = equal_profit_hedge(stake_open, odds_open, odds_live)
    h = cap["hedge_stake"]
    win_branch = stake_open * b_o - h
    lose_branch = h * b_l - stake_open
    ev = p * win_branch + (1.0 - p) * lose_branch
    return {"hedge_stake": round(h, 4),
            "expected_profit": round(ev, 4)}


# ---------------------------------------------------------------------------
# Recommendation glue
# ---------------------------------------------------------------------------

def recommend(stake_open: float, odds_open: float, odds_live: float,
              live_win_prob: float = None) -> Dict[str, object]:
    """Bundle the three hedge variants into one report dict for the CLI.

    When live_win_prob is None, "optimal" is skipped (operator hasn't supplied
    a posterior belief).

    The 'verdict' is a short string the CLI prints as the bottom line:
        "hold"            -- equal-profit hedge has negative guaranteed profit
                             (book vig + line move are eating it) AND live
                             win-prob (if supplied) keeps it +EV to ride.
        "hedge full"      -- equal-profit hedge has positive guaranteed
                             profit; lock it in.
        "partial hedge XX%" -- live_win_prob is supplied and intermediate;
                             the optimal-EV stake equals the equal-profit
                             stake (current corner-solution math), so this
                             surfaces only when partial sizing is explicitly
                             requested. Reserved for future expansion.
    """
    eq = equal_profit_hedge(stake_open, odds_open, odds_live)
    report: Dict[str, object] = {
        "stake_open": float(stake_open),
        "odds_open": float(odds_open),
        "odds_live": float(odds_live),
        "open_profit_if_wins": round(payout(odds_open, stake_open), 4),
        "equal_profit_hedge": eq,
    }
    if live_win_prob is not None:
        opt = optimal_hedge_given_live_prob(stake_open, odds_open,
                                            odds_live, live_win_prob)
        report["optimal"] = opt
        report["live_win_prob"] = float(live_win_prob)
        if opt["hedge_stake"] <= 0:
            report["verdict"] = "hold"
        elif eq["guaranteed_profit"] > 0:
            report["verdict"] = "hedge full"
        else:
            # Equal-profit locks a loss; only hedge if live edge demands it.
            report["verdict"] = "hold"
    else:
        report["verdict"] = ("hedge full" if eq["guaranteed_profit"] > 0
                             else "hold")
    return report
