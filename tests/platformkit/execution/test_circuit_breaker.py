"""Per-file tests for scripts.platformkit.execution.circuit_breaker.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/execution/test_circuit_breaker.py -q
"""
from __future__ import annotations

from scripts.platformkit.execution import circuit_breaker as cb
from scripts.platformkit.execution.thresholds import BREAKER_CAPPED_MAX_PER_DAY

NOW = "2026-07-15T12:00:00Z"


def _row(market_type, ts, clv_pct=None, proxy=False):
    r = {"market_type": market_type, "ts": ts}
    if clv_pct is not None:
        r["clv_pct"] = clv_pct
    if proxy:
        r["clv_is_proxy"] = True
    return r


def test_rolling_clv_means_only_graded_rows_in_window():
    rows = [
        _row("win_home", "2026-07-10T00:00:00Z", clv_pct=10.0),
        _row("win_home", "2026-07-12T00:00:00Z", clv_pct=-2.0, proxy=True),
        _row("win_home", "2026-05-01T00:00:00Z", clv_pct=99.0),  # outside window
        _row("win_home", "2026-07-11T00:00:00Z"),  # ungraded -- skipped
        _row("win_away", "2026-07-11T00:00:00Z", clv_pct=5.0),  # different market
    ]
    out = cb.rolling_clv(rows, "win_home", NOW)
    assert out["n"] == 2
    assert out["n_proxy"] == 1
    assert abs(out["mean_clv_pct"] - 4.0) < 1e-9


def test_rolling_clv_no_data_returns_none():
    out = cb.rolling_clv([], "win_home", NOW)
    assert out["mean_clv_pct"] is None and out["n"] == 0


def test_state_live_when_mean_positive():
    rows = [_row("win_home", "2026-07-10T00:00:00Z", clv_pct=3.0)]
    st = cb.state(rows, "win_home", NOW)
    assert st["state"] == "LIVE"
    assert st["cap_per_day"] is None


def test_state_capped_when_mean_negative():
    rows = [_row("win_home", "2026-07-10T00:00:00Z", clv_pct=-3.0)]
    st = cb.state(rows, "win_home", NOW)
    assert st["state"] == "CAPPED"
    assert st["cap_per_day"] == BREAKER_CAPPED_MAX_PER_DAY


def test_state_capped_when_no_data():
    st = cb.state([], "win_home", NOW)
    assert st["state"] == "CAPPED"
    assert st["cap_per_day"] == BREAKER_CAPPED_MAX_PER_DAY


def test_allow_placement_live_always_allowed():
    rows = [_row("win_home", "2026-07-10T00:00:00Z", clv_pct=3.0)]
    out = cb.allow_placement(rows, "win_home", NOW)
    assert out["allowed"] is True and out["state"] == "LIVE"


def test_allow_placement_capped_respects_daily_cap():
    rows = [_row("win_home", "2026-07-10T00:00:00Z", clv_pct=-3.0)]
    # placed_today starts at 0 for this market (no rows dated today yet)
    out = cb.allow_placement(rows, "win_home", NOW)
    assert out["allowed"] is True and out["state"] == "CAPPED" and out["placed_today"] == 0
    # add BREAKER_CAPPED_MAX_PER_DAY rows dated today -> next placement is blocked
    today_rows = rows + [
        _row("win_home", "2026-07-15T0%d:00:00Z" % i, clv_pct=-1.0)
        for i in range(BREAKER_CAPPED_MAX_PER_DAY)
    ]
    out2 = cb.allow_placement(today_rows, "win_home", NOW)
    assert out2["placed_today"] == BREAKER_CAPPED_MAX_PER_DAY
    assert out2["allowed"] is False
    assert out2["reason"] == "cap_reached"
