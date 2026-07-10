"""Per-file test for knowledge.validate_research_wave4. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/tennis/knowledge/test_validate_research_wave4.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.tennis.knowledge import validate_research_wave4 as vw4


def _synthetic_joined(rows):
    """rows: list of (tourney_id, round, p1_ace_rate, p2_ace_rate)."""
    df = pd.DataFrame(rows, columns=["tourney_id", "round", "p1_ace_rate", "p2_ace_rate"])
    df["ace_rate"] = (df["p1_ace_rate"] + df["p2_ace_rate"]) / 2.0
    df["bucket"] = None
    df.loc[df["round"].isin(vw4.EARLY_ROUNDS), "bucket"] = "early"
    df.loc[df["round"].isin(vw4.LATE_ROUNDS), "bucket"] = "late"
    return df


def test_verdict_nan_p_is_not_testable_never_misclassified():
    assert vw4._verdict(float("nan"), 0.5, 0.01) == "NOT_TESTABLE"
    assert vw4._verdict(0.001, 0.5, 0.01) == "CONFIRMED_LOCAL"
    assert vw4._verdict(0.5, 0.5, 0.01) == "NULL_LOCAL"
    assert vw4._verdict(0.001, 0.005, 0.01) == "NULL_LOCAL"  # significant but below effect bar


def test_tourney_gaps_excludes_underpowered_and_rr_br_rounds():
    rows = []
    # tourney "t1": 3 early + 3 late -> qualifies
    for i in range(3):
        rows.append(("t1", "R32", 0.05, 0.05))
        rows.append(("t1", "QF", 0.10, 0.10))
    # tourney "t2": only 2 late -> does NOT qualify
    rows.append(("t2", "R64", 0.05, 0.05))
    rows.append(("t2", "R64", 0.05, 0.05))
    rows.append(("t2", "QF", 0.10, 0.10))
    rows.append(("t2", "QF", 0.10, 0.10))
    # RR/BR round excluded entirely from both buckets
    rows.append(("t1", "RR", 0.99, 0.99))
    j = _synthetic_joined(rows)
    gaps = vw4._tourney_gaps(j)
    assert list(gaps.index) == ["t1"]
    assert abs(gaps["t1"] - 0.05) < 1e-9


def test_surface_speed_drift_not_testable_below_floor():
    rows = []
    for i in range(3):
        rows.append(("t1", "R32", 0.05, 0.05))
        rows.append(("t1", "QF", 0.10, 0.10))
    j = _synthetic_joined(rows)
    r = vw4.surface_speed_drift_by_round(j)
    assert r["verdict"] == "NOT_TESTABLE"
    assert r["n"] < vw4.MIN_TOURNEYS


def test_surface_speed_drift_confirmed_when_signal_and_power_present():
    rows = []
    for t in range(80):
        for i in range(3):
            rows.append(("t%d" % t, "R32", 0.05, 0.05))
            rows.append(("t%d" % t, "QF", 0.20, 0.20))  # +0.15 gap every tourney, no noise
    j = _synthetic_joined(rows)
    r = vw4.surface_speed_drift_by_round(j)
    assert r["verdict"] == "CONFIRMED_LOCAL"
    assert r["n"] == 80
    assert abs(r["effect"] - 0.15) < 1e-9


def test_tourney_half_is_deterministic_and_boolean():
    a1 = vw4._tourney_half("2020-ausopen")
    a2 = vw4._tourney_half("2020-ausopen")
    assert a1 == a2 and isinstance(a1, bool)


def test_run_writes_one_edge_free_row(tmp_path, monkeypatch):
    ledger = tmp_path / "validation_ledger.jsonl"
    rows_in = []
    for t in range(60):
        for i in range(3):
            rows_in.append(("t%d" % t, "R32", 0.05, 0.05))
            rows_in.append(("t%d" % t, "QF", 0.06, 0.06))
    j = _synthetic_joined(rows_in)
    monkeypatch.setattr(vw4, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vw4, "_load_joined", lambda: j)
    rows = vw4.run()
    assert len(rows) == 1
    assert rows[0]["hypothesis"] == "surface_speed_drift_by_round"
    assert rows[0]["edge_claimed"] is False and rows[0]["sport"] == "tennis"
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 1


def test_run_split_half_writes_two_rows(tmp_path, monkeypatch):
    rows_in = []
    for t in range(120):
        for i in range(3):
            rows_in.append(("t%d" % t, "R32", 0.05, 0.05))
            rows_in.append(("t%d" % t, "QF", 0.06, 0.06))
    j = _synthetic_joined(rows_in)
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vw4, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vw4, "_load_joined", lambda: j)
    rows = vw4.run_split_half()
    assert len(rows) == 2
    assert {r["hypothesis"] for r in rows} == {
        "surface_speed_drift_by_round__split_A", "surface_speed_drift_by_round__split_B"}
    assert all(r["edge_claimed"] is False for r in rows)


def test_self_check_runs():
    vw4._self_check()
