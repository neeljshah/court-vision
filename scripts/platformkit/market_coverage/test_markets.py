"""Per-file tests for market_coverage.markets -- the EVERY-MARKET pricer.

Run ONLY this file (full-suite pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && \
    C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
    scripts/platformkit/market_coverage/test_markets.py -q

Covers: the 7-family taxonomy, pure-function counting, joint correlation LIFT, the
independent-book refusal (kernel boundary), tier honesty tags, live relabeling, and
the generic (mlb/soccer/tennis) path. No edge / $ is asserted -- only that prices are
correct counts off the SAME coherent samples (the sim authors the number).
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.market_coverage import markets as M


def _book(n=4000, seed=0):
    """A coherent SampleBook: 1 star + 1 role player (correlated stats) + two teams + quarters."""
    rng = np.random.default_rng(seed)
    cols, data = {}, []

    def ac(name, arr):
        cols[name] = len(data); data.append(np.asarray(arr, dtype=float))

    spts = rng.normal(28, 8, n).clip(0)
    ac("1|pts", spts)
    ac("1|reb", (spts * 0.25 + rng.normal(3, 2, n)).clip(0))   # +corr with pts
    ac("1|ast", rng.normal(7, 3, n).clip(0))
    ac("1|fg3m", rng.poisson(2.5, n).astype(float))
    ac("1|stl", rng.poisson(1.2, n).astype(float))
    ac("1|blk", rng.poisson(0.8, n).astype(float))
    ac("2|pts", rng.normal(12, 5, n).clip(0))
    ac("2|reb", rng.normal(5, 2, n).clip(0))
    ac("2|ast", rng.normal(3, 2, n).clip(0))
    hq = [rng.normal(28, 5, n) for _ in range(4)]
    aq = [rng.normal(27, 5, n) for _ in range(4)]
    for i in range(4):
        ac(f"home_q{i+1}", hq[i]); ac(f"away_q{i+1}", aq[i])
    ac("home_score", sum(hq)); ac("away_score", sum(aq))
    return M.SampleBook(np.stack(data, axis=1), cols, joint_quality="simulated")


def test_seven_families_enumerated():
    assert len(M.FAMILIES) == 7
    assert set(M.FAMILIES) == {
        "player-props-core", "player-props-combos", "team-quarter-half",
        "game-scenario-longshot", "sgp-correlation", "mlb-soccer-tennis", "ingame-micro",
    }


def test_build_menu_covers_basketball_families():
    menu = M.build_menu(_book())
    fams = {M.family_of(m) for m in menu}
    # the four basketball-only families are produced from a basketball book
    assert {"player-props-core", "player-props-combos",
            "team-quarter-half", "game-scenario-longshot"} <= fams
    assert len(menu) > 40


def test_prob_is_a_pure_count():
    book = _book()
    leg = M.stat_over(book, "1|pts", 27.5)
    p = M.price_single(book, M.Leg("x", leg))["prob"]
    assert p == pytest.approx(float((book.col("1|pts") > 27.5).mean()))
    assert 0.0 <= p <= 1.0


def test_fair_decimal_is_reciprocal():
    book = _book()
    q = M.price_single(book, M.Leg("x", M.stat_over(book, "1|pts", 27.5)))
    assert q["fair_decimal"] == pytest.approx(1.0 / q["prob"])


def test_sgp_joint_lift_positive_for_same_player_pts_reb():
    """Same-player pts & reb are positively correlated -> joint > independence product (lift>1).
    This is the whole edge over a marginal prop model; independence UNDER-prices it."""
    book = _book()
    legs = [M.Leg("a", M.stat_over(book, "1|pts", 29.5)),
            M.Leg("b", M.stat_over(book, "1|reb", 9.5))]
    r = M.price_joint(book, legs)
    assert r["lift"] > 1.05
    assert r["correlation_sign"] == "positive"
    expect = float(((book.col("1|pts") > 29.5) & (book.col("1|reb") > 9.5)).mean())
    assert r["joint"] == pytest.approx(expect)
    assert r["tier"] == "JOINT_PENDING"


def test_price_joint_refuses_independent_book():
    """Kernel boundary (sgp_from_sim): pricing correlated legs off an independent book is refused."""
    rng = np.random.default_rng(1)
    cols = {"1|pts": 0, "1|reb": 1}
    book = M.SampleBook(rng.normal(20, 6, (1000, 2)), cols, joint_quality="independent")
    with pytest.raises(ValueError):
        M.price_joint(book, [M.Leg("x", M.stat_over(book, "1|pts", 19.5))])


def test_price_joint_requires_legs():
    with pytest.raises(ValueError):
        M.price_joint(_book(), [])


def test_combo_tiers_are_joint_pending_or_longshot():
    menu = {m.name: m for m in M.build_menu(_book())}
    assert menu["1|double_double"].tier == "JOINT_PENDING"
    assert menu["1|triple_double"].tier == "LONGSHOT"
    assert menu["1|5x5"].tier == "LONGSHOT"


def test_team_total_overs_are_total_biased():
    menu = M.build_menu(_book())
    tts = [m for m in menu if "team_total_over" in m.name or "game_total_over" in m.name]
    assert tts and all(m.tier == "TOTAL_BIASED" for m in tts)


def test_longshot_tier_for_rare_tail():
    """A very high points line is a thin-tail LONGSHOT/TAIL market, honestly tagged."""
    book = _book()
    q = M.price_single(book, M.Leg("x", M.stat_over(book, "1|pts", 49.5)))
    assert q["tier"] in ("LONGSHOT", "TAIL_APPROX")
    assert q["prob"] < 0.13


def test_live_relabels_to_ingame_micro():
    live = M.build_menu(_book(), live=True)
    assert all(m.kind == "ingame" for m in live)
    assert {M.family_of(m) for m in live} == {"ingame-micro"}


def test_generic_market_is_mlb_soccer_tennis():
    """A bare column (e.g. a soccer/MLB/tennis outcome vector) -> mlb-soccer-tennis family."""
    rng = np.random.default_rng(2)
    book = M.SampleBook(rng.normal(8.5, 3, (2000, 1)), {"total_runs": 0})
    menu = M.build_menu(book)
    assert len(menu) == 1
    assert M.family_of(menu[0]) == "mlb-soccer-tennis"
    assert "total_runs" in menu[0].name


def test_determinism_same_seed_same_prices():
    p1 = M.price_single(_book(seed=7), M.Leg("x", M.stat_over(_book(seed=7), "1|pts", 27.5)))
    p2 = M.price_single(_book(seed=7), M.Leg("x", M.stat_over(_book(seed=7), "1|pts", 27.5)))
    assert p1["prob"] == p2["prob"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
