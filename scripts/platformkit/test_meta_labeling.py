"""Synthetic decision-ledger coverage for the meta-labeling sizer scaffold."""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.platformkit.meta_labeling import (
    DEFAULT_FLOOR,
    MIN_LABELED_ROWS,
    build_training_rows,
    fit_meta,
    ledger_report,
    predict_p_correct,
    size_from_meta,
)


def _write_ledger(path: Path, n: int, seed: int = 7) -> None:
    """High-|edge| decisions are planted to be right more often than low-|edge| ones."""
    rng = random.Random(seed)
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    with path.open("w", encoding="utf-8") as handle:
        for i in range(n):
            edge = rng.uniform(-0.12, 0.12)
            price = rng.uniform(0.35, 0.65)
            side = "home" if edge >= 0 else "away"
            p_right = min(0.95, max(0.05, 0.5 + 3.0 * abs(edge)))
            won = rng.random() < p_right
            handle.write(json.dumps({
                "ts": (start + timedelta(hours=i)).isoformat(),
                "market": "game_%d" % i,
                "side": side,
                "prob_at_entry": round(min(0.99, max(0.01, price + edge)), 6),
                "market_price_at_entry": round(price, 6),
                "size_units": 1.0,
                "strategy": "pregame" if i % 2 else "ingame",
                "outcome": side if won else ("away" if side == "home" else "home"),
            }) + "\n")


def test_meta_model_ranks_high_edge_higher(tmp_path: Path) -> None:
    """With enough settled rows the meta model separates the planted high-|edge| decisions."""
    ledger = tmp_path / "decisions.jsonl"
    _write_ledger(ledger, 900)
    built = build_training_rows(ledger)
    assert built["status"] == "OK"
    assert built["n_labeled"] == 900
    assert "strategy=pregame" in built["feature_names"]

    fitted = fit_meta(built)
    assert fitted["status"] == "OK"
    assert 0.0 < fitted["in_sample_brier"] < 0.25

    probs = predict_p_correct(fitted, built)
    assert len(probs) == 900
    pairs = sorted(zip((abs(r["edge"]) for r in built["rows"]), probs), key=lambda p: p[0])
    low = [p for _, p in pairs[:200]]
    high = [p for _, p in pairs[-200:]]
    assert sum(high) / len(high) > sum(low) / len(low) + 0.05


def test_size_is_monotone_capped_and_floored() -> None:
    """Sizes never decrease with p_correct, respect the cap, and stand down below the floor."""
    grid = [0.50, 0.54, DEFAULT_FLOOR, 0.60, 0.70, 0.80, 0.99]
    sizes = [size_from_meta(p) for p in grid]
    assert sizes == sorted(sizes)
    assert size_from_meta(0.50) == 0.0
    assert size_from_meta(DEFAULT_FLOOR - 1e-9) == 0.0
    assert size_from_meta(DEFAULT_FLOOR) > 0.0
    assert max(sizes) <= 0.25
    assert size_from_meta(0.99, kelly_cap=0.10) == 0.10
    assert abs(size_from_meta(0.60, kelly_cap=1.0) - 0.20) < 1e-9


def test_thin_ledger_returns_insufficient_everywhere(tmp_path: Path) -> None:
    """Under MIN_LABELED_ROWS nothing trains -- every entry point says so honestly."""
    ledger = tmp_path / "thin.jsonl"
    _write_ledger(ledger, 50)
    built = build_training_rows(ledger)
    report = ledger_report(ledger)
    fitted = fit_meta(built)
    for obj in (built, report, fitted):
        assert obj["status"] == "INSUFFICIENT"
        assert obj["rows_needed"] == MIN_LABELED_ROWS - 50
    assert "model" not in fitted
    assert predict_p_correct(fitted, built) is fitted
    assert size_from_meta(fitted) == 0.0
    assert report["by_strategy"]["pregame"]["n_labeled"] == 25


def test_report_counts_unsettled_and_bad_lines(tmp_path: Path) -> None:
    """Void/pending outcomes stay unlabeled; malformed lines are skipped, not fatal."""
    ledger = tmp_path / "mixed.jsonl"
    rows = [
        {"ts": "2026-02-01T12:00:00+00:00", "market": "a", "side": "home",
         "prob_at_entry": 0.6, "market_price_at_entry": 0.5, "size_units": 1.0,
         "strategy": "pregame", "outcome": "home"},
        {"ts": "2026-02-01T13:00:00+00:00", "market": "b", "side": "away",
         "prob_at_entry": 0.4, "market_price_at_entry": 0.5, "size_units": 1.0,
         "strategy": "pregame", "outcome": "push"},
        {"ts": "2026-02-01T14:00:00+00:00", "market": "c", "side": "home",
         "prob_at_entry": None, "market_price_at_entry": 0.5, "strategy": "pregame"},
    ]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot-json\n", encoding="utf-8")
    report = ledger_report(ledger)
    assert report["n_records"] == 2  # the None-prob row and the junk line are dropped
    assert report["n_labeled"] == 1
    assert report["n_unsettled"] == 1
    assert report["hit_rate"] == 1.0
    assert report["status"] == "INSUFFICIENT"
