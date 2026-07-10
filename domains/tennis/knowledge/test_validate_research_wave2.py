"""Per-file test for knowledge.validate_research_wave2. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/tennis/knowledge/test_validate_research_wave2.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.tennis.knowledge import validate_research_wave2 as vrw

_REQUIRED_KEYS = {"hypothesis", "n", "effect", "p"}


def _synthetic_slam_points(n_matches=60, tb_per_match=1, seed=7):
    """Point-level rows with a resolvable tiebreak per match: TB game_no
    ends 6-6 on all but the last point, which flips to 7-6 or 6-7 (mirrors
    the ~46%-of-cases same-row-increment path this session found)."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_matches):
        mid = "m%d" % i
        pn = 0
        # a normal non-TB game first, so the group-by has >1 game_no
        for k in range(4):
            pn += 1
            rows.append({"match_id": mid, "set_no": 1, "game_no": 1, "point_number": pn,
                         "point_server": 1, "p1_games_won": 0, "p2_games_won": 0})
        first_server = int(rng.choice([1, 2]))
        winner = int(rng.choice([1, 2]))
        tb_points = 7
        for k in range(tb_points):
            pn += 1
            server = first_server if k % 2 == 0 else (3 - first_server)
            p1g, p2g = 6, 6
            if k == tb_points - 1:
                p1g, p2g = (7, 6) if winner == 1 else (6, 7)
            rows.append({"match_id": mid, "set_no": 1, "game_no": 2, "point_number": pn,
                         "point_server": server, "p1_games_won": p1g, "p2_games_won": p2g})
    return pd.DataFrame(rows)


def _synthetic_matches_stats(n_players=20, n_matches=300, seed=5):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2018-01-01", periods=200, freq="7D")  # one date per "tourney start"
    m_rows, s_rows = [], []
    for i in range(n_matches):
        p1, p2 = rng.choice(n_players, size=2, replace=False)
        eid = "e%d" % i
        m_rows.append({"event_id": eid, "date": rng.choice(dates), "tourney_id": "t%d" % (i % 30),
                        "p1_id": int(p1), "p2_id": int(p2)})
        s_rows.append({"event_id": eid,
                        "p1_ace_rate": float(rng.uniform(0.02, 0.15)), "p2_ace_rate": float(rng.uniform(0.02, 0.15)),
                        "p1_1st_in_pct": float(rng.uniform(0.5, 0.75)), "p2_1st_in_pct": float(rng.uniform(0.5, 0.75))})
    return pd.DataFrame(m_rows), pd.DataFrame(s_rows)


def test_tiebreak_derivation_resolves_synthetic_winner_and_first_server():
    sp = _synthetic_slam_points(n_matches=80)
    r = vrw.tiebreak_serve_order_win_rate(sp)
    assert _REQUIRED_KEYS <= set(r) and "verdict" in r
    assert r["n"] == 80  # every synthetic TB is resolvable (last point flips)
    assert r["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL"}


def test_tb_winner_two_derivation_paths():
    same_row = pd.DataFrame({"p1_games_won": [6, 6, 7], "p2_games_won": [6, 6, 6]})
    assert vrw._tb_winner(same_row, None) == 1
    next_row = pd.DataFrame({"p1_games_won": [6, 6, 6], "p2_games_won": [6, 6, 6]})
    nxt = pd.Series({"p1_games_won": 6, "p2_games_won": 7})
    assert vrw._tb_winner(next_row, nxt) == 2
    assert vrw._tb_winner(next_row, None) is None


def test_hypothesis_functions_happy_path_shape():
    matches, stats_df = _synthetic_matches_stats()
    r2 = vrw.within_tournament_rest_gap_ace_rate(matches, stats_df)
    assert _REQUIRED_KEYS <= set(r2) and "verdict" in r2
    r3 = vrw.within_tournament_rest_gap_first_serve(matches, stats_df)
    assert _REQUIRED_KEYS <= set(r3) and "verdict" in r3


def test_tourney_constant_date_is_not_testable_with_root_cause_note():
    """Real matches.parquet's date is tourney-constant (verified this
    session) -- reproduce that shape and confirm the premise-failure note,
    not a generic underpowered one, is what gets reported."""
    matches, stats_df = _synthetic_matches_stats()
    matches = matches.copy()
    matches["date"] = pd.Timestamp("2020-01-01")  # collapse to one date, like the real corpus
    r = vrw.within_tournament_rest_gap_ace_rate(matches, stats_df)
    assert r["verdict"] == "NOT_TESTABLE"
    assert "premise failure" in r["note"]


def test_verdict_thresholds():
    assert vrw._verdict(float("nan"), 0.5, 0.1) == "NOT_TESTABLE"
    assert vrw._verdict(0.001, 0.5, 0.1) == "CONFIRMED_LOCAL"
    assert vrw._verdict(0.5, 0.5, 0.1) == "NULL_LOCAL"


def test_sparse_data_is_not_testable_not_a_crash():
    sp = _synthetic_slam_points(n_matches=5)  # below MIN_TB=30
    r = vrw.tiebreak_serve_order_win_rate(sp)
    assert r["verdict"] == "NOT_TESTABLE"
    matches, stats_df = _synthetic_matches_stats(n_matches=2)
    r2 = vrw.within_tournament_rest_gap_ace_rate(matches, stats_df)
    assert r2["verdict"] == "NOT_TESTABLE"


def test_run_stamps_verdict_and_writes_three_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    sp = _synthetic_slam_points(n_matches=40)
    matches, stats_df = _synthetic_matches_stats()
    monkeypatch.setattr(vrw, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vrw, "load_slam_points", lambda: sp)
    monkeypatch.setattr(vrw, "load_matches", lambda: matches)
    monkeypatch.setattr(vrw, "load_match_stats", lambda: stats_df)
    rows = vrw.run()
    assert len(rows) == 3
    assert all("verdict" in r and r["verdict"] in
               {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"} for r in rows)
    assert all(r["edge_claimed"] is False and r["sport"] == "tennis" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 3


def test_self_check_runs():
    vrw._self_check()
