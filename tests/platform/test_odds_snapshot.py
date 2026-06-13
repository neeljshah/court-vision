"""test_odds_snapshot.py — acceptance tests for the timestamped odds snapshot ledger.

All disk writes go to pytest's tmp_path (root=) — the real data/domains/ tree is
NEVER touched.  An injected stub OddsFeed supplies synthetic GameOdds (no network).
Confirms append-only accumulation, round-trip load, first-vs-latest line_movement
delta, the gitignored-local path, and graceful empty-feed handling.

Python 3.9 compatible.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pytest

from scripts.platformkit.frontend.feed import GameOdds, OddsFeed, Quote
from scripts.platformkit.frontend.odds_snapshot import (
    line_movement,
    load_snapshots,
    snapshot_sport,
)


# --------------------------------------------------------------------------- #
# Stub feed: returns whatever GameOdds it was constructed with (no network)    #
# --------------------------------------------------------------------------- #

class _StubFeed(OddsFeed):
    name = "stub_test"

    def __init__(self, games: List[GameOdds]) -> None:
        self._games = games

    def is_live(self) -> bool:
        return False

    def fetch(self, sport: str, *, date: Optional[str] = None) -> List[GameOdds]:
        return list(self._games)


def _game(home_ml: float = 1.5, away_ml: float = 2.64) -> GameOdds:
    quotes = [
        Quote("draftkings", "h2h", "home", home_ml),
        Quote("draftkings", "h2h", "away", away_ml),
        Quote("draftkings", "totals", "over", 1.9091, line=216.5),
    ]
    return GameOdds(
        "basketball_nba:2026-06-14:New York Knicks@San Antonio Spurs",
        "basketball_nba", "San Antonio Spurs", "New York Knicks",
        "2026-06-14T23:00Z", quotes, "espn_free",
    )


# --------------------------------------------------------------------------- #
# 1. snapshot_sport writes JSONL under the expected gitignored-local path       #
# --------------------------------------------------------------------------- #

def test_snapshot_writes_to_expected_path(tmp_path: Path) -> None:
    feed = _StubFeed([_game()])
    path = snapshot_sport("basketball_nba", feed=feed, root=tmp_path,
                          ts_utc="2026-06-13T18:00:00+00:00")
    expected = (tmp_path / "data" / "domains" / "basketball_nba"
                / "odds_snapshots" / "snapshots.jsonl")
    assert path == expected
    assert path.exists()
    # never wrote data/registry/
    assert not (tmp_path / "data" / "registry").exists()


# --------------------------------------------------------------------------- #
# 2. Round-trip: load_snapshots returns the rows just written, schema correct  #
# --------------------------------------------------------------------------- #

def test_snapshot_round_trip_schema(tmp_path: Path) -> None:
    feed = _StubFeed([_game()])
    snapshot_sport("basketball_nba", feed=feed, root=tmp_path,
                   ts_utc="2026-06-13T18:00:00+00:00")
    rows = load_snapshots("basketball_nba", root=tmp_path)
    assert len(rows) == 3  # 3 quotes flattened to 3 rows
    expected_keys = {"ts", "game_id", "sport", "home", "away", "commence_time",
                     "book", "market", "side", "decimal_odds", "line", "source"}
    for r in rows:
        assert set(r.keys()) == expected_keys
        assert r["ts"] == "2026-06-13T18:00:00+00:00"
        assert r["sport"] == "basketball_nba"
        assert r["book"] == "draftkings"
        assert r["source"] == "espn_free"


# --------------------------------------------------------------------------- #
# 3. Append-only: two snapshots accumulate rows (history preserved)            #
# --------------------------------------------------------------------------- #

def test_append_only_accumulates(tmp_path: Path) -> None:
    feed = _StubFeed([_game()])
    snapshot_sport("basketball_nba", feed=feed, root=tmp_path,
                   ts_utc="2026-06-13T18:00:00+00:00")
    snapshot_sport("basketball_nba", feed=feed, root=tmp_path,
                   ts_utc="2026-06-13T19:00:00+00:00")
    rows = load_snapshots("basketball_nba", root=tmp_path)
    assert len(rows) == 6  # 3 + 3, nothing overwritten
    assert {r["ts"] for r in rows} == {
        "2026-06-13T18:00:00+00:00", "2026-06-13T19:00:00+00:00"}


# --------------------------------------------------------------------------- #
# 4. line_movement: first-vs-latest decimal_odds delta is correct             #
# --------------------------------------------------------------------------- #

def test_line_movement_first_vs_latest_delta(tmp_path: Path) -> None:
    # snapshot 1: home ML decimal 1.50; snapshot 2: home ML decimal 1.60 (moved)
    snapshot_sport("basketball_nba", feed=_StubFeed([_game(home_ml=1.50)]),
                   root=tmp_path, ts_utc="2026-06-13T18:00:00+00:00")
    snapshot_sport("basketball_nba", feed=_StubFeed([_game(home_ml=1.60)]),
                   root=tmp_path, ts_utc="2026-06-13T19:00:00+00:00")
    mv = line_movement("basketball_nba", root=tmp_path)
    assert mv["sport"] == "basketball_nba"
    home_h2h = next(m for m in mv["movements"]
                    if m["book"] == "draftkings" and m["market"] == "h2h"
                    and m["side"] == "home")
    assert home_h2h["first"] == pytest.approx(1.50)
    assert home_h2h["latest"] == pytest.approx(1.60)
    assert home_h2h["delta"] == pytest.approx(0.10)
    assert home_h2h["first_ts"] == "2026-06-13T18:00:00+00:00"
    assert home_h2h["latest_ts"] == "2026-06-13T19:00:00+00:00"
    assert "honest_note" in mv


# --------------------------------------------------------------------------- #
# 5. Empty feed -> no crash, no rows, line_movement empty                      #
# --------------------------------------------------------------------------- #

def test_empty_feed_no_crash(tmp_path: Path) -> None:
    path = snapshot_sport("mlb_sbro", feed=_StubFeed([]), root=tmp_path,
                          ts_utc="2026-06-13T18:00:00+00:00")
    assert path.exists()  # file created even with zero rows
    assert load_snapshots("mlb_sbro", root=tmp_path) == []
    mv = line_movement("mlb_sbro", root=tmp_path)
    assert mv["n_keys"] == 0
    assert mv["movements"] == []


# --------------------------------------------------------------------------- #
# 6. load_snapshots on an absent sport returns [] (no crash)                   #
# --------------------------------------------------------------------------- #

def test_load_absent_sport_returns_empty(tmp_path: Path) -> None:
    assert load_snapshots("soccer_fd", root=tmp_path) == []
    mv = line_movement("soccer_fd", root=tmp_path)
    assert mv["n_keys"] == 0


# --------------------------------------------------------------------------- #
# 7. A feed that raises is caught -> snapshot still writes (zero rows)         #
# --------------------------------------------------------------------------- #

def test_feed_error_is_caught(tmp_path: Path) -> None:
    class _Boom(OddsFeed):
        name = "boom"

        def is_live(self) -> bool:
            return False

        def fetch(self, sport: str, *, date: Optional[str] = None):
            raise RuntimeError("feed exploded")

    path = snapshot_sport("basketball_nba", feed=_Boom(), root=tmp_path,
                          ts_utc="2026-06-13T18:00:00+00:00")
    assert path.exists()
    assert load_snapshots("basketball_nba", root=tmp_path) == []
