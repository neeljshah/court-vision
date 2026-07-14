"""Per-file test for scripts.platformkit.live_edge.bus (+ bus_ingest tailing).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/live_edge/test_bus.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.platformkit.live_edge.bus import append_event, append_events, read_events, FileCursor
from scripts.platformkit.live_edge import bus_ingest


def test_append_and_read_roundtrip(tmp_path):
    bus_dir = tmp_path / "bus"
    append_event("odds:nba", "2026-07-14T00:01:00Z", "2026-07-14T00:01:00Z",
                 {"game_id": "g1"}, bus_dir=bus_dir)
    append_event("injury:nba", "2026-07-14T00:02:00Z", "2026-07-14T00:02:00Z",
                 {"player": "X"}, bus_dir=bus_dir)
    rows, offset = read_events("2026-07-14", bus_dir=bus_dir)
    assert len(rows) == 2
    assert offset == 2
    assert rows[0]["source"] == "odds:nba"
    assert rows[0]["payload"] == {"game_id": "g1"}


def test_asof_cursor_filters_and_resumes(tmp_path):
    bus_dir = tmp_path / "bus"
    append_event("odds:nba", "2026-07-14T00:01:00Z", "2026-07-14T00:01:00Z", {"n": 1}, bus_dir=bus_dir)
    append_event("odds:nba", "2026-07-14T00:05:00Z", "2026-07-14T00:05:00Z", {"n": 2}, bus_dir=bus_dir)

    # as-of cutoff before the 2nd row's knowability -> only 1st row visible
    rows, offset = read_events("2026-07-14", asof="2026-07-14T00:03:00Z", bus_dir=bus_dir)
    assert [r["payload"]["n"] for r in rows] == [1]
    # offset advances past BOTH lines even though asof filtered one out
    assert offset == 2

    # resuming from that offset with no new lines yields nothing
    more_rows, offset2 = read_events("2026-07-14", offset=offset, bus_dir=bus_dir)
    assert more_rows == []
    assert offset2 == 2

    # append a 3rd row, resume from offset -> only the new one comes back
    append_event("odds:nba", "2026-07-14T00:10:00Z", "2026-07-14T00:10:00Z", {"n": 3}, bus_dir=bus_dir)
    more_rows, offset3 = read_events("2026-07-14", offset=offset, bus_dir=bus_dir)
    assert [r["payload"]["n"] for r in more_rows] == [3]
    assert offset3 == 3


def test_append_events_batch_and_date_default(tmp_path):
    bus_dir = tmp_path / "bus"
    n = append_events([
        {"source": "gumbo:mlb", "ts_captured": "2026-07-11T18:00:00Z",
         "ts_knowable": "2026-07-11T18:00:00Z", "payload": {"inning": 1}},
        {"source": "gumbo:mlb", "ts_captured": "2026-07-11T18:05:00Z",
         "ts_knowable": "2026-07-11T18:05:00Z", "payload": {"inning": 2}},
    ], bus_dir=bus_dir)
    assert n == 2
    rows, _ = read_events("2026-07-11", bus_dir=bus_dir)
    assert len(rows) == 2


def test_file_cursor_persists(tmp_path):
    cdir = tmp_path / "_cursors"
    c1 = FileCursor("test_cursor", cursor_dir=cdir)
    assert c1.get("k") == 0
    c1.set("k", 7)
    c2 = FileCursor("test_cursor", cursor_dir=cdir)  # fresh instance, same file
    assert c2.get("k") == 7
    assert c2.get("missing", default=3) == 3


def test_ingest_odds_tails_and_is_idempotent(tmp_path, monkeypatch):
    line_history = tmp_path / "line_history"
    (line_history / "nba").mkdir(parents=True)
    f = line_history / "nba" / "2026-07-14.jsonl"
    f.write_text(
        json.dumps({"captured_at": "2026-07-14T00:01:00Z", "game_id": "g1"}) + "\n"
        + json.dumps({"captured_at": "2026-07-14T00:02:00Z", "game_id": "g2"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(bus_ingest, "LINE_HISTORY_DIR", line_history)

    bus_dir = tmp_path / "bus"
    cursor = FileCursor("test_ingest", cursor_dir=tmp_path / "_cursors")

    n1 = bus_ingest.ingest_odds(cursor=cursor, bus_dir=bus_dir)
    assert n1 == 2
    rows, _ = read_events("2026-07-14", bus_dir=bus_dir)
    assert len(rows) == 2
    assert rows[0]["source"] == "odds:nba"
    assert rows[0]["ts_knowable"] == "2026-07-14T00:01:00Z"

    # re-run with unchanged file -> idempotent, appends 0
    n2 = bus_ingest.ingest_odds(cursor=cursor, bus_dir=bus_dir)
    assert n2 == 0

    # append one new line -> only the new one is tailed
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"captured_at": "2026-07-14T00:03:00Z", "game_id": "g3"}) + "\n")
    n3 = bus_ingest.ingest_odds(cursor=cursor, bus_dir=bus_dir)
    assert n3 == 1
