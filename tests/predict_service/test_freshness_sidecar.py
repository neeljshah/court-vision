"""Per-file test: predict_service.freshness_sidecar -- STALE-never-green + rollup.

Covers the W3 ROBUSTNESS rail (BACKEND lane):
  * a FRESH sidecar (recent source_as_of) -> status='fresh', ok=True, stale=False
  * a STALE sidecar (old source_as_of) -> status='stale', ok=False, stale=True
        (a reachable-but-stale feed reads STALE, never green)
  * a MISSING sidecar (feed never came up) -> ok=False, NOT green
  * a FROZEN feed (present-but-empty last_source_ts) -> stale, NOT green
  * feed_rollup is MONOTONE-DOWN: any stale/missing child forces parent off green;
    a fresh child can NEVER lift a stale parent back to green
  * NEGATIVE CONTROL: a missing/stale child reading green would FAIL this test
    (proves the rollup check has teeth)
  * NO $ field anywhere

Run: python -m pytest tests/predict_service/test_freshness_sidecar.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from predict_service import freshness_sidecar as fs

_FORBIDDEN = ("roi", "pnl", "profit", "dollar", "bankroll", "usd")


def _iter_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _iter_keys(it)


def _assert_no_money(body) -> None:
    keys = {str(k).lower() for k in _iter_keys(body)}
    for tok in _FORBIDDEN:
        assert tok not in keys, "forbidden money key %r" % tok


def _write_sidecar(root, sport, payload):
    d = root / sport
    d.mkdir(parents=True, exist_ok=True)
    (d / "_freshness.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture()
def root(tmp_path, monkeypatch):
    monkeypatch.setenv(fs._SIDECAR_ROOT_ENV, str(tmp_path))
    return tmp_path


_NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)


def test_fresh_feed_reads_green(root):
    ts = (_NOW - timedelta(seconds=30)).isoformat()
    _write_sidecar(root, "nba", {"source_as_of": ts})
    v = fs.feed_status("nba", now=_NOW)
    assert v["status"] == "fresh" and v["ok"] is True and v["stale"] is False
    _assert_no_money(v)


def test_stale_feed_reads_stale_not_green(root):
    # reachable-but-stale: the sidecar parses fine, but the source ts is hours old.
    ts = (_NOW - timedelta(hours=6)).isoformat()
    _write_sidecar(root, "nba", {"source_as_of": ts})
    v = fs.feed_status("nba", now=_NOW)
    assert v["status"] == "stale"
    assert v["ok"] is False and v["stale"] is True  # STALE, never green


def test_missing_feed_not_green(root):
    v = fs.feed_status("mlb", now=_NOW)  # no sidecar written
    assert v["ok"] is False and v["stale"] is True


def test_frozen_feed_present_but_empty_is_stale(root):
    # an in-play poll off a frozen feed writes last_source_ts=None on purpose.
    _write_sidecar(root, "tennis", {"last_source_ts": None, "poll_at": _NOW.isoformat()})
    v = fs.feed_status("tennis", now=_NOW)
    assert v["ok"] is False  # must NOT fall through to the fresh poll wall-clock


def test_rollup_is_monotone_down(root):
    fresh = (_NOW - timedelta(seconds=10)).isoformat()
    stale = (_NOW - timedelta(hours=6)).isoformat()
    _write_sidecar(root, "nba", {"source_as_of": fresh})
    _write_sidecar(root, "mlb", {"source_as_of": stale})
    roll = fs.feed_rollup(["nba", "mlb"], now=_NOW)
    # One stale child -> parent is NOT green (monotone-DOWN); a fresh sibling can
    # never lift it back up. NEGATIVE CONTROL: status=='ok' here would be a bug.
    assert roll["status"] != "ok"
    assert roll["ok"] is False
    assert roll["n_fresh"] == 1 and roll["n_stale"] == 1
    _assert_no_money(roll)


def test_rollup_all_fresh_is_green(root):
    fresh = (_NOW - timedelta(seconds=10)).isoformat()
    _write_sidecar(root, "nba", {"source_as_of": fresh})
    _write_sidecar(root, "mlb", {"source_as_of": fresh})
    roll = fs.feed_rollup(["nba", "mlb"], now=_NOW)
    assert roll["status"] == "ok" and roll["ok"] is True


def test_rollup_empty_is_degraded_not_green(root):
    roll = fs.feed_rollup([], now=_NOW)
    assert roll["status"] != "ok"  # absence is never asserted green
    assert roll["ok"] is False


def test_degrade_fallback_is_monotone():
    d = fs._degrade_fallback
    assert d("ok", "degraded") == "degraded"
    assert d("degraded", "ok") == "degraded"   # never lifts back up
    assert d("degraded", "down") == "down"
    assert d("ok", "weird-unknown") == "degraded"  # unknown -> degraded, not ok
