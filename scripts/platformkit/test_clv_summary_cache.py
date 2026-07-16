"""Per-file tests for scripts.platformkit.clv_summary_cache.

Acceptance criteria:
  1. cached_load_ledger returns the same rows as clv_ledger.load_ledger.
  2. A second call against an unchanged ledger returns the cached object
     (identity-equal list) -- no re-parse.
  3. Appending a line changes mtime+size -> cached_load_ledger returns fresh
     rows including the appended one (cache invalidation on append).
  4. cached_clv_summary matches clv_ledger.clv_summary(load_ledger(path)).
  5. Missing ledger path -> empty list / zeroed summary, never raises.

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest \\
      scripts/platformkit/test_clv_summary_cache.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit import clv_ledger as cl
from scripts.platformkit import clv_summary_cache as cache


def _write(path: Path, rows):
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_cached_load_matches_uncached(tmp_path):
    p = tmp_path / "ledger.jsonl"
    _write(p, [{"sport": "nba", "bet_id": "b1", "status": "open"}])
    assert cache.cached_load_ledger(p) == cl.load_ledger(p)


def test_cache_hit_is_same_object_until_mtime_changes(tmp_path):
    p = tmp_path / "ledger.jsonl"
    _write(p, [{"sport": "nba", "bet_id": "b1", "status": "open"}])
    first = cache.cached_load_ledger(p)
    second = cache.cached_load_ledger(p)
    assert second is first  # cache hit -> same list object, no re-parse


def test_append_invalidates_cache(tmp_path):
    p = tmp_path / "ledger.jsonl"
    _write(p, [{"sport": "nba", "bet_id": "b1", "status": "open"}])
    first = cache.cached_load_ledger(p)
    assert len(first) == 1
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"sport": "nba", "bet_id": "b2", "status": "open"}) + "\n")
    second = cache.cached_load_ledger(p)
    assert len(second) == 2
    assert second is not first


def test_cached_summary_matches_uncached(tmp_path):
    p = tmp_path / "ledger.jsonl"
    _write(p, [
        {"sport": "nba", "bet_id": "b1", "status": "settled", "clv_pct": 5.0,
         "side": "home", "taken_decimal": 2.0, "closing_decimal_home": 1.9},
    ])
    expected = cl.clv_summary(cl.load_ledger(p))
    assert cache.cached_clv_summary(p) == expected


def test_missing_ledger_never_raises(tmp_path):
    p = tmp_path / "missing.jsonl"
    assert cache.cached_load_ledger(p) == []
    assert cache.cached_clv_summary(p)["n_bets"] == 0
