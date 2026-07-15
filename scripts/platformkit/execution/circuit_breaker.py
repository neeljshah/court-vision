"""scripts.platformkit.execution.circuit_breaker -- rolling-CLV volume breaker.

Volume follows MEASURED CLV, never confidence. When the rolling window's gating
statistic is negative (or there is no graded data yet), the channel is CAPPED to
a small daily placement count instead of cut off outright -- honest measurement
continues at low volume rather than freezing blind. Pure dict-in/dict-out; no
file IO.

PRE-REGISTERED DECISION (2026-07-15, made BEFORE any forward measurement --
see docs/research/execution-quality/moneyline_clv_mean_audit.md): the arithmetic
mean_clv_pct on real ledger data is a fat-right-tail artifact -- a handful of
collapsed longshot moneyline rows (clv_pct up to +2918) drag the mean to +25.9
while the true-close median sits at +1.87. state()/allow_placement therefore
gate on median_clv_pct (true-close rows preferred; falls back to all rows only
when zero true-close rows exist yet), NOT on the mean. mean_clv_pct is still
reported for context but winsorized at +/-50 so a single longshot cannot swing
it unbounded.

PAPER / UNITS only. No $ figure anywhere.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from scripts.platformkit.execution.thresholds import (
    BREAKER_CAPPED_MAX_PER_DAY, BREAKER_WINDOW_DAYS,
)


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _median(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0


def rolling_clv(rows: List[Dict[str, Any]], market_type: str, now_iso: str,
                 window_days: int = BREAKER_WINDOW_DAYS) -> Dict[str, Any]:
    """CLV stats for *market_type* over the trailing *window_days* ending at now_iso.

    Rows without a graded clv_pct/clv are skipped (not yet settled). Proxy-close
    rows (clv_is_proxy=True) are counted separately as n_proxy. Returns:
      - median_clv_pct: true-close rows only when any exist ("basis": "true_close"),
        else the all-rows median ("basis": "proxy_only"). This is the gating stat.
      - mean_clv_pct: arithmetic mean of all graded rows, winsorized at +/-50 pct
        so a single collapsed-longshot row cannot swing it unbounded
        ("mean_winsorized": True). Context only -- never gates.
    """
    now = _parse_ts(now_iso) or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    vals: List[float] = []
    is_proxy_flags: List[bool] = []
    n_proxy = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        mt = row.get("market_type") or row.get("market")
        if str(mt) != str(market_type):
            continue
        ts = _parse_ts(row.get("ts"))
        if ts is None or ts < cutoff or ts > now:
            continue
        if row.get("clv_status") == "suspect_close":
            continue  # degenerate close join (2026-07-15 audit) -- never gates
        clv = row.get("clv_pct")
        if clv is None:
            clv = row.get("clv")
        if clv is None:
            continue  # not graded yet -- skip, never fabricate
        try:
            clv = float(clv)
        except (TypeError, ValueError):
            continue
        is_proxy = row.get("clv_is_proxy") is True
        vals.append(clv)
        is_proxy_flags.append(is_proxy)
        if is_proxy:
            n_proxy += 1
    if not vals:
        return {"mean_clv_pct": None, "median_clv_pct": None, "n": 0,
                "n_proxy": n_proxy, "basis": None, "mean_winsorized": True}
    true_close_vals = [v for v, p in zip(vals, is_proxy_flags) if not p]
    if true_close_vals:
        median = _median(true_close_vals)
        basis = "true_close"
    else:
        median = _median(vals)
        basis = "proxy_only"
    winsorized = [max(-50.0, min(50.0, v)) for v in vals]
    mean = sum(winsorized) / len(winsorized)
    return {"mean_clv_pct": mean, "median_clv_pct": median, "n": len(vals),
            "n_proxy": n_proxy, "basis": basis, "mean_winsorized": True}


def state(rows: List[Dict[str, Any]], market_type: str, now_iso: str) -> Dict[str, Any]:
    """LIVE (uncapped) unless the gating median is None (no data) or negative -> CAPPED.

    Gates on median_clv_pct (true-close preferred), not the mean -- see the
    2026-07-15 pre-registered decision in the module docstring.
    """
    roll = rolling_clv(rows, market_type, now_iso)
    median = roll["median_clv_pct"]
    capped = median is None or median < 0.0
    return {
        "state": "CAPPED" if capped else "LIVE",
        "mean_clv_pct": roll["mean_clv_pct"], "median_clv_pct": median,
        "n": roll["n"], "n_proxy": roll["n_proxy"], "basis": roll["basis"],
        "cap_per_day": BREAKER_CAPPED_MAX_PER_DAY if capped else None,
    }


def allow_placement(rows: List[Dict[str, Any]], market_type: str, now_iso: str) -> Dict[str, Any]:
    """Whether one more placement for *market_type* is allowed right now.

    LIVE: always allowed. CAPPED: allowed only while today's placement count for
    this market_type is below cap_per_day (counts rows whose ts date matches
    now_iso's date, regardless of settled status -- a placement counts the moment
    it is recorded, not once graded).
    """
    st = state(rows, market_type, now_iso)
    now = _parse_ts(now_iso) or datetime.now(timezone.utc)
    today = now.date()
    placed_today = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        mt = row.get("market_type") or row.get("market")
        if str(mt) != str(market_type):
            continue
        ts = _parse_ts(row.get("ts"))
        if ts is not None and ts.date() == today:
            placed_today += 1
    if st["state"] == "LIVE":
        return {"allowed": True, "state": "LIVE", "placed_today": placed_today,
                "reason": "live"}
    cap = st["cap_per_day"] or 0
    allowed = placed_today < cap
    return {"allowed": allowed, "state": "CAPPED", "placed_today": placed_today,
            "reason": "under_cap" if allowed else "cap_reached"}


def _demo() -> None:
    """Smallest runnable self-check (assert-based); not a test framework."""
    now = "2026-07-15T12:00:00Z"
    rows = [
        {"market_type": "win_home", "ts": "2026-07-01T00:00:00Z", "clv_pct": -5.0},
        {"market_type": "win_home", "ts": "2026-07-10T00:00:00Z", "clv_pct": -3.0,
         "clv_is_proxy": True},
    ]
    roll = rolling_clv(rows, "win_home", now)
    assert roll["n"] == 2 and roll["n_proxy"] == 1
    assert roll["basis"] == "true_close" and roll["median_clv_pct"] == -5.0
    st = state(rows, "win_home", now)
    assert st["state"] == "CAPPED" and st["cap_per_day"] == BREAKER_CAPPED_MAX_PER_DAY
    empty_st = state([], "win_home", now)
    assert empty_st["state"] == "CAPPED"  # no data -> capped, not live
    allow = allow_placement(rows, "win_home", now)
    assert allow["allowed"] is True and allow["state"] == "CAPPED"
    print("circuit_breaker self-check OK")


if __name__ == "__main__":
    _demo()


__all__ = ["rolling_clv", "state", "allow_placement"]
