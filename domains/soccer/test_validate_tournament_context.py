"""Per-file test for knowledge.validate_tournament_context -- synthetic
frame, hand-computed effects, verdict-threshold edge cases, run() wiring.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/test_validate_tournament_context.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.soccer.knowledge import validate_tournament_context as vtc


def _synthetic_df() -> pd.DataFrame:
    rows = []
    # true-home (neutral=False): strong home edge, 8 home wins / 2 away wins
    for i in range(10):
        hs, aws = (2, 0) if i < 8 else (0, 2)
        rows.append({"date": pd.Timestamp("2010-01-01"), "home_score": hs, "away_score": aws,
                     "tournament": "FIFA World Cup", "neutral": False})
    # neutral venue: no home edge, 5-5 split
    for i in range(10):
        hs, aws = (1, 0) if i < 5 else (0, 1)
        rows.append({"date": pd.Timestamp("2010-01-01"), "home_score": hs, "away_score": aws,
                     "tournament": "FIFA World Cup", "neutral": True})
    # friendly, low scoring
    for _ in range(5):
        rows.append({"date": pd.Timestamp("2010-01-01"), "home_score": 0, "away_score": 0,
                     "tournament": "Friendly", "neutral": False})
    # one unplayed fixture -- must be dropped by load_results
    rows.append({"date": pd.Timestamp("2026-06-20"), "home_score": None, "away_score": None,
                 "tournament": "FIFA World Cup", "neutral": True})
    return pd.DataFrame(rows)


def test_load_results_drops_unplayed_fixtures(tmp_path, monkeypatch):
    df = _synthetic_df()
    path = tmp_path / "results.parquet"
    df.to_parquet(path, index=False)
    monkeypatch.setattr(vtc, "RESULTS_PATH", path)
    loaded = vtc.load_results()
    assert len(loaded) == 25  # 26 rows minus the 1 unplayed (NaN scores)
    assert loaded["home_score"].isna().sum() == 0


def test_home_advantage_neutral_vs_true_hand_computed():
    df = _build_played_df()
    rows = vtc.home_advantage_neutral_vs_true(df)
    gd_row = next(r for r in rows if r["hypothesis"] == "home_advantage_neutral_vs_true_goal_diff")
    wr_row = next(r for r in rows if r["hypothesis"] == "home_advantage_neutral_vs_true_win_rate")
    # true-home group = 10 WC home-venue rows (neutral=False) + 5 friendly rows (also
    # neutral=False, all 0-0): goal_diff mean = (8*2 + 2*-2 + 5*0)/15 = 0.8; win-rate = 8/15=0.5333.
    # neutral group = 10 WC rows: goal_diff mean = 0.0; win-rate = 5/10 = 0.5.
    assert gd_row["effect"] == 0.8
    assert round(wr_row["effect"], 4) == 0.0333


def _build_played_df() -> pd.DataFrame:
    df = _synthetic_df().dropna(subset=["home_score", "away_score"]).copy()
    df["goal_diff"] = df["home_score"] - df["away_score"]
    df["home_win"] = (df["home_score"] > df["away_score"]).astype(int)
    df["total_goals"] = df["home_score"] + df["away_score"]
    df["competitive"] = df["tournament"] != "Friendly"
    return df


def test_tournament_vs_friendly_hand_computed():
    df = _build_played_df()
    row = vtc.tournament_vs_friendly_scoring_environment(df)
    # competitive total_goals mean = (8*2+2*2 + 5*1+5*1)/20 = (20+10)/20 = 1.5; friendly mean = 0.0
    assert row["effect"] == 1.5
    assert row["hypothesis"] == "tournament_vs_friendly_scoring_environment"


def test_verdict_nan_p_is_not_testable_never_misclassified():
    """Failure mode: a NaN p-value (degenerate/empty comparison) must verdict
    NOT_TESTABLE, never get compared against ALPHA and silently pass/fail."""
    assert vtc._verdict(float("nan"), 0.5, 0.1) == "NOT_TESTABLE"
    assert vtc._verdict(0.001, 0.5, 0.1) == "CONFIRMED_LOCAL"
    assert vtc._verdict(0.5, 0.5, 0.1) == "NULL_LOCAL"


def test_run_writes_four_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vtc, "LEDGER_PATH", ledger)
    path = tmp_path / "results.parquet"
    _synthetic_df().to_parquet(path, index=False)
    monkeypatch.setattr(vtc, "RESULTS_PATH", path)
    rows = vtc.run()
    assert len(rows) == 4
    assert all(r["edge_claimed"] is False and r["sport"] == "soccer" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 4
