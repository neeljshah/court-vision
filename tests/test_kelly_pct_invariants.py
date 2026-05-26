"""R19_L2: Kelly fraction invariants.

Asserts (a) clamp_kelly_pct enforces [0, 0.25] across all input types and
(b) every kelly_pct value in data/pnl_ledger.csv lies in that band.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

import pytest

from src.prediction.betting_portfolio import KELLY_PCT_MAX, clamp_kelly_pct


def test_clamp_caps_high():
    assert clamp_kelly_pct(5.0) == KELLY_PCT_MAX
    assert clamp_kelly_pct(0.25001) == KELLY_PCT_MAX
    assert clamp_kelly_pct(99) == KELLY_PCT_MAX


def test_clamp_caps_low():
    assert clamp_kelly_pct(-0.1) == 0.0
    assert clamp_kelly_pct(-99) == 0.0


def test_clamp_passes_through_in_band():
    assert clamp_kelly_pct(0.0) == 0.0
    assert clamp_kelly_pct(0.05) == 0.05
    assert clamp_kelly_pct(KELLY_PCT_MAX) == KELLY_PCT_MAX


def test_clamp_handles_none_and_nan():
    assert clamp_kelly_pct(None) is None
    assert clamp_kelly_pct(float("nan")) is None
    assert clamp_kelly_pct("bad") is None


def test_pnl_ledger_invariant():
    ledger = Path("data/pnl_ledger.csv")
    if not ledger.exists():
        pytest.skip("data/pnl_ledger.csv absent")
    offscale = 0
    with ledger.open() as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            raw = row.get("kelly_pct", "")
            if raw == "" or raw is None:
                continue
            try:
                v = float(raw)
            except ValueError:
                continue
            if math.isnan(v):
                continue
            if v < 0.0 or v > KELLY_PCT_MAX:
                offscale += 1
    assert offscale == 0, f"{offscale} ledger rows have kelly_pct outside [0, {KELLY_PCT_MAX}]"
