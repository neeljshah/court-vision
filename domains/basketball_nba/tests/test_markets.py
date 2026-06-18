"""Per-file pytest for the NBA market surface + player-prop pricer coherence.

Run ONLY as:
    python -m pytest domains/basketball_nba/tests/test_markets.py -q

NEVER run the full suite (it freezes the box). The market tests use a tiny FAKE
predictor exposing the same (predict + total_sigma + margin_sigma) contract, so the
closed-form math is checked without building the real corpus. The player-prop tests
load the real local parquet if present and skip cleanly otherwise.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from domains.basketball_nba import markets


class _FakePredictor:
    """Minimal stand-in matching predictor.py's market contract."""

    def __init__(self, p_home=0.62, total_mean=224.0, total_sigma=18.0,
                 margin_sigma=13.5):
        self.total_sigma = total_sigma
        self.margin_sigma = margin_sigma
        self._p = p_home
        self._t = total_mean

    def predict(self, home, away, total_lines=None):
        return {"p_home_win": self._p, "total_mean": self._t,
                "total_sigma": self.total_sigma}


@pytest.fixture
def pred():
    return _FakePredictor()


# --- coherence: spread at pick'em == moneyline -----------------------------
def test_spread_at_pickem_equals_moneyline(pred):
    ml = markets.moneyline(pred, "BOS", "LAL")["p_home_win"]
    sp = markets.spread(pred, "BOS", "LAL", 0.0)["p_home_cover"]
    assert abs(ml - sp) < 1e-3
    # and both equal the predictor's p_home_win within the ndtri/phi roundtrip
    assert abs(ml - pred._p) < 2e-3


# --- coherence: team totals sum to the game total --------------------------
def test_team_totals_sum_to_game_total(pred):
    g = markets.game_distribution(pred, "BOS", "LAL")
    h = markets.team_total(pred, "BOS", "LAL", "home", 110.5)["team_mean"]
    a = markets.team_total(pred, "BOS", "LAL", "away", 110.5)["team_mean"]
    assert abs((h + a) - g["total_mean"]) < 0.2


def test_team_total_home_minus_away_equals_margin(pred):
    g = markets.game_distribution(pred, "BOS", "LAL")
    h = markets.team_total(pred, "BOS", "LAL", "home", 110.5)["team_mean"]
    a = markets.team_total(pred, "BOS", "LAL", "away", 110.5)["team_mean"]
    assert abs((h - a) - g["margin_mean"]) < 0.2


# --- monotonicity: P(over) decreasing in the line --------------------------
def test_total_over_monotonic_in_line(pred):
    lines = [200, 210, 220, 230, 240]
    overs = [markets.total(pred, "BOS", "LAL", ln)["over"] for ln in lines]
    assert all(overs[i] >= overs[i + 1] for i in range(len(overs) - 1))


def test_spread_cover_monotonic_in_line(pred):
    # higher home handicap line (more points given to home) => higher cover prob
    lines = [-12.5, -6.5, 0.0, 6.5, 12.5]
    covers = [markets.spread(pred, "BOS", "LAL", ln)["p_home_cover"] for ln in lines]
    assert all(covers[i] <= covers[i + 1] for i in range(len(covers) - 1))


def test_team_total_over_monotonic(pred):
    lines = [95, 105, 110, 120, 130]
    overs = [markets.team_total(pred, "BOS", "LAL", "home", ln)["over"] for ln in lines]
    assert all(overs[i] >= overs[i + 1] for i in range(len(overs) - 1))


# --- probabilities are valid + complementary --------------------------------
def test_probs_complementary(pred):
    t = markets.total(pred, "BOS", "LAL", 224.0)
    assert abs(t["over"] + t["under"] - 1.0) < 1e-6
    s = markets.spread(pred, "BOS", "LAL", -3.5)
    assert abs(s["p_home_cover"] + s["p_away_cover"] - 1.0) < 1e-6


# --- full surface is populated + period markets coherent --------------------
def test_full_surface_keys(pred):
    surf = markets.full_surface(pred, "BOS", "LAL")
    for k in ("moneyline", "spread_main", "spread_ladder", "total_main",
              "total_ladder", "team_total_home", "team_total_away",
              "first_half", "q1", "q2", "q3", "q4"):
        assert k in surf, f"missing {k}"
    assert len(surf["spread_ladder"]) > 5
    # first half total mean ~ half the game total
    assert abs(surf["first_half"]["period_total_mean"]
               - surf["total_main"] / 2.0) < 0.5


def test_period_total_scales_with_fraction(pred):
    g = markets.game_distribution(pred, "BOS", "LAL")
    q1 = markets.period_markets(pred, "BOS", "LAL", "q1")
    assert abs(q1["period_total_mean"] - g["total_mean"] * 0.25) < 0.2


def test_underdog_home_spread_below_half(pred):
    dog = _FakePredictor(p_home=0.35)
    assert markets.spread(dog, "BOS", "LAL", 0.0)["p_home_cover"] < 0.5


# --- player props (real local parquet; skip cleanly if absent) -------------
_BOX = Path("data/domains/basketball_nba/player_boxscores.parquet")


@pytest.mark.skipif(not _BOX.exists(), reason="player box corpus not on this clone")
def test_player_prop_leakfree_and_monotonic():
    from domains.basketball_nba import player_props as pp
    df = pp.load_box()
    # pick a high-minutes player/date with ample prior history
    row = df.sort_values("date").iloc[len(df) // 2]
    player, date = row["player_name"], row["date"]
    overs = [pp.price_prop(player, "pts", ln, date, df=df)["p_over"]
             for ln in (5.5, 15.5, 25.5, 35.5)]
    overs = [o for o in overs if o is not None]
    if len(overs) >= 2:
        assert all(overs[i] >= overs[i + 1] for i in range(len(overs) - 1))


@pytest.mark.skipif(not _BOX.exists(), reason="player box corpus not on this clone")
def test_player_prop_no_future_leak():
    from domains.basketball_nba import player_props as pp
    df = pp.load_box()
    early = df["date"].min()
    # before the corpus starts -> zero history -> insufficient, never a fabricated number
    out = pp.price_prop(df.iloc[0]["player_name"], "pts", 10.5, early, df=df)
    assert out["status"] == "insufficient_history"
    assert out["p_over"] is None


@pytest.mark.skipif(not _BOX.exists(), reason="player box corpus not on this clone")
def test_player_card_populated():
    from domains.basketball_nba import player_props as pp
    df = pp.load_box()
    row = df.sort_values("date").iloc[len(df) - 50]
    card = pp.price_player_card(row["player_name"], row["date"], df=df)
    assert set(card["props"]) >= {"pts", "reb", "ast", "fg3m", "pra"}
    assert "double_double" in card
