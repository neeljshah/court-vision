"""tests/test_live_hedge.py -- tier2-6 (loop 5). Hedge math + CLI smoke."""
from __future__ import annotations

import math
import os
import subprocess
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from src.betting.live_hedge import (  # noqa: E402
    american_to_decimal,
    equal_profit_hedge,
    optimal_hedge_given_live_prob,
    partial_hedge,
    payout,
)


# ---------------------------------------------------------------------------
# 1. Odds helpers
# ---------------------------------------------------------------------------

def test_american_to_decimal_minus110():
    """-110 -> 1.9090909... (book vig baseline)."""
    d = american_to_decimal(-110)
    assert math.isclose(d, 1.0 + 100.0 / 110.0, rel_tol=1e-9)
    # Plus-side spot check
    assert math.isclose(american_to_decimal(+130), 2.30, rel_tol=1e-9)


def test_payout_minus110_on_100_dollars():
    """Net profit on a winning -110 bet of $100 is $90.9090..."""
    p = payout(-110, 100.0)
    assert math.isclose(p, 100.0 * 100.0 / 110.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 2. Equal-profit hedge -- three manual fixtures
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "stake, open_odds, live_odds, exp_hedge",
    [
        # Classic: $100 at -110, opposite live +130
        # H = 100 * (1 + 100/110) / (1 + 130/100) = 100 * 1.9090909 / 2.30
        (100.0, -110, +130, 100.0 * (1.0 + 100.0 / 110.0) / (1.0 + 130.0 / 100.0)),
        # Original is a plus-side dog (+150), live opposite is favored (-120)
        # H = 100 * (1 + 150/100) / (1 + 100/120) = 100 * 2.50 / 1.8333333
        (100.0, +150, -120, 100.0 * 2.50 / (1.0 + 100.0 / 120.0)),
        # Zero stake -> zero hedge regardless of odds
        (0.0, -110, +200, 0.0),
    ],
)
def test_equal_profit_hedge_matches_manual_calc(stake, open_odds, live_odds, exp_hedge):
    out = equal_profit_hedge(stake, open_odds, live_odds)
    assert math.isclose(out["hedge_stake"], exp_hedge, rel_tol=1e-4, abs_tol=1e-4)
    # Both branches must yield the same profit by construction
    if stake > 0:
        win_branch = stake * payout(open_odds, 1.0) - out["hedge_stake"]
        lose_branch = out["hedge_stake"] * payout(live_odds, 1.0) - stake
        assert math.isclose(win_branch, lose_branch, abs_tol=1e-3)
        assert math.isclose(out["guaranteed_profit"], win_branch, abs_tol=1e-3)


# ---------------------------------------------------------------------------
# 3. Partial hedge corners: 0% = no hedge, 100% = equal-profit
# ---------------------------------------------------------------------------

def test_partial_hedge_zero_pct_is_no_hedge():
    out = partial_hedge(100.0, -110, +130, 0.0)
    assert out["hedge_stake"] == 0.0
    assert math.isclose(out["win_profit"], payout(-110, 100.0), abs_tol=1e-3)
    assert math.isclose(out["lose_profit"], -100.0, abs_tol=1e-3)


def test_partial_hedge_full_pct_equals_equal_profit():
    eq = equal_profit_hedge(100.0, -110, +130)
    ph = partial_hedge(100.0, -110, +130, 1.0)
    assert math.isclose(ph["hedge_stake"], eq["hedge_stake"], abs_tol=1e-3)
    # win and lose profit branches should converge on the guaranteed lock-in
    assert math.isclose(ph["win_profit"], ph["lose_profit"], abs_tol=1e-3)
    assert math.isclose(ph["win_profit"], eq["guaranteed_profit"], abs_tol=1e-3)


# ---------------------------------------------------------------------------
# 4. Optimal hedge corner solutions: prob=1.0 -> no hedge; prob=0.0 -> full
# ---------------------------------------------------------------------------

def test_optimal_hedge_at_prob_one_no_hedge():
    """If we believe original wins for sure, hedging is throwing money away."""
    out = optimal_hedge_given_live_prob(100.0, -110, +130, 1.0)
    assert out["hedge_stake"] == 0.0
    # Expected profit = stake * payout(-110)
    assert math.isclose(out["expected_profit"], payout(-110, 100.0), abs_tol=1e-3)


def test_optimal_hedge_at_prob_zero_full_hedge():
    """If we believe original LOSES for sure, hedge to the equal-profit cap."""
    eq = equal_profit_hedge(100.0, -110, +130)
    out = optimal_hedge_given_live_prob(100.0, -110, +130, 0.0)
    assert math.isclose(out["hedge_stake"], eq["hedge_stake"], abs_tol=1e-3)


# ---------------------------------------------------------------------------
# 5. CLI smoke + arg parsing
# ---------------------------------------------------------------------------

def test_cli_args_and_output_smoke():
    """Run the CLI as a subprocess; verify it exits 0 and prints the key lines.

    Smoke-tests --stake, --open-odds, --live-odds, --live-prob in one shot.
    """
    script = os.path.join(PROJECT_DIR, "scripts", "live_hedge_calc.py")
    result = subprocess.run(
        [sys.executable, script,
         "--stake", "100", "--open-odds", "-110",
         "--live-odds", "+130", "--live-prob", "0.42"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"stderr={result.stderr!r} stdout={result.stdout!r}")
    out = result.stdout
    assert "Original bet:" in out
    assert "Equal-profit hedge:" in out
    assert "Optimal hedge" in out
    assert "Recommendation:" in out


# ---------------------------------------------------------------------------
# 6. Edge case: live odds == open odds -> hedge is a wash (zero profit lock)
# ---------------------------------------------------------------------------

def test_edge_case_live_odds_equal_open_odds_is_wash():
    """When live odds match open odds, equal-profit hedge guarantees $0 profit
    (the hedge and the original perfectly cancel, modulo whichever side wins).
    """
    out = equal_profit_hedge(100.0, -110, -110)
    # H = S * D_o / D_l = S * 1 = S, so hedge_stake equals original stake
    assert math.isclose(out["hedge_stake"], 100.0, abs_tol=1e-3)
    # Both scenarios: win original profit (90.91) - hedge stake (100) = -9.09
    # i.e. you've paid the vig on both sides -> guaranteed -9.09
    expected = payout(-110, 100.0) - 100.0
    assert math.isclose(out["guaranteed_profit"], expected, abs_tol=1e-3)
