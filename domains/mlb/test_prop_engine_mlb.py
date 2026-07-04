"""Per-file tests for domains/mlb/prop_engine_mlb.py (canned in-memory df).

  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/test_prop_engine_mlb.py -q
"""
from __future__ import annotations

import math

import pandas as pd

from domains.mlb.prop_engine_mlb import prop_distribution, prop_ladder


def test_known_lam_poisson_p_over_handchecked():
    # Hand Poisson: lam = 1.5, P(X > 1.5) = 1 - e^-1.5 (1 + 1.5) = 0.44217...
    # Force lam directly: per_pa via a single PA with 1.5 "Hits" is not integer,
    # so instead build a batter whose per_pa * exposure = 1.5 exactly.
    # 3 PA, 3 hits => per_pa = 1.0; pass exposure=1.5 => lam = 1.5.
    df = pd.DataFrame([dict(
        date="2026-05-01", player_id="A", is_pitcher=False, atBats=3,
        baseOnBalls=0, hitByPitch=0, hits=3, totalBases=3, runs=0, rbi=0,
        homeRuns=0, strikeOuts=0, stolenBases=0)])
    # No league baseline besides A itself -> shrinks toward own rate (baseline==own),
    # so per_pa stays 1.0. lam = 1.0 * 1.5 = 1.5.
    dist = prop_distribution(df, "A", "Hits", as_of="2026-06-01", exposure=1.5)
    assert dist["status"] == "ok"
    assert abs(dist["lam"] - 1.5) < 1e-9
    expected = 1.0 - math.exp(-1.5) * (1.0 + 1.5)
    assert abs(dist["p_over"](1.5) - expected) < 1e-9
    assert abs(expected - 0.4421745996) < 1e-6


def test_pitcher_strikeouts_with_exposure():
    df = pd.DataFrame([dict(
        date="2026-05-01", player_id="P", is_pitcher=True, battersFaced=25,
        pitch_strikeOuts=10, earnedRuns=2, hits_allowed=5,
        baseOnBalls_allowed=1, outs=18)])
    # per_bf = 10/25 = 0.4 (only pitcher -> baseline==own). exposure=25 -> lam=10.
    dist = prop_distribution(df, "P", "Pitcher Strikeouts", as_of="2026-06-01",
                             exposure=25.0)
    assert dist["status"] == "ok"
    assert abs(dist["lam"] - 10.0) < 1e-9
    p = dist["p_over"](6.5)
    assert 0.0 < p < 1.0  # mean 10, so P(K>6.5) should be high
    assert p > 0.8


def test_negbin_path_widens_tails():
    df = pd.DataFrame([dict(
        date="2026-05-01", player_id="P", is_pitcher=True, battersFaced=25,
        pitch_strikeOuts=10, earnedRuns=2, hits_allowed=5,
        baseOnBalls_allowed=1, outs=18)])
    pois = prop_distribution(df, "P", "Pitcher Strikeouts", as_of="2026-06-01",
                             exposure=25.0)
    nb = prop_distribution(df, "P", "Pitcher Strikeouts", as_of="2026-06-01",
                           exposure=25.0, dispersion=5.0)
    assert nb["model"] == "negbin"
    assert pois["model"] == "poisson"
    # Over-dispersed NB puts more mass in the upper tail than Poisson(10).
    assert nb["p_over"](14.5) > pois["p_over"](14.5)


def test_outs_per_start_no_exposure_needed():
    df = pd.DataFrame([dict(
        date="2026-05-01", player_id="P", is_pitcher=True, battersFaced=25,
        pitch_strikeOuts=10, earnedRuns=2, hits_allowed=5,
        baseOnBalls_allowed=1, outs=18)])
    # Outs is per-start: lam = per_start = 18 directly (no exposure multiply).
    dist = prop_distribution(df, "P", "Outs", as_of="2026-06-01")
    assert dist["status"] == "ok"
    assert abs(dist["lam"] - 18.0) < 1e-9


def test_unknown_stat_and_no_data():
    df = pd.DataFrame([dict(
        date="2026-05-01", player_id="A", is_pitcher=False, atBats=3,
        baseOnBalls=0, hitByPitch=0, hits=3, totalBases=3, runs=0, rbi=0,
        homeRuns=0, strikeOuts=0, stolenBases=0)])
    assert prop_distribution(df, "A", "NotAStat", as_of="2026-06-01")["status"] \
        == "unknown"
    # Unknown player + no league signal -> unknown.
    assert prop_distribution(df, "ZZ", "Hits", as_of="2000-01-01")["status"] \
        == "unknown"


def test_prop_ladder_keys_and_unknown():
    df = pd.DataFrame([dict(
        date="2026-05-01", player_id="A", is_pitcher=False, atBats=3,
        baseOnBalls=0, hitByPitch=0, hits=3, totalBases=3, runs=0, rbi=0,
        homeRuns=0, strikeOuts=0, stolenBases=0)])
    lad = prop_ladder(df, "A", "Hits", as_of="2026-06-01", lines=[0.5, 1.5, 2.5],
                      exposure=1.5)
    assert [r["line"] for r in lad] == [0.5, 1.5, 2.5]
    for r in lad:
        assert 0.0 <= r["p_over"] <= 1.0
        assert abs(r["p_over"] + r["p_under"] - 1.0) < 1e-9
    # unknown -> None probabilities, never fabricated
    bad = prop_ladder(df, "A", "NotAStat", as_of="2026-06-01", lines=[0.5])
    assert bad[0]["p_over"] is None and bad[0]["p_under"] is None


def test_cache_reused_across_lines_matches_uncached_lam():
    """PERF (m13 prop-edge-budget lane): a shared per-cycle cache dict, reused
    across TWO different lines/stats/players (as a real score cycle would),
    must yield lam values identical to the uncached per-line calls -- the memo
    is purely a performance optimization, never a correctness change."""
    df = pd.DataFrame([
        dict(date="2026-05-01", player_id="A", is_pitcher=False, atBats=3,
             baseOnBalls=0, hitByPitch=0, hits=3, totalBases=3, runs=0, rbi=0,
             homeRuns=0, strikeOuts=0, stolenBases=0),
        dict(date="2026-05-01", player_id="P", is_pitcher=True, battersFaced=25,
             pitch_strikeOuts=10, earnedRuns=2, hits_allowed=5,
             baseOnBalls_allowed=1, outs=18),
    ])
    cache: dict = {}
    d1 = prop_distribution(df, "A", "Hits", as_of="2026-06-01", exposure=1.5, cache=cache)
    d2 = prop_distribution(df, "P", "Pitcher Strikeouts", as_of="2026-06-01",
                           exposure=25.0, cache=cache)
    u1 = prop_distribution(df, "A", "Hits", as_of="2026-06-01", exposure=1.5)
    u2 = prop_distribution(df, "P", "Pitcher Strikeouts", as_of="2026-06-01",
                           exposure=25.0)
    assert d1["lam"] == u1["lam"] and d1["status"] == u1["status"]
    assert d2["lam"] == u2["lam"] and d2["status"] == u2["status"]
