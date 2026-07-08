"""Synthetic-ledger tests for paper_analytics.py -- grouping math, window
filtering, arb tagging, and greenlight attachment. No dependency on the
real (large, growing) data/frontend/clv_ledger.jsonl."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.platformkit.intel_query import paper_analytics as pa

NOW = datetime(2026, 7, 7, 12, 0, 0, tzinfo=timezone.utc)


def _row(days_ago: float, **kw) -> dict:
    ts = NOW - timedelta(days=days_ago)
    base = {
        "ts": ts.isoformat(),
        "sport": "mlb",
        "channel": "paper",
        "taken_book": "kalshi",
        "market_type": "moneyline",
        "status": "open",
    }
    base.update(kw)
    return base


@pytest.fixture
def ledger(tmp_path: Path) -> Path:
    rows = [
        # settled, channel=paper, win, 0.5 days ago
        _row(0.5, channel="paper", status="settled", outcome="win", unit_result=1.0),
        # settled, channel=paper, loss, 2 days ago (inside week, outside today)
        _row(2, channel="paper", status="settled", outcome="loss", unit_result=-1.0),
        # settled, channel=paper_ingame, win, 10 days ago (outside week)
        _row(10, channel="paper_ingame", status="settled", outcome="win", unit_result=1.0, taken_book="draftkings"),
        # settled, channel=paper_pm, push, 1 day ago
        _row(1, channel="paper_pm", status="settled", outcome="push", unit_result=0.0),
        # open, channel=paper, 0.1 days ago
        _row(0.1, channel="paper", status="open"),
        # open, channel=paper, 5 days ago
        _row(5, channel="paper", status="open"),
        # arb-tagged, settled win, 0.2 days ago
        _row(0.2, channel="paper", market_type="arb", status="settled", outcome="win", unit_result=2.0),
        # arb-tagged, open, 3 days ago
        _row(3, channel="paper", market_type="arb", status="open"),
        # settled with no ts (malformed timestamp) -- must be skippable/handled, not fatal
        {"sport": "mlb", "channel": "paper", "status": "settled", "outcome": "win", "unit_result": 1.0},
    ]
    path = tmp_path / "clv_ledger.jsonl"
    with open(path, "w", encoding="ascii") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
        f.write("not json at all\n")  # malformed line -- must be skipped, not fatal
        f.write("\n")  # blank line
    return path


@pytest.fixture
def greenlight(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "edge_greenlight.json"
    data = {"channels": {"paper": {"status": "AMBER"}, "paper_ingame": {"status": "RED"},
                          "paper_pm": {"status": "RED"}}}
    with open(path, "w", encoding="ascii") as f:
        json.dump(data, f)
    monkeypatch.setattr(pa, "GREENLIGHT_PATH", path)
    return path


def test_summary_all_time_by_channel_units_and_counts(ledger, greenlight):
    result = pa.summary(window_days=None, group_by="channel", ledger_path=ledger, now=NOW)
    assert result["answerable"] is True
    assert result["edge_claimed"] is False
    groups = result["groups"]
    paper = groups["paper"]
    # settled paper rows: win(1.0), loss(-1.0), arb-win(2.0), no-ts win(1.0) = 4 settled
    assert paper["n_settled"] == 4
    assert paper["n_win"] == 3
    assert paper["n_loss"] == 1
    assert paper["net_units"] == pytest.approx(3.0)
    assert paper["n_open"] == 3  # 2 plain open + 1 arb open
    assert paper["greenlight_status"] == "AMBER"
    assert groups["paper_ingame"]["greenlight_status"] == "RED"
    assert groups["paper_pm"]["n_push"] == 1


def test_window_filtering_today_excludes_older_rows(ledger, greenlight):
    result = pa.summary(window_days=1, group_by="channel", ledger_path=ledger, now=NOW)
    paper = result["groups"]["paper"]
    # within 1 day: win(0.5d, +1.0), open(0.1d), arb-win(0.2d, +2.0) -- loss@2d and open@5d excluded
    assert paper["n_settled"] == 2
    assert paper["net_units"] == pytest.approx(3.0)
    assert paper["n_open"] == 1
    assert "paper_ingame" not in result["groups"]  # its only row is 10 days old


def test_window_filtering_this_week(ledger, greenlight):
    result = pa.summary(window_days=7, group_by="channel", ledger_path=ledger, now=NOW)
    assert "paper_ingame" not in result["groups"]  # 10 days old, outside 7-day window
    assert "paper_pm" in result["groups"]  # 1 day old, inside


def test_group_by_venue(ledger, greenlight):
    result = pa.summary(window_days=None, group_by="venue", ledger_path=ledger, now=NOW)
    assert "kalshi" in result["groups"]
    assert "draftkings" in result["groups"]
    assert result["groups"]["draftkings"]["n_win"] == 1


def test_group_by_invalid_raises(ledger):
    with pytest.raises(ValueError):
        pa.summary(group_by="not_a_field", ledger_path=ledger)


def test_arb_lane_summary_only_counts_arb_rows(ledger, greenlight):
    result = pa.arb_lane_summary(window_days=None, ledger_path=ledger, now=NOW)
    assert result["arb"]["n_settled"] == 1
    assert result["arb"]["n_win"] == 1
    assert result["arb"]["net_units"] == pytest.approx(2.0)
    assert result["arb"]["n_open"] == 1


def test_settlement_backlog_buckets_by_age(ledger, greenlight):
    result = pa.settlement_backlog(ledger_path=ledger, now=NOW)
    # open rows: 0.1d (paper), 5d (paper), 3d (arb open)
    assert result["n_open"] == 3
    assert result["age_buckets"]["under_1d"] == 1
    assert result["age_buckets"]["1_to_3d"] == 0
    assert result["age_buckets"]["3_to_7d"] == 2  # 3d row lands here (age < 3 is false at exactly 3.0)
    assert result["age_buckets"]["over_7d"] == 0


def test_today_and_this_week_conveniences(ledger, greenlight):
    t = pa.today(ledger_path=ledger, now=NOW)
    w = pa.this_week(ledger_path=ledger, now=NOW)
    assert t["window_days"] == 1
    assert w["window_days"] == 7


def test_ask_paper_routes_keywords(ledger, greenlight, monkeypatch):
    monkeypatch.setattr(pa, "LEDGER_PATH", ledger)
    monkeypatch.setattr(pa, "GREENLIGHT_PATH", greenlight)
    r = pa.ask_paper("how did paper do this week by channel")
    assert r["window_days"] == 7
    assert r["group_by"] == "channel"

    r = pa.ask_paper("what settled today")
    assert r["window_days"] == 1

    r = pa.ask_paper("how many arb pairs graded")
    assert "arb" in r

    r = pa.ask_paper("settlement backlog")
    assert "age_buckets" in r

    r = pa.ask_paper("which venue has the best fill quality")
    assert r["group_by"] == "venue"


def test_missing_ledger_file_returns_empty_not_crash(tmp_path):
    missing = tmp_path / "nope.jsonl"
    result = pa.summary(ledger_path=missing)
    assert result["answerable"] is True
    assert result["n_rows_considered"] == 0


def test_missing_greenlight_status_is_unknown_not_forced_green(ledger, tmp_path, monkeypatch):
    monkeypatch.setattr(pa, "GREENLIGHT_PATH", tmp_path / "does_not_exist.json")
    result = pa.summary(group_by="channel", ledger_path=ledger, now=NOW)
    assert result["groups"]["paper"]["greenlight_status"] == "unknown"


def test_no_edge_language_in_output(ledger, greenlight):
    result = pa.summary(ledger_path=ledger, now=NOW, group_by="channel")
    blob = json.dumps(result).lower()
    for banned in ("roi", "pnl", "bankroll"):
        assert banned not in blob
