"""
tests/test_alt_line_ladder.py — Phase 15.5 Wave 0: xfail stubs for alt_line_ladder.py.

Tests 1-4 are xfail until Plan 02 creates src/prediction/alt_line_ladder.py.
Test 5 verifies conformal_props.py (already exists) works correctly.
"""
from __future__ import annotations
import math
import numpy as np
import pytest

# ── Test 5 (no xfail): conformal_props.py already exists ──────────────────────

def test_conformal_load_and_predict():
    """ConformalPredictor calibrates and predicts valid intervals."""
    from src.prediction.conformal_props import ConformalPredictor
    rng = np.random.default_rng(42)
    y_true = rng.normal(20.0, 3.0, 80)
    y_hat = y_true + rng.normal(0, 1.5, 80)
    cp = ConformalPredictor()
    cp.calibrate(y_true, y_hat)
    lo, hi = cp.predict_interval(22.5, coverage=0.80)
    assert lo < 22.5 < hi, f"Interval {lo}..{hi} must straddle point estimate 22.5"
    assert hi - lo > 0, "Interval width must be positive"

# ── Tests 1-4: xfail until alt_line_ladder.py is created ──────────────────────

@pytest.mark.xfail(reason="alt_line_ladder not yet built — Plan 02", strict=False)
def test_ladder_offsets():
    """build_alt_line_ladder returns 22 entries: 11 offsets × 2 directions."""
    from src.prediction.alt_line_ladder import build_alt_line_ladder
    result = build_alt_line_ladder(
        player="LeBron James",
        stat="pts",
        point_estimate=26.5,
        conformal_interval=(22.0, 31.0),
        pinnacle_signal={"line": 26.5, "over_odds": -110, "under_odds": -110},
    )
    assert isinstance(result, list), "Result must be a list"
    assert len(result) >= 22, f"Expected >= 22 entries (11 offsets × 2), got {len(result)}"
    directions = {r["direction"] for r in result}
    assert "over" in directions and "under" in directions
    alt_lines = sorted({r["alt_line"] for r in result})
    assert len(alt_lines) == 11, f"Expected 11 distinct alt lines, got {len(alt_lines)}"


@pytest.mark.xfail(reason="alt_line_ladder not yet built — Plan 02", strict=False)
def test_ev_computation():
    """EV = model_prob / book_prob - 1. With model=0.60, book=0.50 → EV ≈ 0.20."""
    from src.prediction.alt_line_ladder import _compute_ev
    ev = _compute_ev(model_prob=0.60, book_prob=0.50)
    assert abs(ev - 0.20) < 0.01, f"EV should be ~0.20, got {ev}"


@pytest.mark.xfail(reason="alt_line_ladder not yet built — Plan 02", strict=False)
def test_pinnacle_decay():
    """Book probability decays for wider alt lines (Pinnacle vig structure)."""
    from src.prediction.alt_line_ladder import build_alt_line_ladder
    result = build_alt_line_ladder(
        player="Jayson Tatum",
        stat="pts",
        point_estimate=28.0,
        conformal_interval=(23.5, 32.5),
        pinnacle_signal={"line": 28.0, "over_odds": -110, "under_odds": -110},
    )
    # At offset 0.0 (main line) and offset +2.0 (alt line), over prob should decay
    by_alt = {(r["alt_line"], r["direction"]): r for r in result}
    main_over = by_alt.get((28.0, "over"), {}).get("book_prob", 0.50)
    wide_over = by_alt.get((30.0, "over"), {}).get("book_prob", 0.50)
    assert wide_over < main_over, (
        f"book_prob at +2.0 ({wide_over}) should be < book_prob at 0.0 ({main_over})"
    )


@pytest.mark.xfail(reason="alt_line_ladder not yet built — Plan 02", strict=False)
def test_kelly_cap():
    """kelly_raw must never exceed 0.02 (2% of bankroll cap) for any ladder entry."""
    from src.prediction.alt_line_ladder import build_alt_line_ladder
    result = build_alt_line_ladder(
        player="Stephen Curry",
        stat="fg3m",
        point_estimate=4.5,
        conformal_interval=(2.0, 7.0),
        pinnacle_signal={"line": 4.5, "over_odds": -115, "under_odds": -105},
    )
    for row in result:
        kelly = row.get("kelly_raw", 0.0)
        assert kelly <= 0.02, f"Kelly {kelly} exceeds 2% cap at alt_line={row.get('alt_line')}"
        assert kelly >= 0.0, f"Kelly must be non-negative, got {kelly}"
