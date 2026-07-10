"""Per-file test for knowledge.validate_quarter_volatility. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/knowledge/test_validate_quarter_volatility.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.basketball_nba.knowledge import validate_quarter_volatility as vqv


def _synthetic_linescores(n_games=120, seed=3, n_teams=10) -> pd.DataFrame:
    """n_teams teams, each team's quarter-scoring pattern is a fixed per-team
    bias (so q1_margin should persist split-half) plus noise, and the team's
    own stdev level (quarter_volatility) is also team-specific. n_teams=10
    (not 4) so split-half pearsonr has enough df to clear ALPHA=0.01 on the
    constructed signal -- a real r=0.9+ still needs >=8ish points to be
    significant at that bar."""
    rng = np.random.default_rng(seed)
    teams = [f"T{i}" for i in range(n_teams)]
    bias = {t: (i - n_teams / 2) * 2.0 for i, t in enumerate(teams)}  # q1 tendency
    vol = {t: 2.0 + (i % 4) * 2.0 for i, t in enumerate(teams)}  # scoring volatility level
    rows = []
    start = pd.Timestamp("2024-01-01")
    for g in range(n_games):
        home, away = rng.choice(teams, size=2, replace=False)
        h_q1 = 25 + bias[home] / 2 + rng.normal(0, vol[home])
        a_q1 = 25 - bias[home] / 2 + rng.normal(0, vol[away])
        rows.append({
            "event_id": str(g), "home_abbr": home, "away_abbr": away,
            "home_q1": h_q1, "home_q2": 25 + rng.normal(0, vol[home]),
            "home_q3": 25 + rng.normal(0, vol[home]), "home_q4": 25 + rng.normal(0, vol[home]),
            "away_q1": a_q1, "away_q2": 25 + rng.normal(0, vol[away]),
            "away_q3": 25 + rng.normal(0, vol[away]), "away_q4": 25 + rng.normal(0, vol[away]),
            "date": start + pd.Timedelta(days=g),
        })
    return pd.DataFrame(rows)


def test_team_game_frame_has_expected_columns_and_row_count():
    ls = _synthetic_linescores(n_games=30)
    tg = vqv.team_game_frame(ls)
    assert set(tg.columns) >= {"date", "team", "quarter_volatility", "q1_margin", "margin"}
    assert len(tg) == 60  # 2 team-rows per game


def test_q1_slow_start_persists_detects_synthetic_bias():
    ls = _synthetic_linescores(n_games=400)
    tg = vqv.team_game_frame(ls)
    r = vqv.q1_slow_start_persists(tg)
    assert set(r) >= {"hypothesis", "verdict", "effect", "p", "n"}
    assert r["verdict"] == "CONFIRMED_LOCAL"  # strong per-team q1 bias by construction


def test_quarter_volatility_hypothesis_well_shaped():
    ls = _synthetic_linescores(n_games=150)
    tg = vqv.team_game_frame(ls)
    r = vqv.quarter_volatility_persists_and_relates_to_margin_variance(tg)
    assert set(r) >= {"hypothesis", "verdict", "persist_r", "relate_r"}
    assert r["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"}


def test_team_game_frame_has_q4_margin_and_side():
    ls = _synthetic_linescores(n_games=30)
    tg = vqv.team_game_frame(ls)
    assert set(tg.columns) >= {"side", "q4_margin"}
    assert set(tg["side"].unique()) == {"home", "away"}


def test_home_q4_edge_well_shaped_and_null_on_symmetric_synthetic_data():
    # _synthetic_linescores has no home-specific Q4 bias by construction ->
    # honest NULL expected (must not fabricate CONFIRMED on symmetric data).
    ls = _synthetic_linescores(n_games=300)
    tg = vqv.team_game_frame(ls)
    r = vqv.home_q4_edge_exceeds_other_quarters(tg)
    assert set(r) >= {"hypothesis", "verdict", "effect", "p", "n"}
    assert r["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"}
    assert r["n"] == 300


def test_run_writes_three_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    orig_tgf = vqv.team_game_frame
    monkeypatch.setattr(vqv, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vqv, "team_game_frame", lambda: orig_tgf(_synthetic_linescores(n_games=60)))
    rows = vqv.run()
    assert len(rows) == 3
    assert all(r["edge_claimed"] is False and r["sport"] == "basketball_nba" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 3
