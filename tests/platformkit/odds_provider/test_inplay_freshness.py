"""Per-file test for odds_provider.inplay_freshness (the LA-P0-a staleness helpers).

Proves: source_fresh accepts a recent source_ts and rejects a frozen (old) one;
freshest_source_ts returns the newest among kept ticks (None when none carry one);
write_freshness atomically writes a sidecar carrying last_source_ts, and a None there
(a frozen-feed poll that kept zero ticks) makes freshness.sidecar_status read RED.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_inplay_freshness.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scripts.platformkit.odds_provider import freshness, inplay_freshness as f

NOW = datetime(2026, 6, 18, 23, 30, tzinfo=timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_source_fresh_accepts_recent_rejects_frozen():
    assert f.source_fresh(_iso(NOW - timedelta(seconds=30)), NOW) is True
    assert f.source_fresh(_iso(NOW - timedelta(minutes=10)), NOW) is False  # frozen
    assert f.source_fresh(None, NOW) is False                               # unknown


def test_freshest_source_ts_picks_newest_or_none():
    kept = [{"source_ts": _iso(NOW - timedelta(seconds=60))},
            {"source_ts": _iso(NOW - timedelta(seconds=10))}]
    assert f.freshest_source_ts(kept) == _iso(NOW - timedelta(seconds=10))
    assert f.freshest_source_ts([{"prob": 0.5}]) is None  # none carry a source_ts
    assert f.freshest_source_ts([]) is None


def test_write_freshness_green_when_source_fresh(tmp_path):
    src = _iso(NOW - timedelta(seconds=20))
    f.write_freshness(tmp_path / "nba", NOW, 1, src)
    side = json.loads((tmp_path / "nba" / "_freshness.json").read_text())
    assert side["last_source_ts"] == src
    assert freshness.sidecar_status(tmp_path / "nba", now=NOW)["ok"] is True


def test_write_freshness_none_source_reads_red(tmp_path):
    # A frozen-feed poll kept zero ticks -> last_source_ts=None -> RED, never green.
    f.write_freshness(tmp_path / "nba", NOW, 0, None)
    st = freshness.sidecar_status(tmp_path / "nba", now=NOW)
    assert st["ok"] is False and st["status"] == "stale"
