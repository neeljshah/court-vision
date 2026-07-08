"""Per-file test for injury_facts: parse a recorded ESPN injuries payload. No network."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.edge_engine import injury_facts  # noqa: E402

# Trimmed recording of the real ESPN NBA injuries payload shape (captured 2026-07-08).
_FIXTURE = {
    "injuries": [
        {"id": "1", "displayName": "Atlanta Hawks", "injuries": [
            {"status": "Day-To-Day", "date": "2026-07-07T22:40Z",
             "shortComment": "Ejiofor (rest) won't play Tuesday.",
             "type": {"abbreviation": "DD"},
             "athlete": {"displayName": "Zuby Ejiofor",
                         "links": [{"href": "https://espn.com/p/1"}]}},
            {"status": "Out", "date": "2026-07-06T18:00Z",
             "longComment": "sidelined with a knee issue.",
             "athlete": {"displayName": "Test Guy", "links": []}},
        ]},
        {"id": "2", "displayName": "Boston Celtics", "injuries": [
            {"status": "15-Day-IL", "date": "2026-06-30T21:30Z",
             "shortComment": "hamstring.",
             "athlete": {"displayName": "IL Player", "links": []}},
            {"status": "Questionable", "date": "2026-07-08T00:00Z",
             "athlete": {}},  # no displayName -> skipped
        ]},
    ]
}


def test_rows_from_payload_normalizes():
    rows = injury_facts.rows_from_payload(_FIXTURE, "nba", fetched_at="2026-07-08T20:00:00+00:00")
    assert len(rows) == 3, "the athlete-less row must be skipped"
    by_name = {r["player_name"]: r for r in rows}
    assert by_name["Zuby Ejiofor"]["status"] == "DAY_TO_DAY"
    assert by_name["Zuby Ejiofor"]["team"] == "Atlanta Hawks"
    assert by_name["Zuby Ejiofor"]["report_date"] == "2026-07-07"
    assert by_name["Zuby Ejiofor"]["source_url"] == "https://espn.com/p/1"
    assert by_name["Test Guy"]["status"] == "OUT"
    assert by_name["Test Guy"]["detail"] == "sidelined with a knee issue."  # longComment fallback
    assert by_name["IL Player"]["status"] == "OUT", "IL variants collapse to OUT"
    assert all(r["source"] == "espn_injuries" and r["sport"] == "nba" for r in rows)


def test_fetch_injuries_uses_injected_getter():
    rows = injury_facts.fetch_injuries("nba", http_get=lambda url: _FIXTURE)
    assert len(rows) == 3


def test_unwired_sport_raises():
    try:
        injury_facts.fetch_injuries("soccer", http_get=lambda url: {})
        assert False, "expected ValueError for unwired sport"
    except ValueError:
        pass


def test_store_injuries_dedupes(tmp_path, monkeypatch):
    from scripts.platformkit.edge_engine import facts_store
    monkeypatch.setattr(facts_store, "FACTS_DIR", tmp_path)
    n1, a1 = injury_facts.store_injuries("nba", http_get=lambda url: _FIXTURE)
    assert (n1, a1) == (3, 3)
    n2, a2 = injury_facts.store_injuries("nba", http_get=lambda url: _FIXTURE)
    assert (n2, a2) == (3, 0), "re-fetching the same feed adds nothing"
