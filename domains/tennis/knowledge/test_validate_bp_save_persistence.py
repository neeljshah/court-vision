"""Per-file test for knowledge.validate_bp_save_persistence. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/tennis/knowledge/test_validate_bp_save_persistence.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.tennis.knowledge import validate_bp_save_persistence as vbp

_REQUIRED_KEYS = {"hypothesis", "n", "effect", "p"}


def _synthetic_matches_and_stats(n_players=20, n_matches=300, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-01", periods=3650, freq="D")
    m_rows, s_rows = [], []
    for i in range(n_matches):
        p1, p2 = rng.choice(n_players, size=2, replace=False)
        eid = "e%d" % i
        winner = int(rng.choice([1, 2]))
        m_rows.append({"event_id": eid, "date": rng.choice(dates), "p1_id": int(p1), "p2_id": int(p2),
                        "winner": winner})
        svpt1, svpt2 = 50, 50
        won1, won2 = int(rng.integers(20, 35)), int(rng.integers(20, 35))
        s_rows.append({
            "event_id": eid, "p1_bpFaced": int(rng.integers(3, 10)), "p2_bpFaced": int(rng.integers(3, 10)),
            "p1_bp_saved_pct": float(rng.uniform(0.3, 0.9)), "p2_bp_saved_pct": float(rng.uniform(0.3, 0.9)),
            "p1_svpt": svpt1, "p2_svpt": svpt2,
            "p1_1stWon": won1, "p1_2ndWon": int(rng.integers(5, 15)),
            "p2_1stWon": won2, "p2_2ndWon": int(rng.integers(5, 15)),
        })
    return pd.DataFrame(m_rows), pd.DataFrame(s_rows)


def test_hypothesis_functions_happy_path_shape_without_verdict_key_when_testable():
    matches, stats_df = _synthetic_matches_and_stats()
    r1 = vbp.bp_save_skill_persistence_partial(matches, stats_df)
    assert _REQUIRED_KEYS <= set(r1)
    r2 = vbp.bp_save_differential_predicts_outcome_partial(matches, stats_df)
    assert _REQUIRED_KEYS <= set(r2) and "verdict" not in r2


def test_verdict_nan_p_is_not_testable():
    assert vbp._verdict(float("nan"), 0.5, 0.1) == "NOT_TESTABLE"
    assert vbp._verdict(0.001, 0.5, 0.1) == "CONFIRMED_LOCAL"
    assert vbp._verdict(0.5, 0.5, 0.1) == "NULL_LOCAL"


def test_sparse_data_is_not_testable_not_a_crash():
    """Failure mode: too few players/matches should return an honest
    NOT_TESTABLE verdict, not raise inside statsmodels."""
    matches, stats_df = _synthetic_matches_and_stats(n_players=4, n_matches=3)
    r = vbp.bp_save_skill_persistence_partial(matches, stats_df)
    assert r["verdict"] == "NOT_TESTABLE"
    r2 = vbp.bp_save_differential_predicts_outcome_partial(matches, stats_df)
    assert r2["verdict"] == "NOT_TESTABLE"


def test_run_stamps_verdict_and_writes_two_edge_free_rows(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    matches, stats_df = _synthetic_matches_and_stats()
    monkeypatch.setattr(vbp, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vbp, "load_matches", lambda: matches)
    monkeypatch.setattr(vbp, "load_match_stats", lambda: stats_df)
    rows = vbp.run()
    assert len(rows) == 2
    assert all("verdict" in r and r["verdict"] in
               {"CONFIRMED_LOCAL", "NULL_LOCAL", "NOT_TESTABLE"} for r in rows)
    assert all(r["edge_claimed"] is False and r["sport"] == "tennis" for r in rows)
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 2
