"""Per-file test for facts_store: dedupe-append idempotence + summary. No network."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.edge_engine import facts_store  # noqa: E402


def _key(r):
    return (r["player_name"], r["status"])


def test_append_new_is_deduped_and_idempotent(tmp_path):
    p = tmp_path / "store.jsonl"
    rows = [
        {"player_name": "A", "status": "OUT", "fetched_at": "2026-07-08T10:00:00+00:00"},
        {"player_name": "A", "status": "OUT", "fetched_at": "2026-07-08T10:00:00+00:00"},  # dup
        {"player_name": "B", "status": "GTD", "fetched_at": "2026-07-08T11:00:00+00:00"},
    ]
    added = facts_store.append_new(p, rows, _key)
    assert added == 2, "duplicate within the batch must not be written twice"
    assert len(facts_store.read_rows(p)) == 2
    # Re-run with the SAME rows adds nothing (idempotent).
    assert facts_store.append_new(p, rows, _key) == 0
    assert len(facts_store.read_rows(p)) == 2
    # A genuinely new row appends.
    assert facts_store.append_new(p, [{"player_name": "C", "status": "OUT",
                                       "fetched_at": "2026-07-08T12:00:00+00:00"}], _key) == 1
    assert len(facts_store.read_rows(p)) == 3


def test_store_summary_picks_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(facts_store, "FACTS_DIR", tmp_path)
    p = facts_store.path_for("injury", "nba")
    facts_store.append_new(
        p,
        [{"player_name": "A", "status": "OUT", "fetched_at": "2026-07-08T09:00:00+00:00"},
         {"player_name": "B", "status": "OUT", "fetched_at": "2026-07-08T12:00:00+00:00"}],
        _key,
    )
    s = facts_store.store_summary("injury", "nba")
    assert s == {"kind": "injury", "sport": "nba", "rows": 2,
                 "latest": "2026-07-08T12:00:00+00:00"}


def test_read_rows_missing_file_is_empty(tmp_path):
    assert facts_store.read_rows(tmp_path / "nope.jsonl") == []
