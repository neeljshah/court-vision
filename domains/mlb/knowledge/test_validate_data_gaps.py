"""Per-file test for knowledge.validate_data_gaps. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/knowledge/test_validate_data_gaps.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.knowledge import validate_data_gaps as vdg


def _synthetic_pitch_df(n=40) -> pd.DataFrame:
    rows = []
    for i in range(n):
        is_gb = i < 20
        if is_gb:
            bb_type, events = "ground_ball", ("grounded_into_double_play" if i % 10 else "field_out")
        else:
            bb_type, events = "fly_ball", ("field_out" if i % 10 else "double_play")
        rows.append({"on_1b": "1", "outs_when_up": 0, "bb_type": bb_type, "events": events})
    return pd.DataFrame(rows)


def test_gb_double_play_suppression_happy_path_returns_well_shaped_row():
    r = vdg.gb_double_play_suppression(_synthetic_pitch_df())
    assert set(r) >= {"hypothesis", "n", "effect", "p", "verdict", "note"}
    assert r["verdict"] in {"CONFIRMED_LOCAL", "NULL_LOCAL"}
    assert r["n"] > 0


def test_not_testable_reports_which_columns_are_actually_present():
    r = vdg._not_testable("fake_mechanism", {"temperature", "wind_speed"}, {"balls", "wind_speed"})
    assert r["verdict"] == "NOT_TESTABLE" and r["n"] == 0
    assert "wind_speed" in r["note"]


def test_sb_not_testable_never_fabricates_a_row_when_events_absent():
    df = pd.DataFrame({"events": ["field_out", "single", "double_play"]})
    r = vdg._sb_not_testable(df)
    assert r["verdict"] == "NOT_TESTABLE" and r["n"] == 0


def test_run_appends_all_four_rows_including_honest_not_testable_ones(tmp_path, monkeypatch):
    """Failure mode: an honest NOT_TESTABLE mechanism must still be written to
    the ledger (never silently dropped) -- run() must always emit exactly the
    4 declared rows, edge-claim-free, regardless of corpus richness."""
    ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(vdg, "LEDGER_PATH", ledger)
    monkeypatch.setattr(vdg, "load_season", lambda season=2025: _synthetic_pitch_df())
    rows = vdg.run(season=2025)
    assert len(rows) == 4
    assert all(r["edge_claimed"] is False and r["sport"] == "mlb" for r in rows)
    assert sum(1 for r in rows if r["verdict"] == "NOT_TESTABLE") == 3
    on_disk = [l for l in ledger.read_text(encoding="ascii").splitlines() if l.strip()]
    assert len(on_disk) == 4
