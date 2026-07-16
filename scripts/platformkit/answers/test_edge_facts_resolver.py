"""Per-file test for edge_facts_resolver: fixture jsonl -> latest status,
absent file -> no_data, entity miss -> no_data, stale -> refused.
Run: python -m pytest scripts/platformkit/answers/test_edge_facts_resolver.py -q
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.platformkit.answers import edge_facts_resolver as R  # noqa: E402


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _write_injury_rows(monkeypatch, tmp_path, rows):
    monkeypatch.setattr(R.FS, "FACTS_DIR", tmp_path)
    path = R.FS.path_for("injury", "nba")
    R.FS.append_new(path, rows, lambda r: (r["player_name"], r["fetched_at"]))
    return path


def _write_news_rows(monkeypatch, tmp_path, rows):
    monkeypatch.setattr(R.FS, "FACTS_DIR", tmp_path)
    path = R.FS.path_for("news", "nba")
    R.FS.append_new(path, rows, lambda r: (r["headline"], r["published"]))
    return path


def test_injury_report_latest_status_newest_first(tmp_path, monkeypatch):
    _write_injury_rows(monkeypatch, tmp_path, [
        {"player_name": "Trae Young", "team": "Atlanta Hawks", "status": "OUT", "detail": "old",
         "report_date": "2026-07-10", "source": "espn", "source_url": "u1", "fetched_at": _iso(2)},
        {"player_name": "Trae Young", "team": "Atlanta Hawks", "status": "DAY_TO_DAY", "detail": "new",
         "report_date": "2026-07-12", "source": "espn", "source_url": "u2", "fetched_at": _iso(0.5)},
    ])
    out = R.injury_report("nba", player="Trae Young")
    assert out["status"] == "ok"
    assert out["category"] == "edge_facts_injury_report"
    assert out["n"] == 2
    assert out["rows"][0]["status"] == "DAY_TO_DAY", "newest fetched_at row must sort first"
    assert out["rows"][1]["status"] == "OUT"
    assert out["matched_entity"] == "Trae Young"


def test_injury_report_fuzzy_entity_match(tmp_path, monkeypatch):
    _write_injury_rows(monkeypatch, tmp_path, [
        {"player_name": "Trae Young", "team": "Atlanta Hawks", "status": "OUT", "detail": "d",
         "report_date": "2026-07-12", "source": "espn", "source_url": "u1", "fetched_at": _iso(0.1)},
    ])
    out = R.injury_report("nba", player="Trae Yung")  # typo -- no exact match
    assert out["status"] == "ok"
    assert out["matched_entity"] == "Trae Young"


def test_injury_report_absent_file_is_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(R.FS, "FACTS_DIR", tmp_path)
    out = R.injury_report("nba", player="Trae Young")
    assert out["status"] == "no_data"
    assert out["category"] == "edge_facts_injury_report"


def test_injury_report_entity_miss_is_no_data(tmp_path, monkeypatch):
    _write_injury_rows(monkeypatch, tmp_path, [
        {"player_name": "Trae Young", "team": "Atlanta Hawks", "status": "OUT", "detail": "d",
         "report_date": "2026-07-12", "source": "espn", "source_url": "u1", "fetched_at": _iso(0.1)},
    ])
    out = R.injury_report("nba", player="Zzzqqx Nonexistent Player")
    assert out["status"] == "no_data"


def test_injury_report_stale_is_refused(tmp_path, monkeypatch):
    _write_injury_rows(monkeypatch, tmp_path, [
        {"player_name": "Trae Young", "team": "Atlanta Hawks", "status": "OUT", "detail": "d",
         "report_date": "2026-06-20", "source": "espn", "source_url": "u1", "fetched_at": _iso(10)},
    ])
    out = R.injury_report("nba", player="Trae Young")
    assert out["status"] == "refused"
    assert "staleness" in out["note"]


def test_injury_report_no_entity_supplied_is_no_data(tmp_path, monkeypatch):
    _write_injury_rows(monkeypatch, tmp_path, [
        {"player_name": "Trae Young", "team": "Atlanta Hawks", "status": "OUT", "detail": "d",
         "report_date": "2026-07-12", "source": "espn", "source_url": "u1", "fetched_at": _iso(0.1)},
    ])
    out = R.injury_report("nba")
    assert out["status"] == "no_data"


def test_news_context_latest_by_team_newest_first(tmp_path, monkeypatch):
    _write_news_rows(monkeypatch, tmp_path, [
        {"headline": "old story", "url": "u1", "published": _iso(3), "source": "espn_news",
         "sport": "nba", "categories": [], "teams": ["Atlanta Hawks"], "players": []},
        {"headline": "new story", "url": "u2", "published": _iso(0.2), "source": "espn_news",
         "sport": "nba", "categories": [], "teams": ["Atlanta Hawks"], "players": ["Trae Young"]},
    ])
    out = R.news_context("nba", team="Atlanta Hawks")
    assert out["status"] == "ok"
    assert out["category"] == "edge_facts_news_context"
    assert out["n"] == 2
    assert out["rows"][0]["headline"] == "new story"


def test_news_context_absent_file_is_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(R.FS, "FACTS_DIR", tmp_path)
    out = R.news_context("nba", team="Atlanta Hawks")
    assert out["status"] == "no_data"


def test_news_context_entity_miss_is_no_data(tmp_path, monkeypatch):
    _write_news_rows(monkeypatch, tmp_path, [
        {"headline": "story", "url": "u1", "published": _iso(0.1), "source": "espn_news",
         "sport": "nba", "categories": [], "teams": ["Atlanta Hawks"], "players": []},
    ])
    out = R.news_context("nba", team="Miami Heat")
    assert out["status"] == "no_data"


def test_news_context_stale_is_refused(tmp_path, monkeypatch):
    _write_news_rows(monkeypatch, tmp_path, [
        {"headline": "story", "url": "u1", "published": _iso(8), "source": "espn_news",
         "sport": "nba", "categories": [], "teams": ["Atlanta Hawks"], "players": []},
    ])
    out = R.news_context("nba", team="Atlanta Hawks")
    assert out["status"] == "refused"


def test_resolve_dispatches_by_category_and_rejects_unknown(tmp_path, monkeypatch):
    _write_injury_rows(monkeypatch, tmp_path, [
        {"player_name": "Trae Young", "team": "Atlanta Hawks", "status": "OUT", "detail": "d",
         "report_date": "2026-07-12", "source": "espn", "source_url": "u1", "fetched_at": _iso(0.1)},
    ])
    assert R.resolve("injury_report", "nba", player="Trae Young")["status"] == "ok"
    assert R.resolve("bogus_category", "nba")["status"] == "not_supported"
