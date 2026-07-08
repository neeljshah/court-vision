"""Smallest-useful check for line_dynamics_prep.py: the drift/reversal/
longshot math on a synthetic 3-book, 2-market micro-corpus, no real I/O.

Run: python -m pytest scripts/platformkit/quant/test_line_dynamics_prep.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from scripts.platformkit.quant.line_dynamics_prep import _prep_sport


def _row(game_id, market_type, side, book, minutes_before_close, prob, commence):
    captured = commence - timedelta(minutes=minutes_before_close)
    return {
        "sport": "unit_test_sport", "game_id": game_id, "market_type": market_type,
        "side": side, "book": book, "devigged_prob": prob,
        "captured_at": captured.isoformat(), "commence_time": commence.isoformat(),
    }


def test_drift_and_reversal_and_longshot(monkeypatch) -> None:
    commence = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = [
        # game A: monotonic drift up over the last 60 min, no reversal
        _row("A", "moneyline", "home", "bookX", 60, 0.50, commence),
        _row("A", "moneyline", "home", "bookX", 30, 0.55, commence),
        _row("A", "moneyline", "home", "bookX", 5, 0.60, commence),
        # game B: reversal (up then down) within the 60-min window
        _row("B", "moneyline", "home", "bookX", 60, 0.10, commence),
        _row("B", "moneyline", "home", "bookX", 30, 0.20, commence),
        _row("B", "moneyline", "home", "bookX", 5, 0.05, commence),
    ]
    df = pd.DataFrame(rows)
    monkeypatch.setattr(
        "scripts.platformkit.quant.line_dynamics_prep._load_sport_raw",
        lambda sport: df,
    )
    out = _prep_sport("unit_test_sport").set_index("game_id")

    assert out.loc["A", "drift_60m"] == pytest.approx(0.10)
    assert out.loc["A", "reversal_flag"] == 0
    assert out.loc["A", "is_longshot_start"] == False  # noqa: E712 -- start prob 0.50

    assert out.loc["B", "reversal_flag"] == 1
    assert out.loc["B", "is_longshot_start"] == True  # noqa: E712 -- start prob 0.10 < 0.15
    assert out.loc["B", "longshot_down_flag"] == 1  # drifted 0.10 -> 0.05 (down)

    assert out["obs_id"].is_unique


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
