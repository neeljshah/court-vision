"""Focused leakage and freshness tests for N12 coherence features."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.platformkit.signals.market_coherence import build_features, estimate_shin_z
from scripts.platformkit.signals.market_micro_asof import load_archive


COMMENCE = datetime(2026, 9, 2, 0, 0, tzinfo=timezone.utc)


def _record(market_type, side, captured, probability, implied, **extra):
    return {
        "game_id": "g2", "market_type": market_type, "side": side, "book": "book_a",
        "commence_time": COMMENCE.isoformat(), "captured_at": captured.isoformat(),
        "devigged_prob": probability, "implied_prob": implied, **extra,
    }


def _records():
    reference = COMMENCE - timedelta(hours=1)
    return [
        _record("moneyline", "home", reference, 0.52, 0.55),
        _record("moneyline", "away", reference, 0.48, 0.51),
        _record("spread", "home", reference, 0.52, 0.55, line=-3.0),
        _record("spread", "away", reference, 0.48, 0.51, line=3.0),
    ]


def test_horizon_truncation_is_exact_and_shin_is_bounded():
    records = _records()
    cutoff = COMMENCE - timedelta(hours=1)
    future = records + [_record("moneyline", "home", cutoff + timedelta(seconds=1), 0.99, 0.99)]
    baseline = build_features(records)
    truncated = [record for record in future if datetime.fromisoformat(record["captured_at"]) <= cutoff]
    assert build_features(future) == baseline == build_features(truncated)
    moneyline = next(row for row in baseline if row["market_type"] == "moneyline")
    assert moneyline["overround_level"] >= 1.0
    assert 0.0 <= moneyline["shin_z_estimate"] <= 0.5
    assert math.isfinite(moneyline["related_market_coherence"])
    assert 0.0 <= estimate_shin_z([0.55, 0.51]) <= 0.5


def test_stale_cross_market_leg_emits_nan_instead_of_incoherence():
    records = _records()
    records[2]["captured_at"] = (COMMENCE - timedelta(hours=1, minutes=6)).isoformat()
    row = next(row for row in build_features(records) if row["market_type"] == "moneyline")
    assert math.isnan(row["related_market_coherence"])


def test_stale_outcome_leg_does_not_produce_overround_or_shin():
    records = _records()
    records[1]["captured_at"] = (COMMENCE - timedelta(hours=1, minutes=6)).isoformat()
    row = next(row for row in build_features(records) if row["market_type"] == "moneyline")
    assert math.isnan(row["overround_level"])
    assert math.isnan(row["shin_z_estimate"])


def test_real_archive_overround_and_shin_bounds_when_available():
    root = Path(__file__).resolve().parents[3] / "data" / "cache" / "line_history"
    if not root.exists():
        pytest.skip("owned tick archive is not present in this worktree")
    rows = build_features(load_archive(root))
    emitted = [row for row in rows if math.isfinite(row["overround_level"])]
    assert emitted
    assert all(row["overround_level"] >= 1.0 for row in emitted)
    shin = [row["shin_z_estimate"] for row in emitted if math.isfinite(row["shin_z_estimate"])]
    assert shin and all(0.0 <= value <= 0.5 for value in shin)
