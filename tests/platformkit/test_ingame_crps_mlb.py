"""Per-file smoke tests for scripts/platformkit/benchmarks/crps_market/ingame_mlb
-- ticker join, checkpoint anchoring, and market-point extraction (incl. the
spread->home_margin polarity conversion). Synthetic frames only, no real corpus
reads (those are exercised by the CLI itself, not by this test file).

Run: python -m pytest tests/platformkit/test_ingame_crps_mlb.py -q
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from scripts.platformkit.benchmarks.crps_market.ingame_mlb import (
    checkpoint_ts, load_state_timeline, margin_market_points, resolve_game_pk,
    total_market_points,
)


def _by_key(rows):
    """rows: (game_pk, date, away, home) -> by_key dict shaped like load_statcast_index."""
    out = {}
    for pk, d, a, h in rows:
        out.setdefault((d, a, h), []).append(pk)
    return out


def test_resolve_game_pk_exact_date():
    by_key = _by_key([(101, dt.date(2026, 7, 1), "TEX", "CLE")])
    got = resolve_game_pk("26JUL011310TEXCLE", by_key)
    assert got == (101, "TEX", "CLE")


def test_resolve_game_pk_day_before_fallback():
    by_key = _by_key([(101, dt.date(2026, 6, 30), "TEX", "CLE")])
    got = resolve_game_pk("26JUL011310TEXCLE", by_key)
    assert got == (101, "TEX", "CLE")


def test_resolve_game_pk_ambiguous_doubleheader_skips():
    by_key = _by_key([
        (101, dt.date(2026, 7, 1), "TEX", "CLE"),
        (102, dt.date(2026, 7, 1), "TEX", "CLE"),
    ])
    assert resolve_game_pk("26JUL011310TEXCLE", by_key) is None


def test_resolve_game_pk_unparseable_ticker():
    assert resolve_game_pk("26JUL071415MILSTLG1", {}) is None


def test_checkpoint_ts_finds_first_row_past_inning():
    tl = pd.DataFrame({
        "ts": pd.to_datetime(["2026-07-01T00:00:00Z", "2026-07-01T00:30:00Z",
                              "2026-07-01T01:00:00Z"], utc=True),
        "inning": [3, 4, 5],
    })
    cp = checkpoint_ts(tl, end_inning=3)
    assert cp == pd.Timestamp("2026-07-01T00:30:00Z")


def test_checkpoint_ts_none_when_inning_never_reached():
    tl = pd.DataFrame({"ts": pd.to_datetime(["2026-07-01T00:00:00Z"], utc=True), "inning": [2]})
    assert checkpoint_ts(tl, end_inning=7) is None


def test_checkpoint_ts_empty_timeline():
    assert checkpoint_ts(pd.DataFrame(columns=["ts", "inning"]), end_inning=3) is None


def test_load_state_timeline_parses_and_skips_malformed(tmp_path):
    p = tmp_path / "g.jsonl"
    p.write_text(
        '{"ts": "2026-07-01T00:00:00Z", "state_summary": "inning=1 half=top outs=0"}\n'
        'not json\n'
        '{"ts": "2026-07-01T00:01:00Z", "state_summary": "inning=2 half=top outs=0"}\n',
        encoding="utf-8")
    tl = load_state_timeline(p)
    assert list(tl["inning"]) == [1, 2]


def _event(rows):
    df = pd.DataFrame(rows, columns=["side", "ts", "prob"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df


def test_total_market_points_picks_last_tick_within_tolerance():
    ev = _event([
        ("9", "2026-07-01T00:00:00Z", 0.6),
        ("9", "2026-07-01T00:05:00Z", 0.55),   # last within tol -> wins
        ("10", "2026-07-01T00:59:00Z", 0.4),   # >10min stale -> excluded
    ])
    pts = total_market_points(ev, pd.Timestamp("2026-07-01T00:08:00Z"))
    assert pts == [(9.0, 0.55)]


def test_margin_market_points_away_team_flips_polarity():
    """side "SD5" with SD as the AWAY team -> P(home_margin < -5) = 1 - p."""
    ev = _event([("SD5", "2026-07-01T00:00:00Z", 0.3)])
    pts = margin_market_points(ev, pd.Timestamp("2026-07-01T00:01:00Z"), away_abbr="SD")
    assert pts == [(-5.0, 0.7)]


def test_margin_market_points_home_team_keeps_polarity():
    ev = _event([("LAD5", "2026-07-01T00:00:00Z", 0.3)])
    pts = margin_market_points(ev, pd.Timestamp("2026-07-01T00:01:00Z"), away_abbr="SD")
    assert pts == [(5.0, 0.3)]


def test_margin_market_points_unparseable_side_skipped():
    ev = _event([("bogus", "2026-07-01T00:00:00Z", 0.3)])
    assert margin_market_points(ev, pd.Timestamp("2026-07-01T00:01:00Z"), away_abbr="SD") == []
