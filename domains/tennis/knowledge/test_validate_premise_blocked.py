"""Per-file test for domains.tennis.knowledge.validate_premise_blocked.

Thin coverage: each of the 3 mechanism checks must return the honest
NOT_TESTABLE / premise-blocked verdict shape, and run() must append that many
rows to the ledger with the shared corpus/edge_claimed tagging -- no
regression is ever run here. load_slam_points and CHARTING_POINTS are
monkeypatched to tiny fixtures so the test never touches the real (543K-row)
slam_points corpus.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        domains/tennis/knowledge/test_validate_premise_blocked.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.tennis.knowledge import validate_premise_blocked as VPB

_FIXTURE_SLAM = pd.DataFrame({"set_no": [1, 1], "game_no": [1, 2]})


def _assert_blocked_shape(r):
    assert r["verdict"] == "NOT_TESTABLE"
    assert r["n"] == 0 and r["effect"] is None and r["p"] is None
    assert isinstance(r["note"], str) and len(r["note"]) > 0


def test_tiebreak_skill_persistence_blocked():
    _assert_blocked_shape(VPB.tiebreak_skill_persistence(_FIXTURE_SLAM))


def test_rally_length_by_round_blocked():
    _assert_blocked_shape(VPB.rally_length_by_round(_FIXTURE_SLAM))


def test_second_serve_discount_by_surface_blocked(tmp_path, monkeypatch):
    fixture_cp = tmp_path / "charting_points.parquet"
    pd.DataFrame({"is_second_serve": [True, False]}).to_parquet(fixture_cp)
    monkeypatch.setattr(VPB, "CHARTING_POINTS", fixture_cp)

    r = VPB.second_serve_discount_by_surface()
    _assert_blocked_shape(r)
    assert "is_second_serve" in r["note"]


def test_run_appends_blocked_rows_with_tagging(tmp_path, monkeypatch):
    fake_ledger = tmp_path / "validation_ledger.jsonl"
    fixture_cp = tmp_path / "charting_points.parquet"
    pd.DataFrame({"is_second_serve": [True, False]}).to_parquet(fixture_cp)
    monkeypatch.setattr(VPB, "LEDGER_PATH", fake_ledger)
    monkeypatch.setattr(VPB, "load_slam_points", lambda: _FIXTURE_SLAM)
    monkeypatch.setattr(VPB, "CHARTING_POINTS", fixture_cp)

    rows = VPB.run()

    assert len(rows) == 3
    for r in rows:
        assert r["verdict"] == "NOT_TESTABLE"
        assert r["edge_claimed"] is False
        assert r["sport"] == "tennis"
        assert r["corpus"] == "premise_check_only"
    assert fake_ledger.exists()
    lines = fake_ledger.read_text(encoding="ascii").strip().splitlines()
    assert len(lines) == 3
