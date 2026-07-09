"""Per-file test. Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/data_frontier/test_utilization_audit.py -q
"""
from __future__ import annotations

import json

from scripts.platformkit.data_frontier import utilization_audit as ua


def test_categorize_hits_buckets_pregame_and_live():
    hits = [
        "domains/tennis/asof_hold.py:10:df['x']",
        "domains/tennis/ingame_shadow.py:5:df['x']",
        "scripts/platformkit/answers/resolver_registry.py:3:x",
    ]
    cats = ua.categorize_hits(hits)
    assert "pregame" in cats
    assert "live_ingame" in cats
    assert "answers" in cats


def test_categorize_hits_empty_for_no_hits():
    assert ua.categorize_hits([]) == []


def test_all_sports_have_corpora_and_roots():
    assert set(ua.SPORT_CORPORA) == set(ua.SPORT_ROOTS)
    for sport, corpora in ua.SPORT_CORPORA.items():
        assert corpora, f"{sport} has no corpora"


def test_build_inventory_shape_small_corpus(monkeypatch):
    # Restrict NBA to one tiny, always-present corpus so the test stays fast.
    monkeypatch.setitem(
        ua.SPORT_CORPORA, "nba", [("data/domains/basketball_nba/asof_team_adv.parquet", "parquet")]
    )
    rows = ua.build_inventory("nba")
    assert rows, "expected at least one column row"
    row = rows[0]
    assert set(row) == {
        "column", "dtype", "corpora", "coverage_pct_sample", "used_in", "status", "consumer_categories",
    }
    assert row["status"] in ("USED", "UNUSED")
    json.dumps(rows)  # must be JSON-serializable
