"""Per-file tests for the CLV-honesty fix: settlement/expiry times must NOT act as
tip-off anchors that let a near-final in-play price be labeled is_true_close=True.

Covers:
  * kalshi.parse_events    -- commence_time is None (never close_time=settlement)
  * polymarket.parse_market -- commence_time is None when only endDate present
  * end-to-end via line_snapshot_daemon + line_store:
      - Kalshi-only game: near-settlement quote -> clv_is_proxy (is_true_close=False)
      - ESPN-anchored game: near-tip quote -> is_true_close=True (unchanged)

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_clv_honesty.py -q
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.platformkit.odds_provider.kalshi import parse_events
from scripts.platformkit.odds_provider.polymarket import parse_market
from scripts.platformkit.odds_provider import line_snapshot_daemon as daemon
from scripts.platformkit.odds_provider import line_store


# ---------------------------------------------------------------------------
# Unit: kalshi.parse_events -- close_time must NOT become commence_time
# ---------------------------------------------------------------------------

def _kalshi_two_leg(settlement_iso: str) -> list:
    """Minimal two-leg Kalshi event with a close_time (settlement bound)."""
    return [
        {
            "event_ticker": "KXNBA-GAME1",
            "yes_sub_title": "Knicks",
            "yes_ask_dollars": 0.52,
            "close_time": settlement_iso,
        },
        {
            "event_ticker": "KXNBA-GAME1",
            "yes_sub_title": "Spurs",
            "yes_ask_dollars": 0.48,
            "close_time": settlement_iso,
        },
    ]


def test_kalshi_commence_time_is_none_not_settlement():
    """kalshi.parse_events must NOT put close_time into OddsEvent.commence_time."""
    settlement = "2026-06-18T06:00:00+00:00"  # post-game settlement stamp
    events = parse_events(_kalshi_two_leg(settlement), "nba")
    assert len(events) == 1
    ev = events[0]
    # Before fix: ev.commence_time == settlement (inflates CLV).
    # After fix: ev.commence_time must be None.
    assert ev.commence_time is None, (
        "Kalshi OddsEvent.commence_time must be None, got %r "
        "(close_time is a settlement stamp, not tip-off)" % ev.commence_time
    )


# ---------------------------------------------------------------------------
# Unit: polymarket.parse_market -- endDate fallback must NOT become commence_time
# ---------------------------------------------------------------------------

def _pm_market(*, start_date=None, end_date=None) -> dict:
    """Minimal two-outcome Polymarket gamma market with configurable dates."""
    return {
        "id": "pm-game1",
        "outcomes": '["Knicks", "Spurs"]',
        "outcomePrices": '["0.54", "0.46"]',
        "startDate": start_date,
        "endDate": end_date,
    }


def test_polymarket_commence_time_from_start_date():
    """startDate (the real game start) is used as commence_time."""
    ev = parse_market(_pm_market(start_date="2026-06-18T23:00:00Z"), "nba")
    assert ev is not None
    assert ev.commence_time == "2026-06-18T23:00:00Z"


def test_polymarket_enddate_fallback_does_not_become_commence_time():
    """When startDate is absent, endDate (resolution date) must NOT become commence_time.

    Before fix: commence_time = endDate (resolution/settlement -> inflates CLV).
    After fix:  commence_time = None (proxy, correctly).
    """
    resolution = "2026-06-19T05:00:00Z"
    ev = parse_market(_pm_market(start_date=None, end_date=resolution), "nba")
    assert ev is not None
    assert ev.commence_time is None, (
        "Polymarket OddsEvent.commence_time must be None when only endDate is present, "
        "got %r (endDate is a resolution/settlement stamp, not tip-off)" % ev.commence_time
    )


def test_polymarket_null_start_null_end_commence_none():
    """Both dates absent -> commence_time=None (no tip-off info available)."""
    ev = parse_market(_pm_market(), "nba")
    assert ev is not None
    assert ev.commence_time is None


# ---------------------------------------------------------------------------
# End-to-end: Kalshi-only game -> must be clv_is_proxy even near settlement
# ---------------------------------------------------------------------------

def _kalshi_only_agg(as_of_iso: str, settlement_iso: str) -> dict:
    """Aggregate payload where ONLY a Kalshi venue is present (no ESPN/real tip).

    Simulates a game known only via Kalshi: commence_time in the event comes from
    Kalshi's close_time (before the fix it was set; after the fix it is None).
    """
    return {
        "sport": "nba", "status": "ok", "as_of": as_of_iso,
        "sources": {"kalshi": "ok"},
        "events": [{
            "event_id": "KXNBA-GAME1",
            "sport": "nba", "home": "Knicks", "away": "Spurs",
            # After fix: commence_time is None (Kalshi's close_time was never a tip).
            "commence_time": None,
            "as_of": as_of_iso,
            "prices": {"kalshi": {"home": 1.92, "away": 2.04}},
        }],
    }


def test_kalshi_only_near_settlement_is_proxy(tmp_path):
    """A near-settlement Kalshi quote must be clv_is_proxy (is_true_close=False).

    Scenario: settlement is at T, we capture a tick at T-15min (inside 30-min window
    if settlement were the tip). After the fix, commence_time=None -> the quote is
    never 'at lock' -> get_close returns is_true_close=False (proxy).

    Before the fix: commence_time = settlement -> _within_lock returns True ->
    is_true_close=True (WRONG: we falsely labeled a near-final in-play price a close).
    """
    settlement = datetime(2026, 6, 18, 6, 0, tzinfo=timezone.utc)  # post-game
    # Capture at 15 minutes before settlement (would satisfy the 30-min window).
    capture_time = settlement - timedelta(minutes=15)
    capture_iso = capture_time.isoformat(timespec="seconds")
    settlement_iso = settlement.isoformat(timespec="seconds")

    daemon.serve_forever(
        sports=["nba"],
        clock=lambda: capture_time,
        sleep=lambda _s: None,
        max_ticks=1,
        out_dir=tmp_path,
        agg_fn=lambda sport, **kw: _kalshi_only_agg(capture_iso, settlement_iso),
    )

    result = line_store.get_close("KXNBA-GAME1", base=tmp_path)
    assert result is not None, "No history written -- check agg/write path"
    closes, is_true_close = result
    # This is the key assertion: a Kalshi-only game must NEVER get is_true_close=True
    # from a settlement-derived window.
    assert is_true_close is False, (
        "Kalshi-only game incorrectly labeled is_true_close=True "
        "(settlement time used as tip-off anchor -- CLV would be inflated)"
    )
    # But the proxy close itself must still be returned (we degrade, not erase).
    assert len(closes) > 0, "Proxy close should still be returned (last-observed)"


# ---------------------------------------------------------------------------
# End-to-end: ESPN-anchored game -> true-close still works (no regression)
# ---------------------------------------------------------------------------

def _espn_anchored_agg(as_of_iso: str, tip_iso: str) -> dict:
    """Aggregate payload with a REAL tip-off time (as ESPN provides)."""
    return {
        "sport": "nba", "status": "ok", "as_of": as_of_iso,
        "sources": {"espn": "ok"},
        "events": [{
            "event_id": "ESPN-G1",
            "sport": "nba", "home": "Knicks", "away": "Spurs",
            "commence_time": tip_iso,  # real tip-off from ESPN ev.date
            "as_of": as_of_iso,
            "prices": {
                "espn:DraftKings": {"home": 1.91, "away": 2.05},
            },
        }],
    }


def test_espn_anchored_true_close_unchanged(tmp_path):
    """An ESPN-anchored game's true-close still works after the fix.

    A tick captured within 30 min before the real tip-off must still be labeled
    is_true_close=True. The fix must not regress this path.
    """
    tip = datetime(2026, 6, 18, 23, 0, tzinfo=timezone.utc)
    near_tip = tip - timedelta(minutes=10)
    tip_iso = tip.isoformat(timespec="seconds")

    daemon.serve_forever(
        sports=["nba"],
        clock=lambda: near_tip,
        sleep=lambda _s: None,
        max_ticks=1,
        out_dir=tmp_path,
        agg_fn=lambda sport, **kw: _espn_anchored_agg(
            near_tip.isoformat(timespec="seconds"), tip_iso),
    )

    result = line_store.get_close("ESPN-G1", base=tmp_path)
    assert result is not None
    closes, is_true_close = result
    assert is_true_close is True, (
        "ESPN-anchored game should still get is_true_close=True for a near-tip quote"
    )
    assert ("moneyline", "home") in closes
