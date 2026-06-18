"""Per-file test for domains.soccer.prop_engine (network-free).

Run ONLY this file (full pytest freezes the box):
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_prop_engine.py -q
"""
from __future__ import annotations

import math

import pandas as pd

from domains.soccer.prop_engine import (
    _poisson_pmf,
    prop_distribution,
    prop_ladder,
)


def _row(pid, date, pos, minutes, **stats):
    base = {
        "player_id": pid, "date": date, "position": pos, "minutes": minutes,
        "starter": True,
        "totalShots": 0, "shotsOnTarget": 0, "foulsCommitted": 0,
        "foulsSuffered": 0, "yellowCards": 0, "redCards": 0, "goalAssists": 0,
        "offsides": 0, "totalGoals": 0, "saves": 0,
    }
    base.update(stats)
    return base


def _df():
    # Single player, single 90' match with 2 shots -> raw per90 = 2.0. With no
    # other players the F baseline == 2.0 too, so shrinkage leaves per90 = 2.0.
    return pd.DataFrame([_row("P1", "2026-06-01", "F", 90, totalShots=2)])


def test_poisson_pover_hand_checked():
    # Inject e_minutes=90 so lam = per90(2.0) * 90/90 = 2.0.
    dist = prop_distribution(_df(), "P1", "Shots", "2026-06-10", e_minutes=90.0)
    assert dist["status"] == "ok"
    assert dist["model"] == "poisson"
    assert abs(dist["lam"] - 2.0) < 1e-9
    # P(X > 2.5) for Poisson(2) = 1 - e^-2 (1 + 2 + 2) = 1 - 5 e^-2 = 0.3233236...
    expected = 1.0 - 5.0 * math.exp(-2.0)
    p = dist["p_over"](2.5)
    assert abs(p - expected) < 1e-6
    assert abs(expected - 0.32332358) < 1e-6


def test_pmf_sums_to_one():
    total = sum(_poisson_pmf(k, 2.0) for k in range(0, 50))
    assert abs(total - 1.0) < 1e-9


def test_ladder_monotone_non_increasing():
    ladder = prop_ladder(
        _df(), "P1", "Shots", "2026-06-10", [0.5, 1.5, 2.5, 3.5, 4.5],
        e_minutes=90.0,
    )
    povers = [e["p_over"] for e in ladder]
    assert all(p is not None for p in povers)
    for a, b in zip(povers, povers[1:]):
        assert b <= a + 1e-12  # non-increasing as line rises
    for e in ladder:
        assert abs((e["p_over"] + e["p_under"]) - 1.0) < 1e-9


def test_negbin_runs_and_differs():
    pois = prop_distribution(_df(), "P1", "Shots", "2026-06-10", e_minutes=90.0)
    nb = prop_distribution(
        _df(), "P1", "Shots", "2026-06-10", e_minutes=90.0, dispersion=3.0,
    )
    assert nb["status"] == "ok"
    assert nb["model"] == "negbin"
    assert abs(nb["lam"] - pois["lam"]) < 1e-9  # same mean
    # Over-dispersed NB has fatter tails -> p_over at a high line differs.
    assert abs(nb["p_over"](4.5) - pois["p_over"](4.5)) > 1e-6


def test_unknown_stat_unknown():
    dist = prop_distribution(_df(), "P1", "Tackles", "2026-06-10", e_minutes=90.0)
    assert dist["status"] == "unknown"
    assert dist["p_over"] is None


def test_unknown_minutes_unknown():
    # No history for this player and no e_minutes supplied -> unknown.
    dist = prop_distribution(_df(), "GHOST", "Shots", "2026-06-10")
    assert dist["status"] == "unknown"


def test_ladder_unknown_yields_none():
    ladder = prop_ladder(_df(), "P1", "Tackles", "2026-06-10", [0.5, 1.5])
    assert all(e["p_over"] is None and e["p_under"] is None for e in ladder)
