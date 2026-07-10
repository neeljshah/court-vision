"""Per-file test for knowledge.validate_research_wave3. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/knowledge/test_validate_research_wave3.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from domains.basketball_nba.knowledge import validate_research_wave3 as vrw3


def test_self_check():
    vrw3._self_check()


def test_band_assignment_boundaries():
    assert vrw3._band(0) == 0
    assert vrw3._band(9.99) == 0
    assert vrw3._band(10) == 1
    assert vrw3._band(29.99) == 2
    assert vrw3._band(30) == 3
    assert vrw3._band(100) == 3


def test_build_dataset_joins_starter_minutes_onto_team_games(monkeypatch):
    box = pd.DataFrame([
        {"game_id": "g1", "team": "BOS", "date": pd.Timestamp("2026-01-01"), "season": "2025-26",
         "is_home": 1, "starter": True, "min": 30.0, "pts": 20},
        {"game_id": "g1", "team": "BOS", "date": pd.Timestamp("2026-01-01"), "season": "2025-26",
         "is_home": 1, "starter": False, "min": 10.0, "pts": 5},
        {"game_id": "g1", "team": "PHI", "date": pd.Timestamp("2026-01-01"), "season": "2025-26",
         "is_home": 0, "starter": True, "min": 25.0, "pts": 15},
    ])
    monkeypatch.setattr(vrw3, "load_player_boxscores", lambda: box)
    d = vrw3.build_dataset()
    assert set(d["team"]) == {"BOS", "PHI"}
    bos = d[d["team"] == "BOS"].iloc[0]
    assert bos["starter_minutes"] == 30.0  # only the starter row's minutes, bench row excluded
    assert bos["abs_margin"] == abs(bos["margin"])


def test_trend_verdict_not_testable_below_group_floor():
    small = pd.DataFrame({"date": pd.to_datetime(["2026-01-01"] * 5), "abs_margin": [5.0] * 5,
                           "starter_minutes": [160.0] * 5})
    r = vrw3._trend_verdict(small, "h1")
    assert r["verdict"] == "NOT_TESTABLE"


def test_trend_verdict_confirms_clear_negative_slope():
    d = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01"] * 30 + ["2026-01-02"] * 30 + ["2026-01-03"] * 30 + ["2026-01-04"] * 30),
        "abs_margin": [5.0] * 30 + [15.0] * 30 + [25.0] * 30 + [35.0] * 30,
        "starter_minutes": [160.0] * 30 + [150.0] * 30 + [140.0] * 30 + [125.0] * 30,
    })
    r = vrw3._trend_verdict(d, "h1")
    assert r["verdict"] == "CONFIRMED_LOCAL"
    assert r["effect"] <= -0.05


def test_interaction_verdict_not_testable_when_is_b2b_degenerate():
    d = pd.DataFrame({"abs_margin": [5.0, 10.0, 15.0], "is_b2b": [0, 0, 0],
                       "starter_minutes": [160.0, 150.0, 140.0]})
    r = vrw3._interaction_verdict(d, "h1")
    assert r["verdict"] == "NOT_TESTABLE"


def test_combine_halves_needs_both_confirmed_same_sign():
    confirmed_pos = {"hypothesis": "x__h1", "n": 30, "effect": 0.5, "p": 0.001, "verdict": "CONFIRMED_LOCAL"}
    confirmed_neg = {"hypothesis": "x__h2", "n": 30, "effect": -0.5, "p": 0.001, "verdict": "CONFIRMED_LOCAL"}
    out = vrw3._combine_halves([confirmed_pos, confirmed_neg], "x")
    assert out["verdict"] == "NULL_LOCAL"  # opposite signs -- not a real replication

    out2 = vrw3._combine_halves([confirmed_pos, dict(confirmed_pos, hypothesis="x__h2")], "x")
    assert out2["verdict"] == "CONFIRMED_LOCAL"


def test_run_writes_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vrw3, "LEDGER_PATH", ledger)
    rows = []
    for i in range(30):
        date = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
        rows.append({"game_id": "g%d" % i, "team": "BOS", "date": date, "season": "2025-26",
                     "is_home": 1, "starter": True, "min": 150.0 - i, "pts": 100 + i})
        rows.append({"game_id": "g%d" % i, "team": "PHI", "date": date, "season": "2025-26",
                     "is_home": 0, "starter": True, "min": 140.0, "pts": 90})
    box = pd.DataFrame(rows)
    monkeypatch.setattr(vrw3, "load_player_boxscores", lambda: box)

    rows = vrw3.run()
    assert len(rows) >= 6  # 3 rows x 2 hypotheses
    assert all(r["edge_claimed"] is False and r["sport"] == "basketball_nba" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == len(rows)
    for l in on_disk:
        json.loads(l)  # every line is valid standalone JSON
