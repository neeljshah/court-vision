"""Per-file test for knowledge.validate_research_wave4. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/knowledge/test_validate_research_wave4.py -q
"""
from __future__ import annotations

import json

import pandas as pd

from domains.basketball_nba.knowledge import validate_research_wave4 as vrw4


def test_self_check():
    vrw4._self_check()


def test_build_dataset_drops_thin_team_seasons():
    box = pd.DataFrame([
        {"game_id": "g1", "team": "BOS", "season": "2025-26", "date": pd.Timestamp("2026-01-01"), "pf": 20.0},
        {"game_id": "g1", "team": "PHI", "season": "2025-26", "date": pd.Timestamp("2026-01-01"), "pf": 18.0},
    ])
    d = vrw4.build_dataset(box)
    assert d.empty  # only 1 game per team-season, below MIN_GAMES_PER_TEAM_SEASON


def test_build_dataset_computes_leave_one_out_lambda():
    rows = []
    for i in range(vrw4.MIN_GAMES_PER_TEAM_SEASON):
        date = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
        rows.append({"game_id": "g%d" % i, "team": "BOS", "season": "2025-26", "date": date, "pf": 20.0})
        rows.append({"game_id": "g%d" % i, "team": "PHI", "season": "2025-26", "date": date, "pf": 18.0})
    box = pd.DataFrame(rows)
    d = vrw4.build_dataset(box)
    assert len(d) == vrw4.MIN_GAMES_PER_TEAM_SEASON
    row = d.iloc[0]
    # BOS LOO mean excludes its own 20.0 game -> still 20.0 (constant series); same for PHI's 18.0
    assert row["lambda"] == 38.0
    assert row["observed"] == 38.0


def test_dispersion_verdict_not_testable_below_floor():
    small = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=2), "lambda": [40.0, 40.0],
                           "observed": [41, 39]})
    r = vrw4._dispersion_verdict(small, "h1")
    assert r["verdict"] == "NOT_TESTABLE"


def test_dispersion_verdict_confirms_clear_outlier_dispersion():
    d = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=5), "lambda": [40.0] * 5,
                       "observed": [42, 39, 41, 90, 38]})
    r = vrw4._dispersion_verdict(d, "h1")
    assert r["verdict"] == "CONFIRMED_LOCAL"
    assert r["effect"] >= vrw4.PHI_THRESHOLD


def test_combine_halves_needs_both_confirmed():
    confirmed = {"hypothesis": "x__h1", "n": 5, "effect": 1.5, "p": 0.001, "verdict": "CONFIRMED_LOCAL"}
    out = vrw4._combine_halves([confirmed, dict(confirmed, hypothesis="x__h2")], "x")
    assert out["verdict"] == "CONFIRMED_LOCAL"

    null_ = dict(confirmed, hypothesis="x__h2", verdict="NULL_LOCAL", p=0.5)
    out2 = vrw4._combine_halves([confirmed, null_], "x")
    assert out2["verdict"] == "PROVISIONAL"

    out3 = vrw4._combine_halves([null_, dict(null_, hypothesis="x__h2")], "x")
    assert out3["verdict"] == "NULL_LOCAL"


def test_run_writes_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vrw4, "LEDGER_PATH", ledger)
    rows = []
    for i in range(30):
        date = pd.Timestamp("2026-01-01") + pd.Timedelta(days=i)
        rows.append({"game_id": "g%d" % i, "team": "BOS", "season": "2025-26", "date": date, "pf": 20.0 + (i % 3)})
        rows.append({"game_id": "g%d" % i, "team": "PHI", "season": "2025-26", "date": date, "pf": 18.0})
    box = pd.DataFrame(rows)
    monkeypatch.setattr(vrw4, "load_player_boxscores", lambda: box)

    out = vrw4.run()
    assert len(out) == 3  # h1, h2, combined
    assert all(r["edge_claimed"] is False and r["sport"] == "basketball_nba" for r in out)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == len(out)
    for l in on_disk:
        json.loads(l)  # every line is valid standalone JSON
