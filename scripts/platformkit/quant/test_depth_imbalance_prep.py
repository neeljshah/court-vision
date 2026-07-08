"""Smallest-useful check for depth_imbalance_prep.py: imbalance/bid_heavy
math on a synthetic 2-row micro-corpus, no real I/O.

Run: python -m pytest scripts/platformkit/quant/test_depth_imbalance_prep.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.quant.depth_imbalance_prep import _prep_sport


def test_imbalance_and_bid_heavy_and_obs_id_unique(monkeypatch) -> None:
    rows = [
        {"sport": "unit_test_sport", "ticker": "T1", "ts": "2026-01-01T00:00:00Z",
         "depth_totals": {"yes_bid_total": 300.0, "yes_ask_total": 100.0}},  # bid-heavy
        {"sport": "unit_test_sport", "ticker": "T2", "ts": "2026-01-01T00:00:00Z",
         "depth_totals": {"yes_bid_total": 100.0, "yes_ask_total": 300.0}},  # ask-heavy
        {"sport": "unit_test_sport", "ticker": "T3", "ts": "2026-01-01T00:00:00Z",
         "depth_totals": {"yes_bid_total": 0.0, "yes_ask_total": 0.0}},  # dropped: denom==0
    ]
    df = pd.DataFrame(rows)
    monkeypatch.setattr(
        "scripts.platformkit.quant.depth_imbalance_prep._load_sport_raw",
        lambda sport: df,
    )
    out = _prep_sport("unit_test_sport").set_index("ticker")

    assert len(out) == 2  # T3 dropped (zero-depth denom)
    assert out.loc["T1", "imbalance"] == pytest.approx(0.5)
    assert out.loc["T1", "bid_heavy_flag"] == 1
    assert out.loc["T2", "imbalance"] == pytest.approx(-0.5)
    assert out.loc["T2", "bid_heavy_flag"] == 0
    assert out.reset_index()["obs_id"].is_unique


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
