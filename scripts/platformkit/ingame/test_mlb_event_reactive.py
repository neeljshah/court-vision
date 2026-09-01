"""Per-file tests for mlb_event_reactive -- fake GUMBO feed, replayed diffs.

Proves: every event emitted exactly once, lag computed from the feed's own clock,
replay/truncation idempotent, and the REAL consumer (inplay_tick_latency /
latency_scoreboard) reads the rows through its own loader.

cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/ingame/test_mlb_event_reactive.py -q
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from scripts.platformkit.ingame import inplay_tick_latency as tl
from scripts.platformkit.ingame import latency_scoreboard as sb
from scripts.platformkit.ingame import mlb_event_reactive as er

GAME_PK = 999001
T0 = datetime(2026, 9, 1, 23, 0, 0, tzinfo=timezone.utc)


def _ts(sec: float) -> str:
    return (T0 + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _play(at_bat: int, inning: int, half: str, start: float, end: float,
          n_pitches: int, complete: bool = True, scoring: bool = False):
    """One GUMBO play, shaped like the live payload probed 2026-09-01 (gamePk 824472)."""
    return {
        "about": {"atBatIndex": at_bat, "inning": inning, "halfInning": half,
                  "startTime": _ts(start), "endTime": _ts(end),
                  "isComplete": complete, "isScoringPlay": scoring},
        "result": {"awayScore": 0, "homeScore": 0},
        "playEvents": [
            {"playId": "pid-%d-%d" % (at_bat, i), "index": i, "isPitch": True,
             "startTime": _ts(start + i), "endTime": _ts(start + i + 0.5)}
            for i in range(n_pitches)
        ] + [{"index": 99, "isPitch": False, "startTime": _ts(start)}],  # non-pitch, ignored
    }


def _doc(plays):
    return {"gamePk": GAME_PK, "gameData": {"game": {"pk": GAME_PK}},
            "liveData": {"plays": {"allPlays": plays}}}


# The fake feed: three successive snapshots, each a superset of the last (exactly what
# bootstrap-then-diffPatch produces once the patch batch has been applied).
SNAP_1 = _doc([_play(0, 1, "top", 0, 20, 3)])
SNAP_2 = _doc([_play(0, 1, "top", 0, 20, 3), _play(1, 1, "top", 25, 50, 4)])
SNAP_3 = _doc([_play(0, 1, "top", 0, 20, 3), _play(1, 1, "top", 25, 50, 4),
               _play(2, 1, "bot", 60, 90, 2, scoring=True)])


def test_extract_events_finds_every_event_kind():
    kinds = [e["event_kind"] for e in er.extract_events(SNAP_3)]
    assert kinds.count("pitch") == 3 + 4 + 2
    assert kinds.count("pa_end") == 3
    assert kinds.count("run_scored") == 1
    assert kinds.count("inning_change") == 2  # 1-top and 1-bot


def test_non_pitch_play_events_are_not_emitted():
    ids = {e["event_id"] for e in er.extract_events(SNAP_1)}
    assert not any(i.endswith("-99") or i.endswith(":99") for i in ids)


def test_lag_ms_is_detect_minus_feed_event_clock():
    detect = T0 + timedelta(seconds=100)
    rows = er.build_rows(SNAP_1, detect_ts=detect)
    row = [r for r in rows if r["event_kind"] == "pa_end"][0]
    # pa_end event_ts is the play's endTime = T0+20s; detect is T0+100s -> 80_000 ms
    assert row["lag_ms"] == 80_000
    assert row["src_ts"] == row["event_ts"] and row["ts"] == row["detect_ts"]
    assert row["source_artifact"].endswith("%s/feed/live" % GAME_PK)
    assert row["as_of"] == row["detect_ts"]
    assert row["sport"] == "mlb" and row["venue"] == "mlb_gumbo"


def test_each_event_emitted_exactly_once_across_a_replayed_diff_stream(tmp_path):
    seen = set()
    total = 0
    for snap in (SNAP_1, SNAP_2, SNAP_3):
        total += er.append_rows(er.build_rows(snap, T0 + timedelta(seconds=200), seen),
                                out_dir=tmp_path)
    lines = (tmp_path / "mlb" / ("%s.jsonl" % GAME_PK)).read_text(encoding="utf-8").splitlines()
    ids = [json.loads(x)["event_id"] for x in lines]
    assert total == len(lines) == len(set(ids)) == len(er.extract_events(SNAP_3))


def test_replay_from_disk_is_idempotent(tmp_path):
    seen = set()
    for snap in (SNAP_1, SNAP_2, SNAP_3):
        er.append_rows(er.build_rows(snap, T0 + timedelta(seconds=200), seen), out_dir=tmp_path)
    path = tmp_path / "mlb" / ("%s.jsonl" % GAME_PK)
    n_first = len(path.read_text(encoding="utf-8").splitlines())
    # a fresh process re-reads the store and replays the SAME stream -> zero new rows
    seen2 = er.seen_ids(tmp_path, str(GAME_PK))
    assert seen2 == seen
    for snap in (SNAP_1, SNAP_2, SNAP_3):
        assert er.append_rows(er.build_rows(snap, T0 + timedelta(seconds=300), seen2),
                              out_dir=tmp_path) == 0
    assert len(path.read_text(encoding="utf-8").splitlines()) == n_first


def test_truncated_trailing_line_does_not_break_the_seen_set(tmp_path):
    er.append_rows(er.build_rows(SNAP_1, T0 + timedelta(seconds=200), set()), out_dir=tmp_path)
    path = tmp_path / "mlb" / ("%s.jsonl" % GAME_PK)
    n_good = len(path.read_text(encoding="utf-8").splitlines())
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('{"event_id": "torn", "lag')  # crash mid-write
    assert len(er.seen_ids(tmp_path, str(GAME_PK))) == n_good
    # and the next pass appends only the genuinely-new events
    seen = er.seen_ids(tmp_path, str(GAME_PK))
    assert er.append_rows(er.build_rows(SNAP_2, T0 + timedelta(seconds=300), seen),
                          out_dir=tmp_path) == len(er.extract_events(SNAP_2)) - n_good


def test_summarize_reports_p50_p90_lag(tmp_path):
    er.append_rows(er.build_rows(SNAP_3, T0 + timedelta(seconds=100), set()), out_dir=tmp_path)
    s = er.summarize(tmp_path)
    assert s["n_rows"] == len(er.extract_events(SNAP_3))
    assert s["lag_ms_p50"] is not None and s["lag_ms_p90"] is not None
    assert s["by_kind"]["run_scored"] == 1
    assert s["edge_claimed"] is False


def test_consumer_loader_reads_the_rows_and_computes_lag(tmp_path):
    """The REAL consumer contract: inplay_tick_latency must see src_ts on these rows."""
    seen = set()
    for i, snap in enumerate((SNAP_1, SNAP_2, SNAP_3)):
        er.append_rows(er.build_rows(snap, T0 + timedelta(seconds=200 + i), seen),
                       out_dir=tmp_path)
    m = tl.measure_sport("mlb", grade_dir=tmp_path)
    assert m["n_ticks"] == len(er.extract_events(SNAP_3))
    assert m["schema_has_venue_ts"] is True
    assert m["src_ts_coverage_pct"] == 100.0
    assert m["lag_p50_sec"] is not None and m["lag_p90_sec"] is not None
    assert "NOT_AVAILABLE" not in m["capture_lag_note"]


def test_scoreboard_row_carries_the_two_part_gate_fields(tmp_path):
    """latency_scoreboard groups on sport/venue and evaluates the event_reactive gate."""
    er.append_rows(er.build_rows(SNAP_3, T0 + timedelta(seconds=201), set()), out_dir=tmp_path)
    rows = sb.build_rows(tmp_path)
    row = [r for r in rows if r["sport"] == "mlb"][0]
    assert row["venue"] == "mlb_gumbo"
    assert row["lag_p90"] is not None and row["src_ts_coverage_pct"] == 100.0
    # this synthetic corpus is deliberately far past the 5.0s gate -> fail-closed False
    assert row["lag_p90"] > sb.EVENT_REACTIVE_LAG_P90_SEC
    assert row["event_reactive"] is False


def test_bad_payloads_never_raise():
    assert er.extract_events(None) == []
    assert er.extract_events({}) == []
    assert er.extract_events({"liveData": {"plays": {"allPlays": [None, 7]}}}) == []
    # a play whose timestamps are junk is dropped, not emitted with a fabricated ts
    bad = _doc([_play(0, 1, "top", 0, 20, 1)])
    bad["liveData"]["plays"]["allPlays"][0]["about"]["endTime"] = "not-a-time"
    bad["liveData"]["plays"]["allPlays"][0]["about"]["startTime"] = "not-a-time"
    assert [e["event_kind"] for e in er.extract_events(bad)] == ["pitch"]
