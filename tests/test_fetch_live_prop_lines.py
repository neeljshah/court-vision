"""Tests for scripts/fetch_live_prop_lines.py (tier1-1, loop 5).

Covers the spec:
  1. DK mock with 2 players x 3 stats -> 6 rows written
  2. FD mock -> 6 rows written
  3. Dedup: same (player, stat, minute) twice -> 1 row written total
  4. Empty game day -> no crash, 0 rows
  5. 429 mock -> backoff + retry once then abort gracefully
  6. CSV schema matches spec exactly
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.fetch_live_prop_lines as flp  # noqa: E402


def _raw(name, prop_type, line, over=-115, under=-105):
    return {
        "player_name": name,
        "prop_type":   prop_type,
        "line":        line,
        "over_odds":   over,
        "under_odds":  under,
        "fetched_at":  "2026-05-24T17:00:00",
    }


# ── 1. DK happy-path: 2 players x 3 stats -> 6 rows ──────────────────────────

def test_dk_two_players_three_stats_writes_six_rows():
    raw = [
        _raw("Nikola Jokic", "points",   28.5),
        _raw("Nikola Jokic", "rebounds", 11.5),
        _raw("Nikola Jokic", "assists",   7.5),
        _raw("Stephen Curry", "points",   26.5),
        _raw("Stephen Curry", "threes",    4.5),
        _raw("Stephen Curry", "assists",   5.5),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        counts = flp.fetch_once(
            books=["dk"],
            stats_filter=set(flp._VALID_STATS),
            date_str="2026-05-24",
            lines_dir=tmp,
            fetch_fn=lambda book: raw,
            sleep_fn=lambda *_: None,
        )
        assert counts == {"dk": 6}
        path = os.path.join(tmp, "2026-05-24_dk.csv")
        assert os.path.exists(path)
        with open(path) as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 6
        assert {r["player_name"] for r in rows} == {"Nikola Jokic", "Stephen Curry"}
        # Stat normalisation: 'threes' -> 'fg3m'
        curry_fg3m = [r for r in rows
                      if r["player_name"] == "Stephen Curry" and r["stat"] == "fg3m"]
        assert len(curry_fg3m) == 1
        assert curry_fg3m[0]["line"] == "4.5"
        # All rows tagged with the full book name.
        assert {r["book"] for r in rows} == {"draftkings"}


# ── 2. FD happy-path: 2 players x 3 stats -> 6 rows ──────────────────────────

def test_fd_two_players_three_stats_writes_six_rows():
    raw = [
        _raw("Luka Doncic", "points",   30.5),
        _raw("Luka Doncic", "rebounds",  8.5),
        _raw("Luka Doncic", "assists",   9.5),
        _raw("Anthony Davis", "points",  22.5),
        _raw("Anthony Davis", "rebounds",11.5),
        _raw("Anthony Davis", "blocks",   2.5),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        counts = flp.fetch_once(
            books=["fd"],
            stats_filter=set(flp._VALID_STATS),
            date_str="2026-05-24",
            lines_dir=tmp,
            fetch_fn=lambda book: raw,
            sleep_fn=lambda *_: None,
        )
        assert counts == {"fd": 6}
        path = os.path.join(tmp, "2026-05-24_fd.csv")
        with open(path) as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 6
        assert {r["book"] for r in rows} == {"fanduel"}
        # 'blocks' -> 'blk'
        ad_blk = [r for r in rows
                  if r["player_name"] == "Anthony Davis" and r["stat"] == "blk"]
        assert len(ad_blk) == 1


# ── 3. Dedup: same (player, stat, minute) twice -> 1 row ────────────────────

def test_dedup_same_player_stat_minute_keeps_one_row():
    raw = [_raw("Jayson Tatum", "points", 27.5)]
    ts = "2026-05-24T18:00:00"
    rows = flp.parse_props_for_book(raw, "dk", captured_at=ts)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "out.csv")
        # First write should land.
        n1 = flp.append_rows(rows, path)
        # Same minute, exact dup row -> dropped.
        n2 = flp.append_rows(rows, path)
        # Same minute, dup again but different second within same minute -> dropped.
        rows_b = flp.parse_props_for_book(raw, "dk",
                                           captured_at="2026-05-24T18:00:42")
        n3 = flp.append_rows(rows_b, path)
        # Different minute -> SHOULD land.
        rows_c = flp.parse_props_for_book(raw, "dk",
                                           captured_at="2026-05-24T18:01:00")
        n4 = flp.append_rows(rows_c, path)
        with open(path) as fh:
            final = list(csv.DictReader(fh))
        assert (n1, n2, n3, n4) == (1, 0, 0, 1)
        assert len(final) == 2
        # Both rows for same player+stat, different minute keys.
        assert {r["captured_at"][:16] for r in final} == {
            "2026-05-24T18:00", "2026-05-24T18:01"
        }


# ── 4. Empty game day -> no crash, 0 rows ───────────────────────────────────

def test_empty_returns_no_crash_and_zero_rows():
    with tempfile.TemporaryDirectory() as tmp:
        counts = flp.fetch_once(
            books=["dk", "fd"],
            stats_filter=set(flp._VALID_STATS),
            date_str="2026-07-04",       # off-season -> empty
            lines_dir=tmp,
            fetch_fn=lambda book: [],
            sleep_fn=lambda *_: None,
        )
        assert counts == {"dk": 0, "fd": 0}
        # No CSV created when there are no rows to append (graceful no-op).
        assert os.listdir(tmp) == []


# ── 5. 429 mock: retry once then abort gracefully ───────────────────────────

def test_429_triggers_backoff_then_retry_then_skip():
    calls = {"n": 0}
    sleeps: list = []

    def flaky_fetch(book):
        calls["n"] += 1
        # Always rate-limited -> after backoff + retry, give up gracefully.
        raise flp.RateLimitExceeded(f"429 from {book}")

    with tempfile.TemporaryDirectory() as tmp:
        counts = flp.fetch_once(
            books=["dk"],
            stats_filter=set(flp._VALID_STATS),
            date_str="2026-05-24",
            lines_dir=tmp,
            fetch_fn=flaky_fetch,
            sleep_fn=lambda s: sleeps.append(s),
        )
        # Returned cleanly with 0 rows.
        assert counts == {"dk": 0}
        # First attempt + one retry = 2 calls to the underlying fetcher.
        assert calls["n"] == 2
        # The 30-second backoff sleep was issued exactly once.
        assert flp._RATE_429_BACKOFF_SEC in sleeps
        # No CSV created.
        assert os.listdir(tmp) == []


# ── 6. CSV schema matches spec exactly ──────────────────────────────────────

def test_csv_schema_exact_match():
    """captured_at, book, game_id, player_id, player_name, team, stat,
    line, over_price, under_price, market_status - in this order."""
    expected = [
        "captured_at", "book", "game_id", "player_id", "player_name",
        "team", "stat", "line", "over_price", "under_price",
        "market_status",
    ]
    assert flp._FIELDS == expected
    raw = [_raw("Joel Embiid", "points", 32.5, over=-120, under=+100)]
    with tempfile.TemporaryDirectory() as tmp:
        counts = flp.fetch_once(
            books=["dk"],
            stats_filter={"pts"},
            date_str="2026-05-24",
            lines_dir=tmp,
            fetch_fn=lambda book: raw,
            sleep_fn=lambda *_: None,
        )
        assert counts == {"dk": 1}
        path = os.path.join(tmp, "2026-05-24_dk.csv")
        with open(path) as fh:
            header = next(csv.reader(fh))
            assert header == expected
            fh.seek(0)
            row = next(csv.DictReader(fh))
        # Field-by-field assertions.
        assert row["book"] == "draftkings"
        assert row["player_name"] == "Joel Embiid"
        assert row["stat"] == "pts"
        assert row["line"] == "32.5"
        assert row["over_price"] == "-120"
        assert row["under_price"] == "100"
        assert row["market_status"] == "open"
        # Optional NBA IDs are tolerated blank (downstream re-joins on name+date).
        assert row["game_id"] == ""
        assert row["player_id"] == ""
        assert row["team"] == ""
        # captured_at populated with an ISO timestamp.
        assert len(row["captured_at"]) >= 16


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
