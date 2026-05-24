"""Tests for scripts/fetch_actuals.py — nba_api box-score scrape (cycle 70)."""
from __future__ import annotations

import csv
import os
import sys
import tempfile

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import scripts.fetch_actuals as fa  # noqa: E402


def _box_row(name, pts=20, reb=5, ast=4, fg3m=2, stl=1, blk=0, to=2, minutes="30:15"):
    """Mimic nba_api BoxScoreTraditionalV2 row shape."""
    return {
        "PLAYER_NAME": name, "MIN": minutes,
        "PTS": pts, "REB": reb, "AST": ast, "FG3M": fg3m,
        "STL": stl, "BLK": blk, "TO": to,
        # Other columns the endpoint returns but we don't use:
        "FGM": 7, "FGA": 14, "FG3A": 5, "FTM": 4, "FTA": 5,
    }


def test_rows_for_player_emits_seven_stats():
    rows = fa.rows_for_player(
        _box_row("Nikola Jokic", pts=28, reb=12, ast=8, fg3m=1, stl=1, blk=2, to=4),
        "2026-05-24",
    )
    # 7 stats per player
    assert len(rows) == 7
    by_stat = {r["stat"]: r["actual_value"] for r in rows}
    assert by_stat == {"pts": "28", "reb": "12", "ast": "8",
                       "fg3m": "1", "stl": "1", "blk": "2", "tov": "4"}
    assert all(r["date"] == "2026-05-24" for r in rows)
    assert all(r["player"] == "Nikola Jokic" for r in rows)


def test_rows_for_player_skips_dnps():
    """MIN = None / "" / "0" / "0:00" / 0 → DNP, no rows emitted."""
    for dnp_min in (None, "", "0", "0:00"):
        rows = fa.rows_for_player(_box_row("Bench Guy", minutes=dnp_min),
                                    "2026-05-24")
        assert rows == [], f"failed for MIN={dnp_min!r}"


def test_rows_for_player_skips_missing_stats():
    """If the endpoint dropped a stat column, skip just that one — don't crash."""
    row = _box_row("Partial Player")
    del row["BLK"]
    rows = fa.rows_for_player(row, "2026-05-24")
    stats = {r["stat"] for r in rows}
    assert "blk" not in stats
    assert "pts" in stats   # others still present


def test_rows_for_player_skips_blank_name():
    rows = fa.rows_for_player(_box_row(""), "2026-05-24")
    assert rows == []


def test_fetch_actuals_for_date_flattens_multiple_games():
    """Two games → players from both should appear in the output."""
    def fake_games(date_str):
        return [{"game_id": "0001"}, {"game_id": "0002"}]
    def fake_box(game_id):
        # Game 1: Jokic + LeBron. Game 2: Curry.
        return {
            "0001": [_box_row("Nikola Jokic"), _box_row("LeBron James")],
            "0002": [_box_row("Stephen Curry")],
        }[game_id]
    rows = fa.fetch_actuals_for_date("2026-05-24",
                                       games_fn=fake_games, box_fn=fake_box)
    players = {r["player"] for r in rows}
    assert players == {"Nikola Jokic", "LeBron James", "Stephen Curry"}
    # 3 players × 7 stats = 21 rows
    assert len(rows) == 21


def test_fetch_actuals_for_date_handles_empty_schedule():
    rows = fa.fetch_actuals_for_date("2026-05-24",
                                       games_fn=lambda d: [],
                                       box_fn=lambda g: [])
    assert rows == []


def test_fetch_actuals_for_date_skips_games_with_no_game_id():
    """Defensive: scoreboard payload missing game_id → skip game, don't crash."""
    def games(d): return [{"home_id": 1, "away_id": 2}]   # no game_id
    rows = fa.fetch_actuals_for_date("2026-05-24",
                                       games_fn=games,
                                       box_fn=lambda g: [_box_row("X")])
    assert rows == []


def test_write_csv_matches_settle_bets_schema():
    """Output schema MUST match what settle_bets.load_actuals reads."""
    rows = fa.rows_for_player(_box_row("Nikola Jokic", pts=28, reb=12),
                                "2026-05-24")
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "actuals.csv")
        n = fa.write_csv(rows, out)
        assert n == 7
        with open(out) as fh:
            head = next(csv.DictReader(fh))
        # settle_bets.load_actuals reads exactly these column names.
        assert set(head.keys()) == {"date", "player", "stat", "actual_value"}


def test_write_csv_creates_parent_dir():
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "deep", "nested", "actuals.csv")
        fa.write_csv(fa.rows_for_player(_box_row("X"), "2026-05-24"), out)
        assert os.path.exists(out)


def test_round_trip_through_settle_bets():
    """End-to-end: actuals from fetch_actuals → settle_bets matches Jokic OVER."""
    import scripts.settle_bets as sb
    rows = fa.rows_for_player(_box_row("Nikola Jokic", pts=28, reb=12),
                                "2026-05-24")
    with tempfile.TemporaryDirectory() as tmp:
        actuals_path = os.path.join(tmp, "actuals.csv")
        fa.write_csv(rows, actuals_path)
        loaded = sb.load_actuals(actuals_path)
    # settle_bets keys by canonical name.
    assert ("2026-05-24", "nikola jokic", "pts") in loaded
    assert loaded[("2026-05-24", "nikola jokic", "pts")] == 28.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
