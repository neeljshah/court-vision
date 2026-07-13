"""Tests for scripts.platformkit.omni.news_knowability.

Per-file run only:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_news_knowability.py -q
"""
from __future__ import annotations

import uuid

import pandas as pd
import pytest

from scripts.platformkit.omni import feature_store as fs
from scripts.platformkit.omni import news_knowability as nk


@pytest.fixture()
def isolated(monkeypatch, tmp_path):
    """Isolate news store + feature store to tmp dirs, and give a unique sport."""
    monkeypatch.setattr(nk, "_NEWS_DIR", tmp_path / "news")
    monkeypatch.setattr(fs, "_STORE_ROOT", tmp_path / "feature_store")
    return tmp_path, f"testsport_{uuid.uuid4().hex[:8]}"


def _write_snapshot(tmp_path, fname, rows):
    pd.DataFrame(rows).to_parquet(tmp_path / fname, index=False)


def test_normalization_status_vocab(isolated):
    tmp_path, sport = isolated
    _write_snapshot(
        tmp_path,
        "snap1.parquet",
        [
            {"player_name": "A Player", "status": "OUT", "fetched_at": "2026-01-01T00:00:00Z", "source": "espn"},
            {"player_name": "B Player", "status": "questionable", "fetched_at": "2026-01-01T00:00:00Z", "source": "espn"},
            {"player_name": "C Player", "status": "PROBABLE", "fetched_at": "2026-01-01T00:00:00Z", "source": "espn"},
        ],
    )
    stats = nk.ingest_news(str(tmp_path / "snap1.parquet"), sport=sport, base_dir=tmp_path / "news")
    assert stats["n_written"] == 3
    events = nk.load_events(base_dir=tmp_path / "news")
    by_player = {e["player_or_entity"]: e["minutes_implication"] for e in events}
    assert by_player["A Player"] == 0  # OUT
    assert by_player["B Player"] == 2  # QUESTIONABLE
    assert by_player["C Player"] == 3  # PROBABLE


def test_unknown_status_skipped_not_guessed(isolated):
    tmp_path, sport = isolated
    _write_snapshot(
        tmp_path,
        "snap1.parquet",
        [
            {"player_name": "A Player", "status": "GARBAGE_TIME_MYSTERY", "fetched_at": "2026-01-01T00:00:00Z", "source": "espn"},
        ],
    )
    stats = nk.ingest_news(str(tmp_path / "snap1.parquet"), sport=sport, base_dir=tmp_path / "news")
    assert stats["n_written"] == 0
    assert stats["n_skipped_unknown_status"] == 1
    assert nk.load_events(base_dir=tmp_path / "news") == []


def test_idempotent_reingest(isolated):
    tmp_path, sport = isolated
    _write_snapshot(
        tmp_path,
        "snap1.parquet",
        [{"player_name": "A Player", "status": "OUT", "fetched_at": "2026-01-01T00:00:00Z", "source": "espn"}],
    )
    stats1 = nk.ingest_news(str(tmp_path / "snap1.parquet"), sport=sport, base_dir=tmp_path / "news")
    stats2 = nk.ingest_news(str(tmp_path / "snap1.parquet"), sport=sport, base_dir=tmp_path / "news")
    assert stats1["n_written"] == 1
    assert stats2["n_written"] == 0
    assert stats2["n_duplicate"] == 1
    assert len(nk.load_events(base_dir=tmp_path / "news")) == 1


def test_knowability_stamp_is_report_ts_not_game_ts_leak_guard(isolated):
    """An item reported AFTER a pregame decision time must not leak into get_asof at that time."""
    tmp_path, sport = isolated
    # Item captured/reported the day AFTER the game (post-game injury update).
    _write_snapshot(
        tmp_path,
        "snap1.parquet",
        [{"player_name": "A Player", "status": "OUT", "fetched_at": "2026-03-02T12:00:00Z", "source": "espn"}],
    )
    nk.ingest_news(str(tmp_path / "snap1.parquet"), sport=sport, base_dir=tmp_path / "news")
    events = nk.load_events(base_dir=tmp_path / "news")
    nk.push_to_feature_store(sport, events)

    pregame_decision_ts = "2026-03-01T18:00:00Z"  # before the report_ts
    out = fs.get_asof(sport, ["A Player"], ["injury_status"], pregame_decision_ts)
    assert out.empty  # must NOT see the post-game-day report at pregame time

    postgame_ts = "2026-03-03T00:00:00Z"
    out2 = fs.get_asof(sport, ["A Player"], ["injury_status"], postgame_ts)
    assert len(out2) == 1
    assert out2.iloc[0]["value"] == 0.0


def test_freshness_report(isolated):
    tmp_path, sport = isolated
    _write_snapshot(
        tmp_path,
        "snap1.parquet",
        [
            {"player_name": "A Player", "status": "OUT", "fetched_at": "2026-01-01T00:00:00Z", "source": "espn"},
            {"player_name": "B Player", "status": "PROBABLE", "fetched_at": "2026-01-02T00:00:00Z", "source": "espn"},
        ],
    )
    nk.ingest_news(str(tmp_path / "snap1.parquet"), sport=sport, base_dir=tmp_path / "news")
    report = nk.freshness_report(base_dir=tmp_path / "news")
    assert report["n_items"] == 2
    assert report["latest_ts"] is not None
    assert (tmp_path / "news" / "freshness.json").is_file()
