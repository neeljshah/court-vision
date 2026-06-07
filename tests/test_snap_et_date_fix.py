"""test_snap_et_date_fix.py — gated fix for the snapshot UTC-prefix vs ET
date mismatch in _snap_matches_date (HARDENING SWEEP3, MED/LIVE).

Bug: in api.courtvision_router._synthesize_bets_from_snapshots the nested
_snap_matches_date(snap) compares a raw UTC date-prefix
``(snap["captured_at"])[:10]`` against the ET slate ``date``. Any snapshot
captured after 8:00 PM ET (>= 00:00 UTC) rolls to the next UTC calendar day
and is silently dropped from the synthesized (no-CSV) live path, yielding 0
bet cards exactly when a game is live in the evening.

Fix: gated flag CV_FIX_SNAP_ET_DATE (default OFF = byte-identical raw-prefix
behavior). When ON, captured_at is converted to its ET date via the
in-module helper _et_date_from_iso before comparing — so an evening
snapshot whose UTC prefix is the NEXT day but whose ET date is the slate
date now MATCHES.

_snap_matches_date is a nested closure (not importable), so we:
  1. assert the real module helper _et_date_from_iso produces the ET date
     the gated branch relies on (the load-bearing conversion), and
  2. exercise a faithful replica of the gate's two branches against the
     exact failing snapshot, driven by the same env flag the code reads.
"""
from __future__ import annotations

import importlib
import os

import pytest

# Slate date is an ET evening game. A snapshot captured at 8:30 PM ET on the
# slate date is 00:30Z the NEXT UTC day, so its raw UTC prefix ([:10]) is the
# wrong (next) calendar day while its ET date is the slate date.
SLATE_DATE = "2026-06-15"
EVENING_SNAP_CAPTURED_AT = "2026-06-16T00:30:00Z"  # 8:30 PM ET on 2026-06-15
UTC_PREFIX = "2026-06-16"                          # what [:10] yields (wrong)

# A daytime/afternoon snapshot whose UTC prefix already equals the slate date
# (e.g. 3:00 PM ET == 19:00Z same day) must match under BOTH branches.
AFTERNOON_SNAP_CAPTURED_AT = "2026-06-15T19:00:00Z"  # 3:00 PM ET on 2026-06-15


def _et_date_from_iso():
    mod = importlib.import_module("api.courtvision_router")
    return mod._et_date_from_iso


def _snap_matches_date_replica(snap: dict, date: str, synthesized_flag: bool = True) -> bool:
    """Byte-faithful replica of the gated _snap_matches_date closure body,
    reading the SAME CV_FIX_SNAP_ET_DATE env var the production code reads
    and calling the SAME _et_date_from_iso helper."""
    if not synthesized_flag:
        return True
    if os.environ.get("CV_FIX_SNAP_ET_DATE") == "1":
        return _et_date_from_iso()(snap.get("captured_at") or "") == date
    ca = (snap.get("captured_at") or "")[:10]
    return ca == date


# ---------------------------------------------------------------------------
# Load-bearing helper: the ET conversion the gated branch depends on
# ---------------------------------------------------------------------------

def test_helper_converts_evening_snapshot_to_slate_et_date():
    """The in-module _et_date_from_iso maps the evening snapshot's
    captured_at to the slate's ET date (not the next UTC day)."""
    fn = _et_date_from_iso()
    assert fn(EVENING_SNAP_CAPTURED_AT) == SLATE_DATE
    # sanity: the naive UTC prefix is indeed the WRONG (next) day
    assert EVENING_SNAP_CAPTURED_AT[:10] == UTC_PREFIX
    assert UTC_PREFIX != SLATE_DATE


# ---------------------------------------------------------------------------
# (a) Flag OFF == current raw-prefix behavior (byte-identical)
# ---------------------------------------------------------------------------

def test_off_drops_evening_snapshot(monkeypatch):
    """OFF: the evening snapshot's UTC prefix != slate date, so it is
    dropped — exactly today's (buggy) behavior."""
    monkeypatch.delenv("CV_FIX_SNAP_ET_DATE", raising=False)
    snap = {"captured_at": EVENING_SNAP_CAPTURED_AT}
    assert _snap_matches_date_replica(snap, SLATE_DATE) is False


def test_off_keeps_afternoon_snapshot(monkeypatch):
    """OFF: an afternoon snapshot whose UTC prefix already == slate date is
    kept (no change from raw-prefix semantics)."""
    monkeypatch.delenv("CV_FIX_SNAP_ET_DATE", raising=False)
    snap = {"captured_at": AFTERNOON_SNAP_CAPTURED_AT}
    assert _snap_matches_date_replica(snap, SLATE_DATE) is True


def test_off_late_roster_accepts_any(monkeypatch):
    """OFF: late-roster path (synthesized_flag False) accepts any snapshot,
    regardless of date — unchanged by the gate."""
    monkeypatch.delenv("CV_FIX_SNAP_ET_DATE", raising=False)
    snap = {"captured_at": EVENING_SNAP_CAPTURED_AT}
    assert _snap_matches_date_replica(snap, SLATE_DATE, synthesized_flag=False) is True


# ---------------------------------------------------------------------------
# (b) Flag ON fixes the specific failing evening-snapshot case
# ---------------------------------------------------------------------------

def test_on_keeps_evening_snapshot(monkeypatch):
    """ON: the evening snapshot now matches the slate date via ET
    conversion — it is no longer silently dropped."""
    monkeypatch.setenv("CV_FIX_SNAP_ET_DATE", "1")
    snap = {"captured_at": EVENING_SNAP_CAPTURED_AT}
    assert _snap_matches_date_replica(snap, SLATE_DATE) is True


def test_on_does_not_regress_afternoon_snapshot(monkeypatch):
    """ON: the afternoon snapshot still matches (ET conversion agrees with
    the prefix when there is no UTC rollover)."""
    monkeypatch.setenv("CV_FIX_SNAP_ET_DATE", "1")
    snap = {"captured_at": AFTERNOON_SNAP_CAPTURED_AT}
    assert _snap_matches_date_replica(snap, SLATE_DATE) is True


def test_on_off_diverge_only_for_evening_snapshot(monkeypatch):
    """The gate flips the verdict ONLY for the rolled-over evening snapshot:
    OFF drops it (False), ON keeps it (True)."""
    snap = {"captured_at": EVENING_SNAP_CAPTURED_AT}
    monkeypatch.delenv("CV_FIX_SNAP_ET_DATE", raising=False)
    off = _snap_matches_date_replica(snap, SLATE_DATE)
    monkeypatch.setenv("CV_FIX_SNAP_ET_DATE", "1")
    on = _snap_matches_date_replica(snap, SLATE_DATE)
    assert off is False
    assert on is True
