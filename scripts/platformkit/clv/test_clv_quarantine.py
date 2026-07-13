"""Per-file tests for clv_quarantine (the loader both CLV modules import).

Per-file: python -m pytest scripts/platformkit/clv/test_clv_quarantine.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.clv.clv_quarantine import (
    quarantined_bet_ids, split_quarantined)


def test_missing_file_returns_empty_set(tmp_path):
    assert quarantined_bet_ids(str(tmp_path / "nope.json")) == set()


def test_malformed_json_returns_empty_set_no_crash(tmp_path, capsys):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert quarantined_bet_ids(str(p)) == set()
    assert "not applied" in capsys.readouterr().out


def test_malformed_shape_returns_empty_set_no_crash(tmp_path, capsys):
    # valid json but not the expected dict-with-adjudication shape
    p = tmp_path / "shape.json"
    p.write_text(json.dumps(["just", "a", "list"]), encoding="utf-8")
    assert quarantined_bet_ids(str(p)) == set()
    assert "not applied" in capsys.readouterr().out


def test_no_adjudication_block_returns_empty_set_unchanged_behavior(tmp_path):
    p = tmp_path / "noadj.json"
    p.write_text(json.dumps({"flags": [{"bet_id": "x1"}]}), encoding="utf-8")
    assert quarantined_bet_ids(str(p)) == set()


def test_non_exclude_decision_returns_empty_set(tmp_path):
    p = tmp_path / "review.json"
    p.write_text(json.dumps({
        "flags": [{"bet_id": "x1"}],
        "adjudication": {"decision": "UNDER-REVIEW"},
    }), encoding="utf-8")
    assert quarantined_bet_ids(str(p)) == set()


def test_exclude_decision_returns_flagged_bet_ids(tmp_path):
    p = tmp_path / "excl.json"
    p.write_text(json.dumps({
        "flags": [{"bet_id": "x1"}, {"bet_id": "x2"}],
        "adjudication": {"decision": "EXCLUDE-FROM-AGGREGATES"},
    }), encoding="utf-8")
    assert quarantined_bet_ids(str(p)) == {"x1", "x2"}


def test_split_quarantined_excludes_and_counts():
    rows = [{"bet_id": "x1"}, {"bet_id": "x2"}, {"bet_id": "x3"}]
    kept, n = split_quarantined(rows, {"x2"})
    assert n == 1
    assert [r["bet_id"] for r in kept] == ["x1", "x3"]


def test_split_quarantined_empty_set_is_noop():
    rows = [{"bet_id": "x1"}]
    kept, n = split_quarantined(rows, set())
    assert n == 0
    assert kept == rows
