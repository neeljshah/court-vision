"""test_dk_timeparse_fix.py — gated fix for the DraftKings 7-digit
fractional-seconds ET-date parse failure (HARDENING SWEEP3, HIGH/LIVE).

Bug: DraftKings start_times carry 7 fractional-second digits
('...:00.0000000Z') which datetime.fromisoformat() rejects in py3.10,
so the parser swallows the ValueError and falls back to the raw UTC
prefix iso_ts[:10]. For night games (UTC date == next calendar day) this
buckets DK props onto the WRONG ET day and they vanish from /tonight.

Fix: gated flag CV_DK_FRACSEC_FIX (default OFF). When ON, fractional
seconds are truncated to <=6 digits before strptime, so the timestamp
parses to the correct ET date. When OFF the behavior is byte-identical
to before (falls back to the UTC prefix for the DK string).

The identical helper lives in TWO modules:
    api._courtvision_odds._et_date_of_start_time
    api.courtvision_router._et_date_from_iso
Both are exercised here.
"""
from __future__ import annotations

import importlib

import pytest

# The offending real-world DK timestamp: a 7:30 PM ET tipoff stored in UTC
# (== 23:30Z same day for EDT) with 7 fractional-second digits. We use a
# night game whose UTC date rolls past midnight to make the ET-vs-UTC date
# split observable: 8:30 PM ET on 2026-06-15 == 00:30Z on 2026-06-16.
DK_FRACSEC_TS = "2026-06-16T00:30:00.0000000Z"  # 8:30 PM ET on 2026-06-15
EXPECTED_ET_DATE = "2026-06-15"   # correct ET calendar date
UTC_PREFIX_DATE = "2026-06-16"    # what the buggy fallback returns

# Inputs with 0 / 3 / 6 fractional digits and no-frac must be unaffected by
# the truncation regex (it only strips a 7th+ digit).
FD_FRACSEC_TS = "2026-06-16T00:30:00.000Z"   # 3-digit (FanDuel style)
NOFRAC_TS = "2026-06-16T00:30:00Z"           # no fractional seconds


def _odds_helper():
    mod = importlib.import_module("api._courtvision_odds")
    return mod._et_date_of_start_time


def _router_helper():
    mod = importlib.import_module("api.courtvision_router")
    return mod._et_date_from_iso


# ---------------------------------------------------------------------------
# (a) Flag OFF == current (byte-identical) behavior
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("helper", [_odds_helper, _router_helper])
def test_off_is_unchanged_for_dk_fracsec(monkeypatch, helper):
    """OFF: the 7-digit DK timestamp still fails fromisoformat and falls
    back to the raw UTC prefix — exactly today's (buggy) behavior."""
    monkeypatch.delenv("CV_DK_FRACSEC_FIX", raising=False)
    fn = helper()
    assert fn(DK_FRACSEC_TS) == UTC_PREFIX_DATE  # buggy fallback preserved


@pytest.mark.parametrize("helper", [_odds_helper, _router_helper])
@pytest.mark.parametrize("ts,expected", [
    (FD_FRACSEC_TS, EXPECTED_ET_DATE),   # 3-digit already parses fine
    (NOFRAC_TS, EXPECTED_ET_DATE),       # no-frac already parses fine
])
def test_off_unchanged_for_parsable_inputs(monkeypatch, helper, ts, expected):
    """OFF: inputs that already parse (0/3-digit frac) are unaffected and
    yield the correct ET date both before and after the gate exists."""
    monkeypatch.delenv("CV_DK_FRACSEC_FIX", raising=False)
    fn = helper()
    assert fn(ts) == expected


@pytest.mark.parametrize("helper", [_odds_helper, _router_helper])
@pytest.mark.parametrize("ts,expected", [
    (FD_FRACSEC_TS, EXPECTED_ET_DATE),
    (NOFRAC_TS, EXPECTED_ET_DATE),
])
def test_on_does_not_regress_parsable_inputs(monkeypatch, helper, ts, expected):
    """ON must be harmless for 0/3/6-digit inputs — same ET date as OFF."""
    monkeypatch.setenv("CV_DK_FRACSEC_FIX", "1")
    fn = helper()
    assert fn(ts) == expected


# ---------------------------------------------------------------------------
# (b) Flag ON fixes the specific failing DK case
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("helper", [_odds_helper, _router_helper])
def test_on_fixes_dk_fracsec(monkeypatch, helper):
    """ON: the 7-digit DK timestamp now parses to the correct ET date
    (the night game stays on the slate's ET day, not the next UTC day)."""
    monkeypatch.setenv("CV_DK_FRACSEC_FIX", "1")
    fn = helper()
    assert fn(DK_FRACSEC_TS) == EXPECTED_ET_DATE


@pytest.mark.parametrize("helper", [_odds_helper, _router_helper])
def test_on_off_diverge_only_for_dk_case(monkeypatch, helper):
    """The gate changes output ONLY for the previously-unparsable DK input:
    OFF -> wrong UTC-prefix date, ON -> correct ET date."""
    fn = helper()
    monkeypatch.delenv("CV_DK_FRACSEC_FIX", raising=False)
    off = fn(DK_FRACSEC_TS)
    monkeypatch.setenv("CV_DK_FRACSEC_FIX", "1")
    on = fn(DK_FRACSEC_TS)
    assert off == UTC_PREFIX_DATE
    assert on == EXPECTED_ET_DATE
    assert off != on
