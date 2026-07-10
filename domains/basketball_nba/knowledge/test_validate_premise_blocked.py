"""Per-file test for domains.basketball_nba.knowledge.validate_premise_blocked.

Thin coverage: each of the 3 mechanism checks must return the honest
NOT_TESTABLE / premise-blocked verdict shape (verdict + note explaining the
missing ingredient), and run() must append that many rows to the ledger with
the shared corpus/edge_claimed tagging -- no regression is ever run here.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        domains/basketball_nba/knowledge/test_validate_premise_blocked.py -q
"""
from __future__ import annotations

from domains.basketball_nba.knowledge import validate_premise_blocked as VPB


def _assert_blocked_shape(r):
    assert r["verdict"] == "NOT_TESTABLE"
    assert r["n"] == 0 and r["effect"] is None and r["p"] is None
    assert isinstance(r["note"], str) and len(r["note"]) > 0
    assert isinstance(r["hypothesis"], str) and len(r["hypothesis"]) > 0


def test_transition_freq_pace_mismatch_blocked():
    _assert_blocked_shape(VPB.transition_freq_pace_mismatch())


def test_clutch_ft_pressure_dip_blocked():
    _assert_blocked_shape(VPB.clutch_ft_pressure_dip())


def test_travel_timezone_fatigue_blocked():
    _assert_blocked_shape(VPB.travel_timezone_fatigue())


def test_run_appends_blocked_rows_with_tagging(tmp_path, monkeypatch):
    fake_ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(VPB, "LEDGER_PATH", fake_ledger)

    rows = VPB.run()

    assert len(rows) == 3
    for r in rows:
        assert r["verdict"] == "NOT_TESTABLE"
        assert r["edge_claimed"] is False
        assert r["sport"] == "basketball_nba"
        assert r["corpus"] == "premise_check_only"
    assert fake_ledger.exists()
    lines = fake_ledger.read_text(encoding="ascii").strip().splitlines()
    assert len(lines) == 3
