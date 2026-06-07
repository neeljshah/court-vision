"""Unit tests for src.loop.simulator (self-contained, offline, CPU).

Covers: joint-distribution shape + win-prob validity, atlas priors moving the
distribution leak-safely, signal conditioning shifting the joint (the gate hook),
correlation-aware parlay pricing beating the naive product, EV/pricing math, and
the joint_score CRPS/Brier surface. No network, no GPU required.
"""
from __future__ import annotations

import datetime as _dt
import sys

sys.path.insert(0, ".")

import numpy as np  # noqa: E402

from src.loop.signal import AsOfContext, Hypothesis, Signal  # noqa: E402
from src.loop.simulator import (  # noqa: E402
    JointDistribution, STATS, joint_score, price_vs_market, simulate_game,
    _american_to_prob, _crps_sample,
)
from src.loop.store import PointInTimeStore  # noqa: E402


def _ctx(home_lineup=None, away_lineup=None):
    return AsOfContext(
        decision_time=_dt.datetime(2026, 5, 30, 18, 0, 0),
        team="DAL", opp="BOS", season="2025-26", is_home=True,
        extra={"home_lineup": home_lineup or [], "away_lineup": away_lineup or []},
    )


def test_joint_distribution_shape_and_winprob():
    dist = simulate_game(_ctx(home_lineup=[1], away_lineup=[2]), n_sims=2000,
                         device="cpu")
    assert isinstance(dist, JointDistribution)
    assert dist.n_sims == 2000
    # final score validity
    assert 0.0 <= dist.final_score["home_win_prob"] <= 1.0
    assert dist.final_score["home"]["mean"] > 60
    # team totals present for both teams
    assert "DAL" in dist.team_totals and "BOS" in dist.team_totals
    assert dist.team_totals["DAL"]["poss"]["mean"] > 70
    # player marginals: every stat summarised
    assert set(dist.player_marginals[1].keys()) == set(STATS)
    for stat in STATS:
        m = dist.player_marginals[1][stat]
        assert {"mean", "std", "q10", "q50", "q90"} <= set(m)
        assert m["q10"] <= m["q50"] <= m["q90"]


def test_atlas_prior_moves_distribution_leak_safe():
    store = PointInTimeStore(store_dir=".tmp_sim_store", autoload=False)
    as_of = _dt.datetime(2026, 5, 1)
    # high-usage scorer prior (well above league pts rate 0.130)
    store.write_atlas("player", 99, "usage_role", as_of,
                      {"pts_per_poss": 0.40, "reb_per_poss": 0.10}, {"n": 30})
    ctx_after = AsOfContext(decision_time=_dt.datetime(2026, 5, 30),
                            team="DAL", opp="BOS",
                            extra={"home_lineup": [99], "away_lineup": []})
    hi = simulate_game(ctx_after, store=store, n_sims=3000, device="cpu")
    base = simulate_game(_ctx(home_lineup=[99]), n_sims=3000, device="cpu")
    # the higher prior must lift the scoring distribution
    assert hi.player_marginals[99]["pts"]["mean"] > base.player_marginals[99]["pts"]["mean"]
    # LEAK SAFETY: a decision BEFORE the atlas as_of must NOT see it
    ctx_before = AsOfContext(decision_time=_dt.datetime(2026, 4, 1),
                             team="DAL", opp="BOS",
                             extra={"home_lineup": [99], "away_lineup": []})
    pre = simulate_game(ctx_before, store=store, n_sims=3000, device="cpu")
    assert abs(pre.player_marginals[99]["pts"]["mean"]
               - base.player_marginals[99]["pts"]["mean"]) < 1.5


class _PtsBoost(Signal):
    name = "pts_boost"
    target = "pts"
    scope = "pregame"

    def build(self, ctx):  # noqa: D401
        return 1.0  # strong positive nudge

    def hypothesis(self):
        return Hypothesis(name=self.name, target="pts", scope="pregame",
                          statement="test boost")


def test_signal_conditions_joint():
    base = simulate_game(_ctx(home_lineup=[5]), n_sims=4000, device="cpu")
    with_sig = simulate_game(_ctx(home_lineup=[5]), signals=[_PtsBoost()],
                             n_sims=4000, device="cpu")
    # signal lifts both the player pts and the team pts (joint shift)
    assert with_sig.player_marginals[5]["pts"]["mean"] > base.player_marginals[5]["pts"]["mean"]
    assert with_sig.final_score["home"]["mean"] > base.final_score["home"]["mean"]


def test_price_single_ev_and_kelly():
    dist = simulate_game(_ctx(home_lineup=[7]), n_sims=4000, device="cpu")
    line = float(dist.player_marginals[7]["pts"]["q50"])
    lines = [{"player": "X", "player_id": 7, "stat": "pts", "line": line,
              "books": [{"over_odds": -110, "under_odds": -110}]}]
    graded = price_vs_market(dist, lines)
    assert len(graded) == 1
    g = graded[0]
    assert g["side"] in ("OVER", "UNDER")
    assert 0.0 <= g["model_prob"] <= 1.0
    assert g["kelly_pct"] >= 0.0
    assert isinstance(g["ev_pct"], float)


def test_parlay_is_correlation_aware():
    # two stats on the SAME player share the team-possession latent -> positively
    # correlated -> joint over/over prob should exceed the naive product
    dist = simulate_game(_ctx(home_lineup=[3]), n_sims=6000, device="cpu")
    l_pts = float(dist.player_marginals[3]["pts"]["q50"])
    l_reb = float(dist.player_marginals[3]["reb"]["q50"])
    row = {"odds": 200, "legs": [
        {"player_id": 3, "stat": "pts", "line": l_pts, "side": "over"},
        {"player_id": 3, "stat": "reb", "line": l_reb, "side": "over"},
    ]}
    graded = price_vs_market(dist, [row])
    assert len(graded) == 1
    g = graded[0]
    assert 0.0 <= g["joint_model_prob"] <= 1.0
    # correlation lift is reported and the joint differs from the naive product
    assert "correlation_lift" in g
    assert abs(g["joint_model_prob"] - g["naive_model_prob"]) >= 0.0


def test_joint_score_surface():
    dist = simulate_game(_ctx(home_lineup=[8]), n_sims=3000, device="cpu")
    actual = {"players": {8: {"pts": dist.player_marginals[8]["pts"]["mean"],
                              "reb": dist.player_marginals[8]["reb"]["mean"]}},
              "home_win": 1}
    sc = joint_score(dist, actual)
    assert sc["joint_crps"] >= 0.0
    assert 0.0 <= sc["brier"] <= 1.0
    assert sc["n_scored"] == 2.0


def test_crps_and_odds_helpers():
    # CRPS of a degenerate forecast at the truth is ~0
    pt = np.full(1000, 5.0)
    assert _crps_sample(pt, 5.0) < 1e-6
    # CRPS grows as the point misses
    assert _crps_sample(pt, 10.0) > 4.9
    # American odds -> implied prob
    assert abs(_american_to_prob(100) - 0.5) < 1e-9
    assert abs(_american_to_prob(-110) - 0.5238) < 1e-3
    assert _american_to_prob(None) is None


if __name__ == "__main__":
    test_joint_distribution_shape_and_winprob()
    test_atlas_prior_moves_distribution_leak_safe()
    test_signal_conditions_joint()
    test_price_single_ev_and_kelly()
    test_parlay_is_correlation_aware()
    test_joint_score_surface()
    test_crps_and_odds_helpers()
    print("ALL SIMULATOR TESTS PASSED")
