"""Per-file test for knowledge.validate_staff_dayafter_chain. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/knowledge/test_validate_staff_dayafter_chain.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.knowledge import validate_staff_dayafter_chain as vdc


def _synthetic_pitch_df() -> pd.DataFrame:
    """3 games for team HOU (as home each time): 2026-04-01 (30 pitches,
    low), 2026-04-02 back-to-back (loses 2 runs -- low-pitch precedent),
    2026-04-05 (gap of 3 days, must be excluded from b2b pairs)."""
    rows = []

    def _game(game_pk, date, n_pitches, away_final):
        for i in range(n_pitches):
            top = i % 2 == 0  # alternate top/bottom so HOU pitches half the rows
            rows.append({
                "game_pk": game_pk, "game_date": date,
                "inning_topbot": "Top" if top else "Bot",
                "home_team": "HOU", "away_team": "SEA",
                "post_home_score": 3, "post_away_score": away_final,
            })
    _game(1, "2026-04-01", 60, 2)   # HOU pitches ~30 (Top half), allows 2
    _game(2, "2026-04-02", 200, 8)  # HOU pitches ~100 (heavy day), allows 8
    _game(3, "2026-04-05", 60, 1)   # gap of 3 days from game 2, excluded
    return pd.DataFrame(rows)


def test_team_day_table_sums_pitches_and_runs_allowed():
    t = vdc.team_day_table(_synthetic_pitch_df())
    hou = t[t["team"] == "HOU"].set_index("game_date")
    assert hou.loc[pd.Timestamp("2026-04-01"), "pitches"] == 30
    assert hou.loc[pd.Timestamp("2026-04-01"), "runs_allowed"] == 2
    assert hou.loc[pd.Timestamp("2026-04-02"), "pitches"] == 100


def test_build_dayafter_pairs_keeps_only_gap_one_day():
    t = vdc.team_day_table(_synthetic_pitch_df())
    pairs = vdc.build_dayafter_pairs(t)
    hou_dates = pairs[pairs["team"] == "HOU"]["game_date"].tolist()
    assert pd.Timestamp("2026-04-01") in hou_dates  # -> 04-02 is gap=1
    assert pd.Timestamp("2026-04-02") not in hou_dates  # -> 04-05 is gap=3, excluded


def test_compare_not_testable_when_group_too_small():
    pairs = pd.DataFrame({"team": ["A"] * 5, "game_date": pd.date_range("2026-01-01", periods=5),
                           "prior_day_pitches": [90, 91, 92, 93, 94], "next_runs_allowed": [1, 2, 3, 4, 5]})
    r = vdc._compare(pairs, 2025)
    assert r["verdict"] == "NOT_TESTABLE" and r["p"] is None


def test_combine_never_counts_reverse_direction_as_support():
    rows = [
        {"verdict": "NULL_LOCAL", "p": 0.5, "effect": 0.1, "n": 100},
        {"verdict": "CONFIRMED_LOCAL", "p": 0.001, "effect": -0.5, "n": 100},
        {"verdict": "NULL_LOCAL", "p": 0.3, "effect": 0.2, "n": 100},
    ]
    r = vdc._combine(rows)
    assert r["verdict"] == "NULL_LOCAL"
    assert "REVERSE" in r["note"]


def test_combine_confirms_only_with_two_same_direction_positive_significant_seasons():
    rows = [
        {"verdict": "CONFIRMED_LOCAL", "p": 0.001, "effect": 0.5, "n": 100},
        {"verdict": "CONFIRMED_LOCAL", "p": 0.002, "effect": 0.4, "n": 100},
        {"verdict": "NULL_LOCAL", "p": 0.5, "effect": 0.1, "n": 100},
    ]
    assert vdc._combine(rows)["verdict"] == "CONFIRMED_LOCAL"


def test_run_appends_four_rows_edge_claim_free(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vdc, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vdc, "SEASONS", [2025])
    monkeypatch.setattr(vdc, "load_season", lambda season=2025: _synthetic_pitch_df())
    rows = vdc.run()
    assert len(rows) == 2  # 1 season row + 1 combined row
    assert all(r["edge_claimed"] is False and r["sport"] == "mlb" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 2
