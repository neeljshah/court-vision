"""Per-file test for knowledge.validate_research_wave1. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/tennis/knowledge/test_validate_research_wave1.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.tennis.knowledge import validate_research_wave1 as vrw

_REQUIRED_KEYS = {"hypothesis", "n", "effect", "p"}


def _synthetic_matches_stats_asof_sched(n_players=24, n_matches=400, seed=3):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-01", periods=3650, freq="D")
    m_rows, s_rows, a_rows, sd_rows = [], [], [], []
    scores = ["6-3 6-4", "7-6(4) 6-3", "6-7(4) 7-6(6) 6-1", "6-2 6-1", "7-6(2) 7-6(9)"]
    for i in range(n_matches):
        p1, p2 = rng.choice(n_players, size=2, replace=False)
        eid = "e%d" % i
        winner = int(rng.choice([1, 2]))
        date = rng.choice(dates)
        m_rows.append({"event_id": eid, "date": date, "p1_id": int(p1), "p2_id": int(p2),
                        "winner": winner, "score": rng.choice(scores),
                        "p1_rank": int(rng.integers(1, 200)), "p2_rank": int(rng.integers(1, 200))})
        s_rows.append({
            "event_id": eid, "p1_svpt": 50, "p2_svpt": 50,
            "p1_1stWon": int(rng.integers(15, 30)), "p1_2ndWon": int(rng.integers(5, 15)),
            "p2_1stWon": int(rng.integers(15, 30)), "p2_2ndWon": int(rng.integers(5, 15)),
            "p1_ace_rate": float(rng.uniform(0.02, 0.15)), "p2_ace_rate": float(rng.uniform(0.02, 0.15)),
            "p1_1st_in_pct": float(rng.uniform(0.5, 0.75)), "p2_1st_in_pct": float(rng.uniform(0.5, 0.75)),
        })
        a_rows.append({"event_id": eid, "avg_games_per_set_asof_diff": float(rng.uniform(-2, 2))})
        for pid in (p1, p2):
            sd_rows.append({"event_id": eid, "player_id": int(pid), "matches_last_14d": float(rng.integers(0, 8))})
    return pd.DataFrame(m_rows), pd.DataFrame(s_rows), pd.DataFrame(a_rows), pd.DataFrame(sd_rows)


def test_hypothesis_functions_happy_path_shape():
    matches, stats_df, asof, sched = _synthetic_matches_stats_asof_sched()
    r1 = vrw.tiebreak_skill_persistence_partial(matches, stats_df)
    assert _REQUIRED_KEYS <= set(r1)
    r2 = vrw.dominance_margin_predicts_outcome_partial(matches, asof)
    assert _REQUIRED_KEYS <= set(r2) and "verdict" in r2
    r3 = vrw.load_14d_ace_rate_tercile(matches, sched, stats_df)
    assert _REQUIRED_KEYS <= set(r3) and "verdict" in r3
    r4 = vrw.load_14d_first_serve_in_tercile(matches, sched, stats_df)
    assert _REQUIRED_KEYS <= set(r4) and "verdict" in r4


def test_tiebreak_parser_matches_hash14_winner_first_convention():
    assert vrw._match_winner_tiebreaks("7-6(4) 6-3") == (1, 1)
    assert vrw._match_winner_tiebreaks("6-7(4) 7-6(6) 6-1") == (1, 2)
    assert vrw._match_winner_tiebreaks("6-3 6-4") == (0, 0)
    assert vrw._match_winner_tiebreaks(None) == (0, 0)


def test_verdict_thresholds():
    assert vrw._verdict(float("nan"), 0.5, 0.1) == "NOT_TESTABLE"
    assert vrw._verdict(0.001, 0.5, 0.1) == "CONFIRMED_LOCAL"
    assert vrw._verdict(0.5, 0.5, 0.1) == "NULL_LOCAL"


def test_sparse_data_is_not_testable_not_a_crash():
    matches, stats_df, asof, sched = _synthetic_matches_stats_asof_sched(n_players=4, n_matches=3)
    r1 = vrw.tiebreak_skill_persistence_partial(matches, stats_df)
    assert r1["verdict"] == "NOT_TESTABLE"
    r2 = vrw.dominance_margin_predicts_outcome_partial(matches, asof)
    assert r2["verdict"] == "NOT_TESTABLE"


def test_run_stamps_verdict_and_writes_four_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    matches, stats_df, asof, sched = _synthetic_matches_stats_asof_sched()
    monkeypatch.setattr(vrw, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vrw, "load_matches", lambda: matches)
    monkeypatch.setattr(vrw, "load_match_stats", lambda: stats_df)
    monkeypatch.setattr(vrw, "load_asof_setdetail", lambda: asof)
    monkeypatch.setattr(vrw, "load_schedule_density", lambda: sched)
    rows = vrw.run()
    assert len(rows) == 4
    assert all("verdict" in r and r["verdict"] in
               {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"} for r in rows)
    assert all(r["edge_claimed"] is False and r["sport"] == "tennis" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 4


def test_self_check_runs():
    vrw._self_check()
