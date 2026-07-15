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
    assert out["mean_winsorized"] is True
    # true-close rows exist (the 10.0 row) -> median uses true-close only
    assert out["basis"] == "true_close"
    assert out["median_clv_pct"] == 10.0


def test_rolling_clv_no_data_returns_none():
    out = cb.rolling_clv([], "win_home", NOW)
    assert out["mean_clv_pct"] is None and out["median_clv_pct"] is None
    assert out["n"] == 0 and out["basis"] is None


def test_rolling_clv_proxy_only_falls_back_to_all_rows_median():
    rows = [
        _row("win_home", "2026-07-10T00:00:00Z", clv_pct=-1.0, proxy=True),
        _row("win_home", "2026-07-11T00:00:00Z", clv_pct=3.0, proxy=True),
    ]
    out = cb.rolling_clv(rows, "win_home", NOW)
    assert out["basis"] == "proxy_only"
    assert out["median_clv_pct"] == 1.0  # median of [-1.0, 3.0], no true-close rows


def test_rolling_clv_mean_winsorized_but_median_stable_under_outlier():
    """A single collapsed-longshot row (clv_pct=+2918) must not swing the median,
    and the mean is clipped to +50 rather than exploding -- the audited artifact.
    """
    rows = [
        _row("moneyline", "2026-07-10T00:00:00Z", clv_pct=1.0),
        _row("moneyline", "2026-07-11T00:00:00Z", clv_pct=2.0),
        _row("moneyline", "2026-07-12T00:00:00Z", clv_pct=2918.0),  # the outlier row
    ]
    out = cb.rolling_clv(rows, "moneyline", NOW)
    assert out["median_clv_pct"] == 2.0  # unmoved by the outlier
    assert abs(out["mean_clv_pct"] - (1.0 + 2.0 + 50.0) / 3.0) < 1e-9  # winsorized at +50


def test_state_live_when_median_positive():
    rows = [_row("win_home", "2026-07-10T00:00:00Z", clv_pct=3.0)]
    st = cb.state(rows, "win_home", NOW)
    assert st["state"] == "LIVE"
    assert st["cap_per_day"] is None


def test_state_capped_when_median_negative():
    rows = [_row("win_home", "2026-07-10T00:00:00Z", clv_pct=-3.0)]
    st = cb.state(rows, "win_home", NOW)
    assert st["state"] == "CAPPED"
    assert st["cap_per_day"] == BREAKER_CAPPED_MAX_PER_DAY


def test_state_capped_when_no_data():
    st = cb.state([], "win_home", NOW)
    assert st["state"] == "CAPPED"
    assert st["cap_per_day"] == BREAKER_CAPPED_MAX_PER_DAY


def test_state_gates_on_median_not_mean_outlier_row():
    """The pre-registered fix: a longshot row inflates the mean to positive but
    the median stays negative -- state must follow the median (stay CAPPED).
    """
    rows = [
        _row("moneyline", "2026-07-10T00:00:00Z", clv_pct=-3.0),
        _row("moneyline", "2026-07-11T00:00:00Z", clv_pct=-2.0),
        _row("moneyline", "2026-07-12T00:00:00Z", clv_pct=500.0),  # outlier
    ]
    st = cb.state(rows, "moneyline", NOW)
    assert st["mean_clv_pct"] > 0  # mean (even winsorized) is dragged positive
    assert st["median_clv_pct"] < 0
    assert st["state"] == "CAPPED"  # gate follows the median, not the mean


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


def test_suspect_close_rows_never_enter_the_window():
    now = "2026-07-15T12:00:00Z"
    rows = [
        {"market_type": "moneyline", "ts": "2026-07-10T00:00:00Z", "clv_pct": 2.0},
        {"market_type": "moneyline", "ts": "2026-07-11T00:00:00Z",
         "clv_pct": 15928.6, "clv_status": "suspect_close"},
    ]
    roll = cb.rolling_clv(rows, "moneyline", now)
    assert roll["n"] == 1
    assert roll["median_clv_pct"] == 2.0
    assert roll["mean_clv_pct"] == 2.0
