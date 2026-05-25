"""Tests for scripts/snap_action_network_bets.py (tier3-12, loop 5).

Fully offline - no Action Network network calls. Injects fake fetchers
into snap_once / fetch_scoreboard / fetch_game_props.
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

import scripts.snap_action_network_bets as snab  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_props_payload(props_list):
    """Build a fake /props payload from a list of
    (pid, player, stat, line, pct_bets_over, pct_money_over) tuples.
    """
    players = {}
    by_stat: dict = {}
    for pid, player, stat, line, pct_bets, pct_money in props_list:
        players[str(pid)] = {"full_name": player}
        outcomes = [
            {"side": "over",  "value": line, "odds": -110,
             "bet_info": {"tickets": {"percent": pct_bets},
                          "money":   {"percent": pct_money}}},
            {"side": "under", "value": line, "odds": -110,
             "bet_info": {"tickets": {"percent": 100.0 - pct_bets},
                          "money":   {"percent": 100.0 - pct_money}}},
        ]
        entry = {"player_id": pid,
                 "lines": {snab._BOOK_ID: outcomes}}
        an_key = snab._STAT_TO_AN_PROP[stat]
        by_stat.setdefault(an_key, []).append(entry)
    return {"player_props": by_stat, "players": players}


# ── 1. Mock AN response with 2 props -> 2 rows ───────────────────────────────

def test_two_props_yields_two_rows():
    """A single-game payload with two props produces exactly two snapshot rows
    with the canonical schema fields populated."""
    fake_games = [{"id": 1001}]
    fake_props = _make_props_payload([
        (101, "Nikola Jokic",   "pts", 28.5, 55.0, 60.0),
        (202, "Stephen Curry",  "fg3m", 4.5, 70.0, 55.0),
    ])

    def fake_scoreboard(url, params, headers):
        assert "scoreboard/nba" in url
        assert params["bookIds"] == "15"
        assert params["period"] == "game"
        return {"games": fake_games}

    def fake_props_fn(url, params, headers):
        assert "/games/1001/props" in url
        return fake_props

    with tempfile.TemporaryDirectory() as tmp:
        path, rows = snab.snap_once(date_str="2026-05-24", hhmm="1700",
                                      out_dir=tmp,
                                      scoreboard_fn=fake_scoreboard,
                                      props_fn=fake_props_fn,
                                      sleep_fn=lambda *_: None)
    assert len(rows) == 2
    by_player = {r["player"]: r for r in rows}
    assert by_player["Nikola Jokic"]["stat"] == "pts"
    assert by_player["Nikola Jokic"]["line_current"] == "28.5"
    assert by_player["Nikola Jokic"]["line_opening"] == "28.5"
    assert by_player["Nikola Jokic"]["pct_bets_over"] == "55"
    assert by_player["Nikola Jokic"]["pct_money_over"] == "60"
    # First poll establishes openings -> line_move_dir = 0 -> rlm = N
    assert by_player["Nikola Jokic"]["line_move_dir"] == "0"
    assert by_player["Nikola Jokic"]["rlm_flag"] == "N"


# ── 2. RLM flag computation on 4 fixture scenarios ───────────────────────────

def test_rlm_flag_computation_matches_manual_logic():
    """compute_rlm should match the documented rule on 4 scenarios."""
    # A. Money on OVER (60 vs 50 bets), line moved DOWN -> RLM=True
    move_dir, rlm = snab.compute_rlm(line_opening=28.5, line_current=27.5,
                                       pct_bets_over=50.0, pct_money_over=60.0)
    assert move_dir == -1 and rlm is True

    # B. Money on UNDER (40 money 50 bets => money_on_over=False),
    #    line moved UP -> RLM=True
    move_dir, rlm = snab.compute_rlm(line_opening=4.5, line_current=5.0,
                                       pct_bets_over=50.0, pct_money_over=40.0)
    assert move_dir == 1 and rlm is True

    # C. Money on OVER, line moved UP -> public agrees, NOT RLM
    move_dir, rlm = snab.compute_rlm(line_opening=8.5, line_current=9.0,
                                       pct_bets_over=50.0, pct_money_over=60.0)
    assert move_dir == 1 and rlm is False

    # D. Line unchanged -> never RLM regardless of money skew
    move_dir, rlm = snab.compute_rlm(line_opening=20.5, line_current=20.5,
                                       pct_bets_over=30.0, pct_money_over=70.0)
    assert move_dir == 0 and rlm is False

    # E (bonus) Money/bets gap below 5pp threshold -> NOT RLM even when
    #     line moves against the small money skew
    move_dir, rlm = snab.compute_rlm(line_opening=10.0, line_current=9.5,
                                       pct_bets_over=50.0, pct_money_over=53.0)
    assert move_dir == -1 and rlm is False


# ── 3. Empty game day -> no rows, no crash ───────────────────────────────────

def test_offseason_empty_schedule_no_crash():
    """Scoreboard with zero games (offseason) writes a header-only CSV and
    returns []."""
    def fake_scoreboard(url, params, headers):
        return {"games": []}

    with tempfile.TemporaryDirectory() as tmp:
        path, rows = snab.snap_once(date_str="2026-07-15", hhmm="1200",
                                      out_dir=tmp,
                                      scoreboard_fn=fake_scoreboard,
                                      sleep_fn=lambda *_: None)
        assert rows == []
        assert os.path.exists(path)
        # Header is present (so the file is auditable) but no data rows.
        with open(path, encoding="utf-8") as fh:
            content = fh.read().strip().splitlines()
        assert len(content) == 1
        assert content[0].split(",") == snab._FIELDS


# ── 4. Endpoint unavailable -> graceful exit ─────────────────────────────────

def test_endpoint_unavailable_graceful_exit(caplog):
    """403/404 from scoreboard -> logs a WebSearch hint, writes empty file,
    returns ([], path) - does NOT crash."""
    def fake_scoreboard(url, params, headers):
        raise snab.EndpointUnavailable(
            "AN scoreboard returned 403 - endpoint may have changed")

    with tempfile.TemporaryDirectory() as tmp:
        with caplog.at_level("ERROR", logger="snap_action_network_bets"):
            path, rows = snab.snap_once(date_str="2026-05-24", hhmm="1700",
                                          out_dir=tmp,
                                          scoreboard_fn=fake_scoreboard,
                                          sleep_fn=lambda *_: None)
        assert rows == []
        assert os.path.exists(path)
    text = " ".join(r.message for r in caplog.records).lower()
    assert "endpoint unavailable" in text
    assert "websearch" in text


# ── 5. CSV schema matches spec ───────────────────────────────────────────────

def test_csv_schema_matches_spec():
    """Written CSV must have exactly the spec'd columns in spec order, and
    every row must populate them all."""
    fake_games = [{"id": 2002}]
    fake_props = _make_props_payload([
        (303, "LeBron James", "ast", 7.5, 45.0, 55.0),
    ])

    def fake_scoreboard(url, params, headers):
        return {"games": fake_games}

    def fake_props_fn(url, params, headers):
        return fake_props

    expected = ["captured_at", "game_id", "player_id", "player", "stat",
                "line_opening", "line_current", "pct_bets_over",
                "pct_money_over", "line_move_dir", "rlm_flag"]
    assert snab._FIELDS == expected
    with tempfile.TemporaryDirectory() as tmp:
        path, rows = snab.snap_once(date_str="2026-05-24", hhmm="1700",
                                      out_dir=tmp,
                                      scoreboard_fn=fake_scoreboard,
                                      props_fn=fake_props_fn,
                                      sleep_fn=lambda *_: None)
        with open(path, encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames == expected
            data = list(reader)
    assert len(data) == 1
    row = data[0]
    # Every spec column must be present and non-None (empty string allowed
    # only for pct_bets / pct_money when bet_info absent - not in this test).
    for col in expected:
        assert col in row
    assert row["player"] == "LeBron James"
    assert row["stat"] == "ast"
    assert row["line_opening"] == "7.5"
    assert row["pct_bets_over"] == "45"
    assert row["pct_money_over"] == "55"
    assert row["rlm_flag"] == "N"   # first poll - opening = current


# ── bonus: opening line is preserved across polls ────────────────────────────

def test_opening_line_preserved_across_polls():
    """The first poll establishes line_opening; a second poll with a moved
    current line should still report the original opening."""
    fake_games = [{"id": 3003}]
    poll1_props = _make_props_payload([
        (404, "Luka Doncic", "pts", 32.5, 50.0, 60.0),
    ])
    poll2_props = _make_props_payload([
        (404, "Luka Doncic", "pts", 31.5, 50.0, 60.0),   # line dropped 1.0
    ])
    calls = {"props": iter([poll1_props, poll2_props])}

    def fake_scoreboard(url, params, headers):
        return {"games": fake_games}

    def fake_props_fn(url, params, headers):
        return next(calls["props"])

    with tempfile.TemporaryDirectory() as tmp:
        _, rows1 = snab.snap_once(date_str="2026-05-24", hhmm="1700",
                                    out_dir=tmp,
                                    scoreboard_fn=fake_scoreboard,
                                    props_fn=fake_props_fn,
                                    sleep_fn=lambda *_: None)
        _, rows2 = snab.snap_once(date_str="2026-05-24", hhmm="1800",
                                    out_dir=tmp,
                                    scoreboard_fn=fake_scoreboard,
                                    props_fn=fake_props_fn,
                                    sleep_fn=lambda *_: None)
    assert rows1[0]["line_opening"] == "32.5"
    assert rows1[0]["line_current"] == "32.5"
    assert rows2[0]["line_opening"] == "32.5"   # PRESERVED
    assert rows2[0]["line_current"] == "31.5"
    assert rows2[0]["line_move_dir"] == "-1"
    # Money on OVER (60>50), line moved DOWN -> RLM
    assert rows2[0]["rlm_flag"] == "Y"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
