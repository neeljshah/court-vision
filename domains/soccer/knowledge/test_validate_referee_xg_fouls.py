"""Per-file test for knowledge.validate_referee_xg_fouls. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/knowledge/test_validate_referee_xg_fouls.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.soccer.knowledge import validate_referee_xg_fouls as vrf


def test_verdict_nan_p_is_not_testable_never_misclassified():
    assert vrf._verdict(float("nan"), 0.5, 0.05) == "NOT_TESTABLE"
    assert vrf._verdict(0.001, 0.5, 0.05) == "CONFIRMED_LOCAL"
    assert vrf._verdict(0.5, 0.5, 0.05) == "NULL_LOCAL"


def test_partial_r_removes_a_pure_confound():
    """Failure mode this guards: a shared confound z inflating raw r must be
    stripped out -- x and y here are independent given z is removed."""
    rng = np.random.RandomState(0)
    z = rng.normal(size=500)
    x = z + rng.normal(scale=0.01, size=500)
    y = z + rng.normal(scale=0.01, size=500)
    raw_r, _ = pd_corr(x, y)
    pr = vrf._partial_r(x, y, z)
    assert raw_r > 0.9  # confounded raw correlation is strong
    assert abs(pr) < 0.2  # partialling out z should mostly kill it


def pd_corr(x, y):
    from scipy import stats
    return stats.pearsonr(x, y)


def _synthetic_ms(n=200, seed=0):
    rng = np.random.RandomState(seed)
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    teams = ["T%d" % i for i in range(20)]
    home = rng.choice(teams, n)
    away = rng.choice(teams, n)
    fouls = rng.uniform(5, 20, n * 2)
    return pd.DataFrame({
        "event_id": ["m%d" % i for i in range(n)], "date": dates,
        "home_team": home, "away_team": away,
        "home_fouls": fouls[:n], "away_fouls": fouls[n:],
        "home_sot": rng.uniform(1, 10, n), "away_sot": rng.uniform(1, 10, n),
        "total_shots": rng.uniform(10, 30, n),
    })


def test_referee_persistence_not_testable_below_min_referees():
    ms = _synthetic_ms(n=30)
    ref = pd.DataFrame({"event_id": ms["event_id"], "referee": ["R1"] * 30,
                         "total_fouls": [10.0] * 30, "total_cards": [3.0] * 30})
    r = vrf.referee_card_rate_persistence_at_scale(ref, ms)
    assert r["verdict"] == "NOT_TESTABLE" and r["p"] is None


def test_xg_supremacy_persistence_not_testable_below_min_teams():
    ms = _synthetic_ms(n=30)
    axg = pd.DataFrame({"event_id": ms["event_id"],
                         "home_xg_supremacy_asof": np.random.RandomState(1).normal(size=30),
                         "away_xg_supremacy_asof": np.random.RandomState(2).normal(size=30)})
    r = vrf.xg_supremacy_persistence(axg, ms)
    assert r["verdict"] == "NOT_TESTABLE" and r["p"] is None


def test_fouls_suppress_opponent_sot_runs_and_returns_finite_stats():
    ms = _synthetic_ms(n=200)
    r = vrf.fouls_suppress_opponent_sot(ms)
    assert r["n"] == 400  # pooled both sides
    assert r["p"] == r["p"]  # not NaN
    assert r["verdict"] in ("CONFIRMED_LOCAL", "NULL_LOCAL")


def test_run_writes_three_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vrf, "LEDGER_PATH", ledger)
    ms = _synthetic_ms(n=200)
    ref = pd.DataFrame({"event_id": ms["event_id"],
                         "referee": np.random.RandomState(3).choice(["R1", "R2", "R3"], 200),
                         "total_fouls": np.random.RandomState(4).uniform(5, 25, 200),
                         "total_cards": np.random.RandomState(5).uniform(0, 8, 200)})
    axg = pd.DataFrame({"event_id": ms["event_id"],
                         "home_xg_supremacy_asof": np.random.RandomState(6).normal(size=200),
                         "away_xg_supremacy_asof": np.random.RandomState(7).normal(size=200)})
    monkeypatch.setattr(vrf, "load_referee_profiles", lambda: ref)
    monkeypatch.setattr(vrf, "load_match_stats", lambda: ms)
    monkeypatch.setattr(vrf, "load_xg_proxy", lambda: axg)
    rows = vrf.run()
    assert len(rows) == 3
    assert all(r["edge_claimed"] is False and r["sport"] == "soccer" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 3
