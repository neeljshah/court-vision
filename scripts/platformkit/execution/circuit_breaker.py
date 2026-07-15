"""scripts.platformkit.execution.circuit_breaker -- rolling-CLV volume breaker.

Volume follows MEASURED CLV, never confidence. When the rolling window's mean CLV
is negative (or there is no graded data yet), the channel is CAPPED to a small
daily placement count instead of cut off outright -- honest measurement continues
at low volume rather than freezing blind. Pure dict-in/dict-out; no file IO.

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


def rolling_clv(rows: List[Dict[str, Any]], market_type: str, now_iso: str,
                 window_days: int = BREAKER_WINDOW_DAYS) -> Dict[str, Any]:
    """Mean CLV for *market_type* over the trailing *window_days* ending at now_iso.

    Rows without a graded clv_pct/clv are skipped (not yet settled). Proxy-close
    rows (clv_is_proxy=True) are INCLUDED in the mean but counted separately as
    n_proxy so a caller can judge data quality without discarding the rows.
    """
    now = _parse_ts(now_iso) or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    vals: List[float] = []
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
        clv = row.get("clv_pct")
        if clv is None:
            clv = row.get("clv")
        if clv is None:
            continue  # not graded yet -- skip, never fabricate
        try:
            vals.append(float(clv))
        except (TypeError, ValueError):
            continue
        if row.get("clv_is_proxy") is True:
            n_proxy += 1
    if not vals:
        return {"mean_clv_pct": None, "n": 0, "n_proxy": n_proxy}
    return {"mean_clv_pct": sum(vals) / len(vals), "n": len(vals), "n_proxy": n_proxy}


def state(rows: List[Dict[str, Any]], market_type: str, now_iso: str) -> Dict[str, Any]:
    """LIVE (uncapped) unless rolling CLV is None (no data) or negative -> CAPPED."""
    roll = rolling_clv(rows, market_type, now_iso)
    mean = roll["mean_clv_pct"]
    capped = mean is None or mean < 0.0
    return {
        "state": "CAPPED" if capped else "LIVE",
        "mean_clv_pct": mean, "n": roll["n"],
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
