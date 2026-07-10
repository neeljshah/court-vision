"""Per-file test for ingame_score_drift_audit.py (D5 seed).

Hermetic synthetic ledger + snapshot fixtures; no network; never touches the
real data/frontend/clv_ledger.jsonl or data/frontend/ops/ artifacts.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/paper/test_ingame_score_drift_audit.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.paper.ingame_score_drift_audit import (
    build_snapshot_rows,
    classify_mismatches,
    load_snapshot_history,
    run_audit,
)

_ROW = {
    "channel": "paper_ingame", "status": "settled", "sport": "mlb",
    "game_id": "KXMLBGAME-TEST01", "settle_key": "s1", "home_score": 5, "away_score": 2,
    "outcome": "win", "settled_at": "2026-07-01T00:00:00Z",
}


def test_build_snapshot_rows_reads_fresh_resolver_score():
    out = build_snapshot_rows([_ROW], score_fn=lambda gid: (5, 2), captured_at="t1")
    assert out == [{
        "id": "s1", "sport": "mlb", "game_id": "KXMLBGAME-TEST01", "ledger_home": 5, "ledger_away": 2,
        "ledger_outcome": "win", "settled_at": "2026-07-01T00:00:00Z",
        "parquet_home": 5, "parquet_away": 2, "captured_at": "t1",
    }]


def test_build_snapshot_rows_skips_open_and_other_channels():
    rows = [dict(_ROW, status="open"), dict(_ROW, channel="paper")]
    assert build_snapshot_rows(rows, score_fn=lambda gid: (5, 2)) == []


def test_classify_no_flag_when_current_read_matches_ledger():
    out = classify_mismatches([_ROW], score_fn=lambda gid: (5, 2), history={})
    assert out == []


def test_classify_baseline_unclassified_with_no_history():
    out = classify_mismatches([_ROW], score_fn=lambda gid: (9, 9), history={})
    assert len(out) == 1
    assert out[0]["kind"] == "baseline_unclassified"
    assert out[0]["first_seen"] == "this_run"


def test_classify_parquet_rebuilt_after_settle_when_first_snapshot_agreed():
    # First-ever observed snapshot matched the ledger (5,2); a LATER snapshot
    # and the current read both show (9,9) -- the parquet moved, not the row.
    history = {"s1": [
        {"parquet_home": 5, "parquet_away": 2, "captured_at": "t1"},
        {"parquet_home": 9, "parquet_away": 9, "captured_at": "t2"},
    ]}
    out = classify_mismatches([_ROW], score_fn=lambda gid: (9, 9), history=history)
    assert out[0]["kind"] == "parquet_rebuilt_after_settle"
    assert out[0]["first_seen"] == "t2"


def test_classify_wrong_at_settle_time_when_never_agreed():
    # Never once agreed with the ledger score across 2+ observations.
    history = {"s1": [
        {"parquet_home": 9, "parquet_away": 9, "captured_at": "t1"},
        {"parquet_home": 9, "parquet_away": 9, "captured_at": "t2"},
    ]}
    out = classify_mismatches([_ROW], score_fn=lambda gid: (9, 9), history=history)
    assert out[0]["kind"] == "wrong_at_settle_time"
    assert out[0]["first_seen"] == "t1"


def test_load_snapshot_history_sorts_oldest_first_and_skips_corrupt_lines(tmp_path):
    p = tmp_path / "snap.jsonl"
    p.write_text(
        json.dumps({"id": "s1", "captured_at": "t2"}) + "\n"
        + "not json\n"
        + json.dumps({"id": "s1", "captured_at": "t1"}) + "\n",
        encoding="ascii",
    )
    hist = load_snapshot_history(p)
    assert [d["captured_at"] for d in hist["s1"]] == ["t1", "t2"]


def test_run_audit_end_to_end_appends_forward_only_and_writes_flags(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger_path.write_text(json.dumps(_ROW) + "\n", encoding="utf-8")
    snap_path = tmp_path / "snap.jsonl"
    flags_path = tmp_path / "flags.json"

    report1 = run_audit(ledger_path=ledger_path, snapshot_path=snap_path,
                        flags_path=flags_path, score_fn=lambda gid: (9, 9))
    assert report1["n_settled_scanned"] == 1
    assert report1["n_flags"] == 1
    assert report1["flags"][0]["kind"] == "baseline_unclassified"
    lines1 = snap_path.read_text(encoding="ascii").splitlines()
    assert len(lines1) == 1

    # Second run: history now has one prior point that never matched -> still
    # baseline_unclassified (need >=2 prior points to prove "never agreed").
    report2 = run_audit(ledger_path=ledger_path, snapshot_path=snap_path,
                        flags_path=flags_path, score_fn=lambda gid: (9, 9))
    lines2 = snap_path.read_text(encoding="ascii").splitlines()
    assert len(lines2) == 2  # append-only, never rewrites the first line
    assert lines2[0] == lines1[0]
    assert report2["flags"][0]["kind"] == "baseline_unclassified"

    # Third run: now 2 prior points, both disagreeing -> wrong_at_settle_time.
    report3 = run_audit(ledger_path=ledger_path, snapshot_path=snap_path,
                        flags_path=flags_path, score_fn=lambda gid: (9, 9))
    assert report3["flags"][0]["kind"] == "wrong_at_settle_time"
    assert json.loads(flags_path.read_text(encoding="ascii"))["n_flags"] == 1


def test_run_audit_never_touches_the_ledger_file(tmp_path):
    ledger_path = tmp_path / "ledger.jsonl"
    original = json.dumps(_ROW) + "\n"
    ledger_path.write_text(original, encoding="utf-8")
    run_audit(ledger_path=ledger_path, snapshot_path=tmp_path / "snap.jsonl",
             flags_path=tmp_path / "flags.json", score_fn=lambda gid: (5, 2))
    assert ledger_path.read_text(encoding="utf-8") == original
