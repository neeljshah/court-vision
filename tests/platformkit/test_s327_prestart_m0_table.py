"""Synthetic coverage for S327's labelled prestart selection."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.ingame.prestart_m0_table import build_table, iter_rows, state_events


def _events():
    return state_events([
        {"game_id": "pre", "start_ts": 1000, "home": "Home", "away": "Away"},
        {"game_id": "tip", "start_ts": 1000, "home": "Tip H", "away": "Tip A"},
        {"game_id": "late", "start_ts": 1000, "home": "Late H", "away": "Late A"},
        {"game_id": "rating", "start_ts": 1000, "home": "Rate H", "away": "Rate A"},
    ], "nba")


def test_synthetic_store_selects_latest_prestart_then_tip_then_first_inplay():
    store = Path(".s327_synthetic_store.jsonl")
    rows = [
        {"event_id": "pre", "ts": 900, "probability": 0.2},
        {"event_id": "pre", "ts": 999, "probability": 0.6},
        {"event_id": "tip", "ts": 1020, "probability": 0.7},
        {"event_id": "late", "ts": 1061, "probability": 0.8},
        {"event_id": "rating", "ts": 900, "p0": 0.99, "elo": 9999},
    ]
    store.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    try:
        table, unmapped = build_table(_events(), iter_rows(store), "nba", source="synthetic")
        by_key = {row["event_key"]: row for row in table}
        assert (by_key["pre"]["kind"], by_key["pre"]["p_prestart"]) == ("PRE_START", 0.6)
        assert by_key["tip"]["kind"] == "AT_TIP"
        assert by_key["late"]["kind"] == "FIRST_INPLAY"
        assert by_key["rating"]["kind"] == "NONE"
        assert not unmapped
    finally:
        store.unlink(missing_ok=True)


def test_at_tip_window_ends_at_sixty_seconds_and_later_quote_is_first_inplay():
    events = state_events([
        {"game_id": "on", "start_ts": 1000}, {"game_id": "after", "start_ts": 1000},
    ], "mlb")
    table, _ = build_table(events, [
        {"event_id": "on", "ts": 1060, "p_close": 0.51},
        {"event_id": "after", "ts": 1060.1, "p_close": 0.52},
    ], "mlb")
    by_key = {row["event_key"]: row for row in table}
    assert by_key["on"]["kind"] == "AT_TIP"
    assert by_key["after"]["kind"] == "FIRST_INPLAY"


def test_unmapped_participant_is_listed_and_never_silently_matched():
    events = state_events([{
        "game_id": "known", "start_ts": 1000, "date": "2026-09-08",
        "home": "Known Home", "away": "Known Away",
    }], "soccer")
    table, unmapped = build_table(events, [{
        "date": "2026-09-08", "ts": 900, "home": "Unknown Club", "away": "Known Away",
        "probability": 0.5,
    }], "soccer")
    assert table[0]["kind"] == "NONE"
    assert unmapped == {"unknown club": 1}


def test_rating_like_columns_are_not_eligible_market_probabilities():
    events = state_events([{"game_id": "g", "start_ts": 1000}], "tennis")
    table, _ = build_table(events, [{"event_id": "g", "ts": 999, "p0": 0.9,
                                     "elo": 2100, "prediction": 0.9}], "tennis")
    assert table[0]["kind"] == "NONE"
    assert table[0]["p_prestart"] is None


def test_sec_before_start_is_positive_before_start_negative_after_per_spec():
    """S327_spec.md:38: sec_before_start is negative = after start (positive before)."""
    events = state_events([{"game_id": "pre", "start_ts": 1000}, {"game_id": "tip", "start_ts": 1000}], "nba")
    table, _ = build_table(events, [
        {"event_id": "pre", "ts": 940, "probability": 0.5},
        {"event_id": "tip", "ts": 1030, "probability": 0.6},
    ], "nba")
    by_key = {row["event_key"]: row for row in table}
    assert by_key["pre"]["sec_before_start"] == 60.0
    assert by_key["tip"]["sec_before_start"] == -30.0
    proxy_events = state_events([{"game_id": "proxy", "date": "2026-01-01"}], "mlb")
    proxy_table, _ = build_table(proxy_events, [{
        "event_id": "proxy", "ts": 900, "close_source": "pregame_last_tick_before_commence",
        "close_sec_after_tip": -60.0, "p_close": 0.5,
    }], "mlb", allow_proxy=True)
    assert proxy_table[0]["sec_before_start"] == 60.0
