"""Per-file test for scripts.platformkit.live_edge.robustness.{freshness_sla,watchdog}
(LIVE-EDGE A3 scraper robustness).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_freshness_sla.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.platformkit.live_edge.robustness.freshness_sla import (
    DOWN,
    OK,
    STALE,
    SlaEntry,
    TABLE,
    check_all,
    check_one,
    sla_path,
    write_rows,
)
from scripts.platformkit.live_edge.robustness.watchdog import (
    backoff_schedule,
    capture_proc_for,
    check_and_restart,
    conditional_get_headers,
    is_ban_shaped,
    jittered_delay,
)


def _write_bus_row(bus_dir: Path, date: str, source: str, ts_knowable: str) -> None:
    bus_dir.mkdir(parents=True, exist_ok=True)
    row = {"source": source, "ts_captured": ts_knowable, "ts_knowable": ts_knowable, "payload": {}}
    (bus_dir / f"{date}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_no_sla_entry_is_down_never_ok():
    row = check_one("totally_unknown_source_xyz", now=1000.0)
    assert row["status"] == DOWN
    assert row["reason"] == "no_sla_entry"


def test_fresh_bus_source_is_ok(tmp_path):
    bus_dir = tmp_path / "bus"
    _write_bus_row(bus_dir, "2026-07-14", "odds:nba", "2026-07-14T12:00:00+00:00")
    table = {"odds:nba": SlaEntry("bus", 1800.0)}
    now = __import__("datetime").datetime(2026, 7, 14, 12, 5, 0, tzinfo=__import__("datetime").timezone.utc).timestamp()
    row = check_one("odds:nba", now=now, table=table, bus_dir=bus_dir)
    assert row["status"] == OK
    assert row["last_seen"] == "2026-07-14T12:00:00+00:00"


def test_stale_source_fabricated_old_ts_flips_to_stale_or_down(tmp_path):
    """The DONE-bar simulation: fabricate an old ts_knowable and assert the SLA
    flips off OK -- this is the '<5min recovery' bar proven in test, not prod."""
    bus_dir = tmp_path / "bus"
    _write_bus_row(bus_dir, "2026-07-14", "gumbo:mlb", "2026-07-14T00:00:00+00:00")
    table = {"gumbo:mlb": SlaEntry("bus", 900.0)}
    now = __import__("datetime").datetime(2026, 7, 14, 12, 0, 0, tzinfo=__import__("datetime").timezone.utc).timestamp()
    row = check_one("gumbo:mlb", now=now, table=table, bus_dir=bus_dir)
    # 12h stale vs 900s sla * 3 = 2700s threshold -> well past DOWN.
    assert row["status"] == DOWN
    assert row["reason"] == "down"


def test_stale_within_3x_window_is_stale_not_down(tmp_path):
    bus_dir = tmp_path / "bus"
    _write_bus_row(bus_dir, "2026-07-14", "gumbo:mlb", "2026-07-14T12:00:00+00:00")
    table = {"gumbo:mlb": SlaEntry("bus", 900.0)}
    now = __import__("datetime").datetime(2026, 7, 14, 12, 30, 0, tzinfo=__import__("datetime").timezone.utc).timestamp()
    row = check_one("gumbo:mlb", now=now, table=table, bus_dir=bus_dir)
    assert row["status"] == STALE


def test_never_seen_source_is_down(tmp_path):
    bus_dir = tmp_path / "bus"
    table = {"odds:nba": SlaEntry("bus", 1800.0)}
    row = check_one("odds:nba", now=1000.0, table=table, bus_dir=bus_dir)
    assert row["status"] == DOWN
    assert row["reason"] == "never_seen"


def test_watchdog_emits_restart_intent_for_down_source_with_correct_capture_proc():
    rows = [
        {"source": "gumbo:mlb", "status": DOWN, "staleness_sec": 5000.0, "sla_sec": 900.0},
        {"source": "odds:nba", "status": OK, "staleness_sec": 10.0, "sla_sec": 1800.0},
    ]
    intents = check_and_restart(rows)
    assert len(intents) == 1
    assert intents[0]["source"] == "gumbo:mlb"
    assert intents[0]["capture_proc"] == "scripts.platformkit.live_edge.bus_ingest.ingest_gumbo"
    assert intents[0]["action"] == "restart_intent"


def test_capture_proc_for_every_prefix():
    assert capture_proc_for("odds:mlb").endswith("ingest_odds")
    assert capture_proc_for("injury:nba").endswith("ingest_injury")
    assert capture_proc_for("fotmob:soccer_intl").endswith("ingest_fotmob")
    assert capture_proc_for("news:espn").endswith("capture_once")
    assert capture_proc_for("mystery:x") == "unknown"


def test_backoff_schedule_bounded_and_increasing():
    assert backoff_schedule(0) < backoff_schedule(1) < backoff_schedule(2)
    assert backoff_schedule(20) == 900.0  # capped, never grows unbounded


def test_jittered_delay_stays_near_base():
    for _ in range(20):
        d = jittered_delay(100.0, jitter_frac=0.2)
        assert 80.0 <= d <= 120.0


def test_is_ban_shaped_detects_429_and_friends():
    assert is_ban_shaped(429) is True
    assert is_ban_shaped(403) is True
    assert is_ban_shaped(200) is False
    assert is_ban_shaped(None) is False


def test_conditional_get_headers_only_set_when_given():
    assert conditional_get_headers() == {}
    assert conditional_get_headers(etag="abc") == {"If-None-Match": "abc"}
    assert conditional_get_headers(last_modified="X") == {"If-Modified-Since": "X"}


def test_write_rows_appends_jsonl(tmp_path):
    out_dir = tmp_path / "freshness"
    rows = [{"source": "odds:nba", "status": OK}]
    path = write_rows(rows, date="2026-07-14", out_dir=out_dir)
    assert path == sla_path("2026-07-14", out_dir=out_dir)
    lines = path.read_text(encoding="ascii").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["source"] == "odds:nba"


def test_real_read_produces_a_row_for_every_wired_source():
    """DONE bar: SLA rows visible for every wired source on a REAL read
    (against the actual data/omni/live_edge bus + news dirs, no fabrication)."""
    rows = check_all()
    assert len(rows) == len(TABLE)
    sources_seen = {r["source"] for r in rows}
    assert sources_seen == set(TABLE.keys())
    for r in rows:
        assert r["status"] in (OK, STALE, DOWN)
