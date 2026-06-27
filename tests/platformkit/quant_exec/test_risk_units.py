"""Per-file test for the units-only portfolio risk view (LANE Q risk_units).

Run ONLY this file (a bare pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && \
      python -m pytest tests/platformkit/quant_exec/test_risk_units.py -q

Covers the honesty invariants:
  * joint_exposure_units < naive total whenever >=2 distinct games appear
    (correlation haircut; same-game legs do not diversify, cross-game do).
  * NO $/dollar/roi/pnl/profit/bankroll key (or substring) anywhere in the view.
  * risk_of_ruin is a DESCRIPTIVE [0,1] stat: in [0,1], decreasing in model edge,
    1.0 when sigma==0 and mu deeply negative, 0.0 on an empty book.
  * portfolio_variance reflects same-game positive covariance and never raises.
"""
from __future__ import annotations

import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.quant import risk_units as ru  # noqa: E402

_MONEY_TOKENS = ("$", "dollar", "roi", "pnl", "profit", "bankroll")


def _leg(game_id, units, p=None, edge=None):
    d = {"game_id": game_id, "stake_units": units}
    if p is not None:
        d["model_prob"] = p
    if edge is not None:
        d["edge"] = edge
    return d


# --------------------------------------------------------------------------- #
# joint < naive sum whenever >=2 games appear.
# --------------------------------------------------------------------------- #
def test_joint_exposure_below_naive_sum_cross_game():
    bets = [_leg("G1", 2.0), _leg("G2", 2.0), _leg("G3", 2.0)]
    total = ru.total_exposure_units(bets)
    joint = ru.joint_exposure_units(bets)
    assert total == 6.0
    assert joint < total  # quadrature of three independent games diversifies
    assert joint > 0.0


def test_same_game_legs_do_not_diversify():
    # two same-game legs: block sum = 4; one other game = 2 -> sqrt(16+4) < 6.
    bets = [_leg("G1", 2.0), _leg("G1", 2.0), _leg("G2", 2.0)]
    total = ru.total_exposure_units(bets)
    joint = ru.joint_exposure_units(bets)
    assert total == 6.0
    assert joint < total
    # single game -> NO diversification: joint == total.
    one_game = [_leg("G1", 2.0), _leg("G1", 3.0)]
    assert ru.joint_exposure_units(one_game) == ru.total_exposure_units(one_game)


def test_portfolio_view_joint_le_total_and_haircut_nonneg():
    bets = [_leg("G1", 1.5, p=0.6), _leg("G2", 2.5, p=0.4)]
    view = ru.portfolio_risk(bets)
    assert view["joint_exposure_units"] <= view["total_exposure_units"]
    assert view["diversification_units"] >= 0.0
    assert view["n_games"] == 2
    assert view["n_legs"] == 2


# --------------------------------------------------------------------------- #
# NO money key anywhere.
# --------------------------------------------------------------------------- #
def test_no_dollar_key_anywhere():
    bets = [_leg("G1", 2.0, p=0.6, edge=0.05), _leg("G2", 1.0, p=0.55, edge=0.03)]
    view = ru.portfolio_risk(bets)
    for k in view:
        kl = str(k).lower()
        assert not any(tok in kl for tok in _MONEY_TOKENS), k
    # also assert the rendered view carries no money substring in any string value.
    blob = repr(view).lower()
    for tok in ("$", "dollar", "bankroll", "pnl"):
        assert tok not in blob, tok


# --------------------------------------------------------------------------- #
# risk_of_ruin is a descriptive [0,1] stat.
# --------------------------------------------------------------------------- #
def test_risk_of_ruin_in_unit_interval_and_descriptive():
    bets = [_leg("G1", 2.0, p=0.6, edge=0.05), _leg("G2", 2.0, p=0.55, edge=0.04)]
    ror = ru.risk_of_ruin(bets, ruin_units=5.0)
    assert 0.0 <= ror <= 1.0


def test_risk_of_ruin_decreasing_in_edge():
    low = [_leg("G1", 3.0, p=0.55, edge=0.01)]
    high = [_leg("G1", 3.0, p=0.55, edge=0.20)]
    # a larger positive model edge (mu up, same sigma) lowers risk of ruin.
    assert ru.risk_of_ruin(high, ruin_units=2.0) <= ru.risk_of_ruin(low, ruin_units=2.0)


def test_risk_of_ruin_empty_book_is_zero():
    assert ru.risk_of_ruin([], ruin_units=5.0) == 0.0
    assert ru.total_exposure_units([]) == 0.0
    assert ru.portfolio_variance([]) == 0.0


def test_risk_of_ruin_zero_sigma_branch():
    # no usable p -> sigma 0; deeply negative model drift -> ruin certain (1.0).
    bets = [_leg("G1", 10.0, edge=-1.0)]  # no model_prob -> variance 0
    assert ru.portfolio_variance(bets) == 0.0
    assert ru.risk_of_ruin(bets, ruin_units=1.0) == 1.0
    # positive drift, sigma 0 -> no ruin.
    assert ru.risk_of_ruin([_leg("G1", 10.0, edge=1.0)], ruin_units=1.0) == 0.0


def test_same_game_variance_exceeds_independent():
    # two correlated same-game legs carry MORE variance than the same two legs
    # treated as different games (positive covariance term).
    correlated = [_leg("G1", 2.0, p=0.5), _leg("G1", 2.0, p=0.5)]
    independent = [_leg("G1", 2.0, p=0.5), _leg("G2", 2.0, p=0.5)]
    assert ru.portfolio_variance(correlated) > ru.portfolio_variance(independent)


def test_never_raises_on_malformed_legs():
    bets = [None, {"game_id": "G1"}, {"stake_units": "x"}, 42, _leg("G2", 1.0)]
    view = ru.portfolio_risk(bets)  # must not raise
    assert view["units"] == "units"
