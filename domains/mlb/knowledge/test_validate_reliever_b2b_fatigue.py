"""Per-file test for knowledge.validate_reliever_b2b_fatigue. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/knowledge/test_validate_reliever_b2b_fatigue.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.knowledge import validate_reliever_b2b_fatigue as vrb


def _synthetic_pitch_df(n_games=40) -> pd.DataFrame:
    """One PA per game for a single pitcher, xwOBA allowed alternating so the
    comparison has real variance either side of the flag."""
    rows = []
    for g in range(n_games):
        rows.append({"game_pk": g, "pitcher": 1, "at_bat_number": 1, "pitch_number": 1,
                     "events": "field_out", "estimated_woba_using_speedangle": 0.25 + (g % 5) * 0.02})
    return pd.DataFrame(rows)


def _synthetic_chains(n_games=40) -> pd.DataFrame:
    rows = []
    for g in range(n_games):
        rows.append({"game_pk": g, "player_id": 1, "year": 2025,
                     "is_b2b": 1.0 if g % 2 else 0.0,
                     "appearances_last_3d": 2.0 if g % 2 else 0.0})
    return pd.DataFrame(rows)


def test_appearance_outcome_averages_xwoba_per_game_pitcher():
    outcome = vrb.appearance_outcome(_synthetic_pitch_df(n_games=3))
    assert (0, 1) in outcome.index
    assert outcome.loc[(0, 1)] == 0.25


def test_compare_returns_not_testable_when_group_too_small():
    chains = _synthetic_chains(n_games=6)
    outcome = vrb.appearance_outcome(_synthetic_pitch_df(n_games=6))
    r = vrb._compare(chains, outcome, "is_b2b", 1, 2025, "reliever_b2b_fatigue")
    assert r["verdict"] == "NOT_TESTABLE" and r["p"] is None


def test_compare_happy_path_returns_well_shaped_row():
    chains = _synthetic_chains(n_games=60)
    outcome = vrb.appearance_outcome(_synthetic_pitch_df(n_games=60))
    r = vrb._compare(chains, outcome, "is_b2b", 1, 2025, "reliever_b2b_fatigue")
    assert set(r) >= {"hypothesis", "n", "effect", "p", "verdict", "note"}
    assert r["n"] > 0


def test_combine_never_counts_a_reverse_direction_significant_row_as_support():
    """Failure mode this guards: a significant NEGATIVE effect (fatigued group
    allows LESS xwOBA -- the opposite of the fatigue hypothesis, plausibly a
    selection confound) must never be mislabeled as PROVISIONAL/CONFIRMED
    support for the fatigue-degrades-performance claim."""
    rows = [
        {"verdict": "NULL_LOCAL", "p": 0.5, "effect": 0.01, "n": 100},
        {"verdict": "CONFIRMED_LOCAL", "p": 0.001, "effect": -0.05, "n": 100},
        {"verdict": "NULL_LOCAL", "p": 0.3, "effect": 0.02, "n": 100},
    ]
    r = vrb._combine(rows, "reliever_b2b_fatigue")
    assert r["verdict"] == "NULL_LOCAL"
    assert "REVERSE" in r["note"]


def test_combine_confirms_only_with_two_same_direction_positive_significant_seasons():
    rows = [
        {"verdict": "CONFIRMED_LOCAL", "p": 0.001, "effect": 0.05, "n": 100},
        {"verdict": "CONFIRMED_LOCAL", "p": 0.002, "effect": 0.04, "n": 100},
        {"verdict": "NULL_LOCAL", "p": 0.5, "effect": 0.01, "n": 100},
    ]
    r = vrb._combine(rows, "reliever_b2b_fatigue")
    assert r["verdict"] == "CONFIRMED_LOCAL"


def test_run_appends_four_rows_edge_claim_free(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vrb, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vrb, "SEASONS", [2025])
    monkeypatch.setattr(vrb, "load_chains", lambda: _synthetic_chains(n_games=60))
    monkeypatch.setattr(vrb, "load_season", lambda season=2025: _synthetic_pitch_df(n_games=60))
    rows = vrb.run()
    assert len(rows) == 4  # 2 hypotheses x (1 season row + 1 combined row)
    assert all(r["edge_claimed"] is False and r["sport"] == "mlb" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 4
