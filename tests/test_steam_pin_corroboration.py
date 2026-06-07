"""tests/test_steam_pin_corroboration.py — Pin-as-ground-truth filter
for scripts/line_move_detector.py.

Born from the 2026-05-26 false-positive postmortem: FanDuel's scraper
emitted alt-line rungs (Castle/Fox AST "3.5 @ -1100") as primary, the
detector tagged them as huge moves, but Pinnacle's main line never
budged off 6.5 (Castle) / 5.5 (Fox). These tests pin the filter that
suppresses that entire class of false positive going forward.
"""
from __future__ import annotations

import importlib.util
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LMD_PATH = os.path.join(os.path.dirname(HERE), "scripts", "line_move_detector.py")
spec = importlib.util.spec_from_file_location("line_move_detector", LMD_PATH)
lmd = importlib.util.module_from_spec(spec)
sys.modules["line_move_detector"] = lmd
spec.loader.exec_module(lmd)  # type: ignore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _pin_df_for(name: str, stat: str, snapshots):
    """Build a Pin DataFrame for a single (player, stat) from
    (timestamp, line, over, under) tuples."""
    rows = []
    for ts, line, over, under in snapshots:
        rows.append({
            "captured_at": ts,
            "book": "pin",
            "game_id": "1",
            "player_id": "",
            "player_name": name,
            "stat": stat,
            "line": line,
            "over_price": over,
            "under_price": under,
            "start_time": "2026-05-27T00:35:00Z",
        })
    df = pd.DataFrame(rows)
    df = lmd.collapse_to_main_line(df)
    df = df.copy()
    df["name_key"] = df["player_name"].apply(lmd._name_key)
    df["_ts"] = df["captured_at"].apply(lmd._parse_ts)
    df["line"] = pd.to_numeric(df["line"], errors="coerce")
    return df[df["_ts"].notna() & df["line"].notna()]


# ---------------------------------------------------------------------------
# 1. Castle AST 2026-05-26 false positive must be downgraded
# ---------------------------------------------------------------------------
def test_castle_ast_false_positive_downgraded():
    """Exactly the event from data/cache/line_moves_2026-05-26.json:
    FD shows 5.5 -> 3.5 with odds tightening to -1200. Pin's AST line was
    6.5 the entire window. Must NOT corroborate."""
    fd_event = {
        "book": "fd",
        "player_name": "Stephon Castle",
        "name_key": "stephon castle",
        "stat": "ast",
        "ts_from": "2026-05-26T14:55:00",
        "ts_to": "2026-05-26T14:55:21",
        "line_from": 5.5,
        "line_to": 3.5,
        "line_delta": -2.0,
        "odds_from": -205,
        "odds_to": -1200,
        "odds_pct_delta": 37.3358,
        "tags": ["LINE_DOWN", "ODDS_TIGHTEN"],
        "consensus": False,
    }
    pin_df = _pin_df_for("Stephon Castle", "ast", [
        ("2026-05-26T12:27", 6.5, -112, -118),
        ("2026-05-26T12:28", 6.5, -112, -118),
        ("2026-05-26T15:00", 6.5, -110, -114),
        ("2026-05-26T15:01", 6.5, -110, -114),
        ("2026-05-26T15:02", 6.5, -110, -114),
        ("2026-05-26T15:20", 6.5, -116, -104),
    ])
    corroborated, reason = lmd.pin_corroborates(fd_event, pin_df)
    assert corroborated is False
    assert reason == "pin_flat"

    # tag_pin_corroboration must annotate AND downgrade
    events = lmd.tag_pin_corroboration([fd_event], pin_df)
    assert events[0]["pin_corroborated"] is False
    assert events[0]["pin_corroboration_reason"] == "pin_flat"
    assert "SOFT_BOOK_MOVE_ONLY" in events[0]["tags"]
    # The pre-existing tags must be preserved (additive filter)
    assert "LINE_DOWN" in events[0]["tags"]
    assert "ODDS_TIGHTEN" in events[0]["tags"]


# ---------------------------------------------------------------------------
# 2. Fox AST — the second false positive that same night
# ---------------------------------------------------------------------------
def test_fox_ast_false_positive_downgraded():
    fd_event = {
        "book": "fd",
        "player_name": "De'Aaron Fox",
        "name_key": "de'aaron fox",
        "stat": "ast",
        "ts_from": "2026-05-26T14:55:00",
        "ts_to": "2026-05-26T14:55:21",
        "line_from": 5.5,
        "line_to": 3.5,
        "line_delta": -2.0,
        "odds_from": 106,
        "odds_to": -460,
        "odds_pct_delta": 69.2143,
        "tags": ["LINE_DOWN", "ODDS_TIGHTEN"],
        "consensus": False,
    }
    # Pin shows AST stuck at 5.5 the whole window
    pin_df = _pin_df_for("De'Aaron Fox", "ast", [
        ("2026-05-26T12:27", 5.5, 106, -140),
        ("2026-05-26T12:28", 5.5, 106, -140),
        ("2026-05-26T15:00", 5.5, 108, -136),
        ("2026-05-26T15:01", 5.5, 108, -136),
        ("2026-05-26T15:02", 5.5, 108, -136),
        ("2026-05-26T15:20", 5.5, 110, -133),
    ])
    corroborated, reason = lmd.pin_corroborates(fd_event, pin_df)
    assert corroborated is False
    assert reason == "pin_flat"


# ---------------------------------------------------------------------------
# 3. Real steam — Pin moved in same direction — must corroborate
# ---------------------------------------------------------------------------
def test_real_steam_pin_confirms():
    fd_event = {
        "book": "fd",
        "player_name": "LeBron James",
        "name_key": "lebron james",
        "stat": "pts",
        "ts_from": "2026-05-26T14:00:00",
        "ts_to": "2026-05-26T14:05:00",
        "line_from": 25.5,
        "line_to": 26.5,
        "line_delta": 1.0,
        "odds_from": -110,
        "odds_to": -115,
        "odds_pct_delta": 3.5,
        "tags": ["LINE_UP"],
        "consensus": True,
    }
    pin_df = _pin_df_for("LeBron James", "pts", [
        ("2026-05-26T13:55", 25.5, -110, -110),
        ("2026-05-26T14:10", 26.5, -110, -110),  # Pin moved up too
    ])
    corroborated, reason = lmd.pin_corroborates(fd_event, pin_df)
    assert corroborated is True
    assert reason == "pin_confirms"


# ---------------------------------------------------------------------------
# 4. Pin moved OPPOSITE direction — definitely not steam
# ---------------------------------------------------------------------------
def test_pin_opposite_direction_not_corroborated():
    fd_event = {
        "book": "fd",
        "player_name": "LeBron James",
        "name_key": "lebron james",
        "stat": "pts",
        "ts_from": "2026-05-26T14:00:00",
        "ts_to": "2026-05-26T14:05:00",
        "line_from": 25.5,
        "line_to": 26.5,
        "line_delta": 1.0,
        "odds_from": -110,
        "odds_to": -110,
        "odds_pct_delta": 0.0,
        "tags": ["LINE_UP"],
        "consensus": False,
    }
    pin_df = _pin_df_for("LeBron James", "pts", [
        ("2026-05-26T13:55", 26.5, -110, -110),
        ("2026-05-26T14:10", 25.5, -110, -110),  # Pin moved down
    ])
    corroborated, reason = lmd.pin_corroborates(fd_event, pin_df)
    assert corroborated is False
    assert reason == "pin_opposite"


# ---------------------------------------------------------------------------
# 5. Pin doesn't cover the (player, stat) at all
# ---------------------------------------------------------------------------
def test_no_pin_market_fails_closed():
    """When Pin doesn't have the prop, default to NOT corroborated and tag
    reason='no_pin_market' so the operator can manually review."""
    fd_event = {
        "book": "fd",
        "player_name": "Jared McCain",
        "name_key": "jared mccain",
        "stat": "fg3m",
        "ts_from": "2026-05-26T14:00:00",
        "ts_to": "2026-05-26T14:05:00",
        "line_from": 2.5,
        "line_to": 1.5,
        "line_delta": -1.0,
        "odds_from": -110,
        "odds_to": -300,
        "odds_pct_delta": 25.0,
        "tags": ["LINE_DOWN", "ODDS_TIGHTEN"],
        "consensus": True,
    }
    # Pin only has a different stat for this player
    pin_df = _pin_df_for("Jared McCain", "pts", [
        ("2026-05-26T13:55", 10.5, -148, 111),
        ("2026-05-26T14:10", 10.5, -148, 111),
    ])
    corroborated, reason = lmd.pin_corroborates(fd_event, pin_df)
    assert corroborated is False
    assert reason == "no_pin_market"


# ---------------------------------------------------------------------------
# 6. Pin file totally missing -> no_pin_file (fail closed)
# ---------------------------------------------------------------------------
def test_no_pin_file_at_all():
    fd_event = {
        "book": "fd",
        "player_name": "LeBron James",
        "name_key": "lebron james",
        "stat": "pts",
        "ts_to": "2026-05-26T14:05:00",
        "line_from": 25.5, "line_to": 26.5, "line_delta": 1.0,
        "tags": ["LINE_UP"], "consensus": False,
    }
    empty = pd.DataFrame()
    corroborated, reason = lmd.pin_corroborates(fd_event, empty)
    assert corroborated is False
    assert reason == "no_pin_file"


# ---------------------------------------------------------------------------
# 7. Pin's own events are auto-corroborated (Pin IS the source)
# ---------------------------------------------------------------------------
def test_pin_self_events_auto_corroborate():
    pin_event = {
        "book": "pin",
        "player_name": "LeBron James",
        "name_key": "lebron james",
        "stat": "pts",
        "ts_from": "2026-05-26T14:00:00",
        "ts_to": "2026-05-26T14:05:00",
        "line_from": 25.5, "line_to": 26.5, "line_delta": 1.0,
        "tags": ["LINE_UP"], "consensus": True,
    }
    events = lmd.tag_pin_corroboration([pin_event], pd.DataFrame())
    assert events[0]["pin_corroborated"] is True
    assert events[0]["pin_corroboration_reason"] == "self_is_pin"


# ---------------------------------------------------------------------------
# 8. Odds-only events with no LINE_UP/LINE_DOWN tag pass through
# ---------------------------------------------------------------------------
def test_odds_only_event_passes_through():
    """Holmgren-style 'odds tightened but line stayed' move can't be
    line-corroborated. Returns True so we don't suppress those (they're
    a separate signal class)."""
    odds_only = {
        "book": "fd",
        "player_name": "Chet Holmgren",
        "name_key": "chet holmgren",
        "stat": "fg3m",
        "ts_from": "2026-05-26T12:25:43",
        "ts_to": "2026-05-26T14:57:21",
        "line_from": 1.5, "line_to": 1.5, "line_delta": 0.0,
        "odds_from": 220, "odds_to": 176, "odds_pct_delta": 15.94,
        "tags": ["ODDS_TIGHTEN"], "consensus": False,
    }
    pin_df = _pin_df_for("Chet Holmgren", "fg3m", [
        ("2026-05-26T13:00", 1.5, 200, -250),
        ("2026-05-26T15:00", 1.5, 180, -220),
    ])
    corroborated, reason = lmd.pin_corroborates(odds_only, pin_df)
    assert corroborated is True
    assert reason == "odds_only_event"


# ---------------------------------------------------------------------------
# 9. Full run_once with the actual 2026-05-26 data (regression test)
# ---------------------------------------------------------------------------
def test_run_once_with_pin_filter_castle_downgraded(tmp_path):
    """End-to-end: stage FD + Pin CSVs reproducing the 2026-05-26 bug,
    confirm Castle/Fox AST get pin_corroborated=False."""
    lines_dir = tmp_path / "lines"
    cache_dir = tmp_path / "cache"
    lines_dir.mkdir()
    cache_dir.mkdir()
    vault = tmp_path / "vault" / "line_moves.md"

    # FD shows the spurious alt-line jump
    fd_rows = [
        ["2026-05-26T14:55:00", "fd", "1", "", "Stephon Castle", "ast", 5.5, -205, 175, ""],
        ["2026-05-26T14:55:21", "fd", "1", "", "Stephon Castle", "ast", 3.5, -1200, 700, ""],
        ["2026-05-26T14:55:00", "fd", "1", "", "De'Aaron Fox", "ast", 5.5, 106, -140, ""],
        ["2026-05-26T14:55:21", "fd", "1", "", "De'Aaron Fox", "ast", 3.5, -460, 320, ""],
    ]
    fd_df = pd.DataFrame(fd_rows, columns=[
        "captured_at", "book", "game_id", "player_id", "player_name",
        "stat", "line", "over_price", "under_price", "start_time",
    ])
    fd_df.to_csv(lines_dir / "2026-05-26_fd.csv", index=False)

    # Pin shows the lines never moved
    pin_rows = [
        ["2026-05-26T14:50", "pin", "1", "", "Stephon Castle", "ast", 6.5, -112, -118, ""],
        ["2026-05-26T15:00", "pin", "1", "", "Stephon Castle", "ast", 6.5, -110, -114, ""],
        ["2026-05-26T15:10", "pin", "1", "", "Stephon Castle", "ast", 6.5, -110, -114, ""],
        ["2026-05-26T14:50", "pin", "1", "", "De'Aaron Fox", "ast", 5.5, 106, -140, ""],
        ["2026-05-26T15:00", "pin", "1", "", "De'Aaron Fox", "ast", 5.5, 108, -136, ""],
        ["2026-05-26T15:10", "pin", "1", "", "De'Aaron Fox", "ast", 5.5, 108, -136, ""],
    ]
    pin_df = pd.DataFrame(pin_rows, columns=[
        "captured_at", "book", "game_id", "player_id", "player_name",
        "stat", "line", "over_price", "under_price", "start_time",
    ])
    pin_df.to_csv(lines_dir / "2026-05-26_pin.csv", index=False)

    summary = lmd.run_once(
        "2026-05-26", 0.5, 10.0,
        lines_dir=str(lines_dir),
        cache_dir=str(cache_dir),
        vault_path=str(vault),
    )
    # Both FD events should be detected but downgraded
    assert summary["events_new"] >= 2
    assert summary["downgraded_new"] >= 2 or summary["pin_corroborated_new"] == 0

    cache_path = cache_dir / "line_moves_2026-05-26.json"
    import json as _json
    rows = []
    with open(cache_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(_json.loads(line))
    castle = [r for r in rows
              if r["name_key"] == "stephon castle" and r["stat"] == "ast"
              and r["book"] == "fd"]
    fox = [r for r in rows
           if r["name_key"] == "de'aaron fox" and r["stat"] == "ast"
           and r["book"] == "fd"]
    assert castle, "Castle FD event not recorded"
    assert fox, "Fox FD event not recorded"
    assert all(not c["pin_corroborated"] for c in castle)
    assert all(not f["pin_corroborated"] for f in fox)
    assert all(c["pin_corroboration_reason"] == "pin_flat" for c in castle)
    assert all(f["pin_corroboration_reason"] == "pin_flat" for f in fox)
