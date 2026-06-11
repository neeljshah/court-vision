"""test_dk_timeparse_fix.py — gated fix for the DraftKings 7-digit
fractional-seconds ET-date parse failure (HARDENING SWEEP3, HIGH/LIVE).

Bug: DraftKings start_times carry 7 fractional-second digits
('...:00.0000000Z') which datetime.fromisoformat() rejects in py3.10,
so the parser swallows the ValueError and falls back to the raw UTC
prefix iso_ts[:10]. For night games (UTC date == next calendar day) this
buckets DK props onto the WRONG ET day and they vanish from /tonight.

Fix: flag CV_DK_FRACSEC_FIX. When ON, fractional seconds are truncated
to <=6 digits before strptime, so the timestamp parses to the correct
ET date. Round 2 flipped the DEFAULT in the odds module:

    api._courtvision_odds._et_date_of_start_time
        default ON  — env unset or "1" fixes the date; "0" opts out
        (restores the legacy UTC-prefix fallback).
    api.courtvision_router._et_date_from_iso
        default OFF — only "1" enables; unset keeps the legacy
        byte-identical fallback (NOT yet flipped by Round 2).

Both helpers are exercised here, each against its own default.
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
# (a) Default behavior — odds helper now defaults ON (Round 2); router
#     helper still defaults OFF (byte-identical legacy fallback)
# ---------------------------------------------------------------------------

def test_default_on_fixes_dk_fracsec_in_odds_helper(monkeypatch):
    """Round 2: env UNSET, the odds-module helper fixes the 7-digit DK
    timestamp by default — the night game lands on the correct ET day."""
    monkeypatch.delenv("CV_DK_FRACSEC_FIX", raising=False)
    fn = _odds_helper()
    assert fn(DK_FRACSEC_TS) == EXPECTED_ET_DATE


def test_explicit_zero_opts_odds_helper_out(monkeypatch):
    """CV_DK_FRACSEC_FIX=0 restores the legacy UTC-prefix fallback in the
    odds-module helper (the documented opt-out escape hatch)."""
    monkeypatch.setenv("CV_DK_FRACSEC_FIX", "0")
    fn = _odds_helper()
    assert fn(DK_FRACSEC_TS) == UTC_PREFIX_DATE


def test_router_helper_default_still_off(monkeypatch):
    """Router helper was NOT flipped by Round 2: env unset still falls back
    to the raw UTC prefix (legacy byte-identical behavior)."""
    monkeypatch.delenv("CV_DK_FRACSEC_FIX", raising=False)
    fn = _router_helper()
    assert fn(DK_FRACSEC_TS) == UTC_PREFIX_DATE


@pytest.mark.parametrize("helper", [_odds_helper, _router_helper])
@pytest.mark.parametrize("ts,expected", [
    (FD_FRACSEC_TS, EXPECTED_ET_DATE),   # 3-digit already parses fine
    (NOFRAC_TS, EXPECTED_ET_DATE),       # no-frac already parses fine
])
def test_default_env_unchanged_for_parsable_inputs(monkeypatch, helper, ts, expected):
    """Env unset: inputs that already parse (0/3-digit frac) are unaffected
    by either default and yield the correct ET date in both helpers."""
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


def test_odds_helper_on_off_diverge_only_for_dk_case(monkeypatch):
    """Odds helper: "0" -> legacy UTC-prefix date; unset and "1" both yield
    the correct ET date (default ON). The gate moves ONLY the DK input."""
    fn = _odds_helper()
    monkeypatch.setenv("CV_DK_FRACSEC_FIX", "0")
    off = fn(DK_FRACSEC_TS)
    monkeypatch.delenv("CV_DK_FRACSEC_FIX", raising=False)
    default = fn(DK_FRACSEC_TS)
    monkeypatch.setenv("CV_DK_FRACSEC_FIX", "1")
    on = fn(DK_FRACSEC_TS)
    assert off == UTC_PREFIX_DATE
    assert default == EXPECTED_ET_DATE
    assert on == EXPECTED_ET_DATE
    assert off != on


def test_router_helper_on_off_diverge_only_for_dk_case(monkeypatch):
    """Router helper: unset -> legacy UTC-prefix date (default OFF);
    "1" -> correct ET date."""
    fn = _router_helper()
    monkeypatch.delenv("CV_DK_FRACSEC_FIX", raising=False)
    off = fn(DK_FRACSEC_TS)
    monkeypatch.setenv("CV_DK_FRACSEC_FIX", "1")
    on = fn(DK_FRACSEC_TS)
    assert off == UTC_PREFIX_DATE
    assert on == EXPECTED_ET_DATE
    assert off != on
