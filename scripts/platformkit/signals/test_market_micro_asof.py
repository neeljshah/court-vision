"""Focused leakage and stale-quote tests for N12 microstructure features."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.platformkit.signals.market_micro_asof import (
    MAX_MEDIAN_CADENCE_SECONDS, build_features, load_archive,
)


COMMENCE = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)


def _record(captured, probability, book="a"):
    return {
        "game_id": "g1", "market_type": "moneyline", "side": "home", "book": book,
        "commence_time": COMMENCE.isoformat(), "captured_at": captured.isoformat(),
        "devigged_prob": probability,
    }


def _dense_records():
    records = []
    for book, offset in (("a", 0.0), ("b", 0.01)):
        for minute in range(0, 301, 10):
            captured = COMMENCE - timedelta(hours=6) + timedelta(minutes=minute)
            records.append(_record(captured, 0.45 + offset + minute / 10000.0, book))
    return records


def test_horizon_truncation_and_future_extreme_are_exactly_invariant():
    records = _dense_records()
    cutoff = COMMENCE - timedelta(hours=1)
    baseline = build_features(records)
    future = records + [_record(cutoff + timedelta(seconds=1), 0.999, "a")]
    truncated = [record for record in future if datetime.fromisoformat(record["captured_at"]) <= cutoff]
    assert build_features(future) == baseline == build_features(truncated)
    assert not math.isnan(baseline[0]["price_drift_T6_to_T1"])
    assert not math.isnan(baseline[0]["cross_book_dispersion"])


def test_slow_series_has_no_forward_filled_micro_features():
    records = [
        _record(COMMENCE - timedelta(hours=6), 0.45),
        _record(COMMENCE - timedelta(hours=5, minutes=40), 0.50),
        _record(COMMENCE - timedelta(hours=1), 0.55),
        _record(COMMENCE - timedelta(minutes=20), 0.99),
    ]
    row = build_features(records)[0]
    assert row["quote_cadence_seconds"] > MAX_MEDIAN_CADENCE_SECONDS
    for column in ("price_drift_T6_to_T1", "realized_vol_of_prob", "jump_count_pregame"):
        assert math.isnan(row[column])


def test_stale_cross_book_leg_is_not_mixed_into_dispersion():
    records = _dense_records()
    cutoff = COMMENCE - timedelta(hours=1)
    records = [record for record in records if record["book"] != "b" or
               datetime.fromisoformat(record["captured_at"]) < cutoff - timedelta(minutes=5)]
    row = build_features(records)[0]
    assert math.isnan(row["cross_book_dispersion"])


def test_one_stale_book_invalidates_an_otherwise_fresh_cross_book_set():
    records = _dense_records()
    cutoff = COMMENCE - timedelta(hours=1)
    for minute in range(0, 301, 10):
        captured = COMMENCE - timedelta(hours=6) + timedelta(minutes=minute)
        records.append(_record(captured, 0.47 + minute / 10000.0, "c"))
    records = [record for record in records if record["book"] != "c" or
               datetime.fromisoformat(record["captured_at"]) < cutoff - timedelta(minutes=5)]
    row = build_features(records)[0]
    assert math.isnan(row["cross_book_dispersion"])


def test_real_archive_has_a_sport_with_200_game_rows_when_available():
    root = Path(__file__).resolve().parents[3] / "data" / "cache" / "line_history"
    if not root.exists():
        pytest.skip("owned tick archive is not present in this worktree")
    rows = build_features(load_archive(root))
    games_by_sport = {}
    for row in rows:
        games_by_sport.setdefault(row["sport"], set()).add(row["game_id"])
    assert any(len(game_ids) >= 200 for game_ids in games_by_sport.values())
