"""Per-file test: serving-path staleness guard (LA-P0-b stale-never-green rail).

Proves the freshness sidecar + guard that turns a dead/cached feed RED:
  * the PREGAME daemon writes a per-sport _freshness.json carrying the slate's TRUE
    source as_of (not the poll wall-clock);
  * freshness.sidecar_status reads it and reports ok=True only while FRESH;
  * once the source as_of ages past the max age, the SAME sidecar reads ok=False /
    "stale" -- a dead feed (re-serving an old cached body) can never read green;
  * a MISSING sidecar (daemon never ran) reads ok=False / "missing", never green.

Offline: injected agg payload + fake clock; no network.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_freshness_serving_guard.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from scripts.platformkit.odds_provider import freshness
from scripts.platformkit.odds_provider import line_snapshot_daemon as daemon


NOW = datetime(2026, 6, 18, 23, 30, tzinfo=timezone.utc)


def _agg(as_of_iso, commence_iso):
    return {
        "sport": "nba", "status": "ok", "as_of": as_of_iso,
        "sources": {"espn": "ok"},
        "events": [{
            "event_id": "G1", "sport": "nba", "home": "Knicks", "away": "Spurs",
            "commence_time": commence_iso, "as_of": as_of_iso,
            "prices": {"espn:DraftKings": {"home": 1.91, "away": 2.05}},
        }],
    }


def test_pregame_poll_writes_sidecar_with_source_as_of(tmp_path):
    as_of = "2026-06-18T23:29:00+00:00"
    rep = daemon.poll_once("nba", now=NOW, out_dir=tmp_path,
                           agg=_agg(as_of, "2026-06-19T00:00:00+00:00"))
    assert rep["status"] == "ok"
    side = json.loads((tmp_path / "nba" / "_freshness.json").read_text())
    # The sidecar carries the slate's TRUE source as_of, not the poll wall-clock.
    assert side["source_as_of"] == as_of
    assert side["poll_at"].startswith("2026-06-18T23:30")


def test_guard_fresh_then_stale_on_same_sidecar(tmp_path):
    # Source fetched at 23:29; sidecar written.
    daemon.poll_once("nba", now=NOW, out_dir=tmp_path,
                     agg=_agg("2026-06-18T23:29:00+00:00",
                              "2026-06-19T00:00:00+00:00"))
    sport_dir = tmp_path / "nba"

    # Serving 1 min after the source time -> FRESH (within 900s default).
    st = freshness.sidecar_status(
        sport_dir, now=datetime(2026, 6, 18, 23, 30, tzinfo=timezone.utc))
    assert st["ok"] is True
    assert st["status"] == "fresh"

    # Serving 30 min later -> the SAME (now dead) feed's sidecar reads STALE.
    st2 = freshness.sidecar_status(
        sport_dir, now=datetime(2026, 6, 18, 23, 59, tzinfo=timezone.utc))
    assert st2["ok"] is False
    assert st2["status"] == "stale"
    assert freshness.serve_ok(
        sport_dir, now=datetime(2026, 6, 18, 23, 59, tzinfo=timezone.utc)) is False


def test_missing_sidecar_reads_red_not_green(tmp_path):
    # No daemon ever ran for this sport -> no sidecar -> NOT fresh (red).
    st = freshness.sidecar_status(tmp_path / "never_ran", now=NOW)
    assert st["ok"] is False
    assert st["status"] == "missing"
    assert freshness.serve_ok(tmp_path / "never_ran", now=NOW) is False


def test_unavailable_poll_does_not_write_green_sidecar(tmp_path):
    # An UNAVAILABLE slate (dead feed) writes NO sidecar -> guard stays red.
    rep = daemon.poll_once(
        "nba", now=NOW, out_dir=tmp_path,
        agg={"sport": "nba", "status": "unavailable", "as_of": NOW.isoformat(),
             "sources": {}, "events": []})
    assert rep["status"] == "unavailable"
    assert not (tmp_path / "nba" / "_freshness.json").exists()
    assert freshness.serve_ok(tmp_path / "nba", now=NOW) is False
