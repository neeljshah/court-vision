"""tests.platform.test_soccer_markets -- coherence of the full soccer market surface.

Every market in domains/soccer/markets.py is a linear read-off of ONE scoreline matrix,
so cross-market identities must hold EXACTLY (up to float tolerance):

  1. 1X2 probabilities sum to 1.0.
  2. Double chance = the sum of its two covered 1X2 legs.
  3. Draw-no-bet renormalises over the decisive (non-draw) mass.
  4. BTTS yes/no in [0, 1] and sum to 1.0.
  5. Totals over-prob is monotone DECREASING across rising lines.
  6. Asian handicap at line 0.0 ~= draw-no-bet (push-as-half-credit == DNB renorm).
  7. European handicap legs sum to 1.0; clean sheets / odd-even / margin in [0, 1].
  8. full_surface contains every catalog family and stays a coherent probability set.

HONEST: this tests COHERENCE of the pricing math only -- not calibration, not edge.

Run ONLY this file:
    python -m pytest tests/platform/test_soccer_markets.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from domains.soccer import markets as M
from domains.soccer.scoreline_engine import scoreline_matrix

TOL = 1e-9


@pytest.fixture(scope="module")
def P() -> np.ndarray:
    """A realistic non-degenerate scoreline matrix (home favourite, DC rho)."""
    return scoreline_matrix(1.7, 1.1, rho=-0.05)


# ---------------------------------------------------------------------------

def test_1x2_sums_to_one(P):
    mk = M.one_x_two(P)
    assert abs(mk["1X2_home"] + mk["1X2_draw"] + mk["1X2_away"] - 1.0) < TOL
    assert all(0.0 <= v <= 1.0 for v in mk.values())


def test_double_chance_equals_two_legs(P):
    o = M.one_x_two(P)
    dc = M.double_chance(P)
    assert abs(dc["dc_1X"] - (o["1X2_home"] + o["1X2_draw"])) < TOL
    assert abs(dc["dc_12"] - (o["1X2_home"] + o["1X2_away"])) < TOL
    assert abs(dc["dc_X2"] - (o["1X2_draw"] + o["1X2_away"])) < TOL


def test_dnb_renormalises_over_decisive_mass(P):
    o = M.one_x_two(P)
    dnb = M.draw_no_bet(P)
    decisive = o["1X2_home"] + o["1X2_away"]
    assert abs(dnb["dnb_home"] - o["1X2_home"] / decisive) < TOL
    assert abs(dnb["dnb_home"] + dnb["dnb_away"] - 1.0) < TOL


def test_btts_in_unit_interval_and_sums(P):
    b = M.btts(P)
    assert 0.0 <= b["btts_yes"] <= 1.0
    assert abs(b["btts_yes"] + b["btts_no"] - 1.0) < TOL


def test_totals_monotone_decreasing_in_line(P):
    t = M.totals(P)
    overs = [t[f"over_{ln:g}"] for ln in (0.5, 1.5, 2.5, 3.5, 4.5)]
    for a, b in zip(overs, overs[1:]):
        assert a >= b - TOL
        assert 0.0 <= b <= 1.0
    # over_0.5 == P(total >= 1) == 1 - P(0,0)
    assert abs(t["over_0.5"] - (1.0 - float(P[0, 0]))) < 1e-9


def test_asian_handicap_zero_equals_dnb(P):
    ah = M.asian_handicap(P, lines=(0.0,))
    dnb = M.draw_no_bet(P)
    # AH(0) home with push-as-half-credit equals the DNB home win prob.
    assert abs(ah["ah_home_0"] - dnb["dnb_home"]) < 1e-9


def test_asian_handicap_half_line_no_push(P):
    # -0.5 line: home covers iff home wins outright; equals 1X2 home.
    ah = M.asian_handicap(P, lines=(-0.5,))
    o = M.one_x_two(P)
    assert abs(ah["ah_home_-0.5"] - o["1X2_home"]) < TOL


def test_asian_handicap_quarter_line_is_average(P):
    ah = M.asian_handicap(P, lines=(-0.25, 0.0, -0.5))
    expected = 0.5 * (ah["ah_home_0"] + ah["ah_home_-0.5"])
    assert abs(ah["ah_home_-0.25"] - expected) < 1e-9


def test_european_handicap_legs_sum_to_one(P):
    eh = M.european_handicap(P, lines=(1,))
    for tag in ("home+1", "home-1"):
        s = eh[f"eh_{tag}_home"] + eh[f"eh_{tag}_draw"] + eh[f"eh_{tag}_away"]
        assert abs(s - 1.0) < TOL


def test_team_totals_and_marginals(P):
    tt = M.team_totals(P)
    # team_home_over_0.5 == P(home scores >= 1) == 1 - P(home == 0)
    assert abs(tt["team_home_over_0.5"] - (1.0 - float(P[0, :].sum()))) < 1e-9
    assert all(0.0 <= v <= 1.0 for v in tt.values())


def test_clean_sheet_and_odd_even(P):
    cs = M.clean_sheet(P)
    oe = M.odd_even(P)
    assert all(0.0 <= v <= 1.0 for v in cs.values())
    assert abs(oe["total_odd"] + oe["total_even"] - 1.0) < TOL


def test_winning_margin_partition(P):
    wm = M.winning_margin(P)
    # All margin buckets partition the full probability mass.
    assert abs(sum(wm.values()) - 1.0) < 1e-9
    assert all(0.0 <= v <= 1.0 for v in wm.values())


def test_full_surface_has_all_families(P):
    surf = M.full_surface(P, top_n=5)
    for k in ("1X2_home", "dc_1X", "dnb_home", "btts_yes", "over_2.5",
              "team_home_over_0.5", "ah_home_0", "eh_home+1_home",
              "total_odd", "cs_home_clean", "wm_draw"):
        assert k in surf, f"missing market family key: {k}"
    assert all(0.0 <= v <= 1.0 for v in surf.values())
    # at least 5 correct-score keys of the cs_<int>_<int> form
    n_cs = sum(1 for k in surf if k.split("_")[1:2] and k.startswith("cs_")
               and k.split("_")[1].isdigit())
    assert n_cs >= 5
