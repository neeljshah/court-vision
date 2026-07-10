"""Per-file test for domains.mlb.knowledge.validate_premise_blocked.

Thin coverage: each of the 4 mechanism checks must return the honest
NOT_TESTABLE / premise-blocked verdict shape, and run() must append that many
rows to the ledger with the shared corpus/edge_claimed tagging -- no
regression is ever run here. load_season is monkeypatched to a tiny fixture
frame so the test never touches the real statcast corpus.

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \
        domains/mlb/knowledge/test_validate_premise_blocked.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.knowledge import validate_premise_blocked as VPB

_FIXTURE = pd.DataFrame({"on_1b": [1.0, None], "on_2b": [None, None], "on_3b": [None, None]})


def _assert_blocked_shape(r):
    assert r["verdict"] == "NOT_TESTABLE"
    assert r["n"] == 0 and r["effect"] is None and r["p"] is None
    assert isinstance(r["note"], str) and len(r["note"]) > 0


def test_sequencing_cluster_luck_blocked():
    _assert_blocked_shape(VPB.sequencing_cluster_luck(_FIXTURE))


def test_speed_baserunning_advancement_blocked():
    r = VPB.speed_baserunning_advancement(_FIXTURE)
    _assert_blocked_shape(r)
    assert "on_1b" in r["note"]


def test_lineup_slot_run_value_blocked():
    _assert_blocked_shape(VPB.lineup_slot_run_value(_FIXTURE))


def test_umpire_zone_call_consistency_blocked():
    _assert_blocked_shape(VPB.umpire_zone_call_consistency(_FIXTURE))


def test_run_appends_blocked_rows_with_tagging(tmp_path, monkeypatch):
    fake_ledger = tmp_path / "validation_ledger.jsonl"
    monkeypatch.setattr(VPB, "LEDGER_PATH", fake_ledger)
    monkeypatch.setattr(VPB, "load_season", lambda season: _FIXTURE)

    rows = VPB.run()

    assert len(rows) == 4
    for r in rows:
        assert r["verdict"] == "NOT_TESTABLE"
        assert r["edge_claimed"] is False
        assert r["sport"] == "mlb"
        assert r["corpus"] == "premise_check_only"
    assert fake_ledger.exists()
    lines = fake_ledger.read_text(encoding="ascii").strip().splitlines()
    assert len(lines) == 4
