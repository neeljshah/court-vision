"""G329: a data dir left behind by a killed worker must not buy a completed row.

MEASURED on the pod for the 2026-09-08 05:26Z volume event: the relaunched
daemon picked up 8 clips; the 4 whose data dir was older than their own start
recorded 0 to 2 rows in 365 to 393 s and were written as `tracked`, while the 4
with no prior data dir recorded thousands. A `tracked` row is what moves the
source out of staging, so a row like that can cost the mp4 it never read.

n = CONSTRUCT. Every branch of the new marking is enumerated here.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from scripts.platformkit import track_daemon
from scripts.platformkit import track_daemon_ledger
from scripts.platformkit import track_daemon_sources


_VIDEO = b"x" * (track_daemon.MIN_VIDEO_BYTES + 1)
_HEADER = "frame,player_id\n"


class FakeProc:
    """A tracking child that has already exited, whatever its exit code was."""

    def poll(self):
        return 0


def _stage(tmp_path, monkeypatch):
    stage = tmp_path / "footage_bridge"
    stage.mkdir()
    monkeypatch.setattr(track_daemon, "STAGE", stage)
    monkeypatch.setattr(track_daemon, "CORPUS", tmp_path / "footage_corpus")
    monkeypatch.setattr(track_daemon, "QUARANTINE", tmp_path / "quarantine")
    monkeypatch.setattr(track_daemon, "TRACKING", tmp_path / "tracking")
    monkeypatch.setattr(track_daemon, "LEDGER", tmp_path / "ledger.jsonl")
    source = {"source_fps": None, "source_height": None, "source_duration": None}
    monkeypatch.setattr(track_daemon_sources, "probe_source", lambda _: source)
    monkeypatch.setattr(track_daemon, "probe_source", lambda _: source)
    return stage


def _run(tmp_path, monkeypatch, game_id, rows, started, leftovers=()):
    """Drive one finished job through the real daemon path and read its row."""
    stage = _stage(tmp_path, monkeypatch)
    video = stage / ("nba__%s.mp4" % game_id)
    video.write_bytes(_VIDEO)
    log = stage / ("nba__%s.log" % game_id)
    log.write_text("done", encoding="utf-8")

    data_dir = track_daemon.TRACKING / game_id
    data_dir.mkdir(parents=True)
    for name in leftovers:
        left = data_dir / name
        left.write_text("{}", encoding="utf-8")
        os.utime(left, (started - 100, started - 100))
    (data_dir / "tracking_data.csv").write_text(
        _HEADER + "0,1\n" * rows, encoding="utf-8")

    active = {video.name: {"proc": FakeProc(), "video": video, "log": log,
                           "sport": "nba", "game_id": game_id,
                           "started": started}}
    track_daemon.tick(active, workers=4)
    for job in active.values():
        job["adjudication"].join(5)
    track_daemon.tick(active, workers=4)
    text = Path(track_daemon.LEDGER).read_text(encoding="utf-8").strip()
    return json.loads(text.splitlines()[-1])


def test_a_partial_data_dir_can_no_longer_yield_a_completed_row(tmp_path, monkeypatch):
    """The bar. A killed worker's leftovers plus a thin fast run is not `tracked`."""
    started = time.time() - 300
    entry = _run(tmp_path, monkeypatch, "g_resume", 2, started,
                 leftovers=("resolver_debug.json",))

    assert entry["status"] == track_daemon_ledger.DEGENERATE_STATUS
    assert entry["status"] != "tracked"
    assert entry["degenerate"] is True and entry["resumed_partial"] is True
    assert entry["rows"] == 2, "rows stay as measured, never zeroed or inflated"


def test_a_clean_data_dir_with_a_full_row_count_stays_tracked(tmp_path, monkeypatch):
    """A clean data dir plus a full row count keeps every meaning it had.

    This case does NOT prove the tracker ran: the child is a stub that has
    already exited and the output was placed by the harness. What it proves
    is that the new marking downgrades nothing when neither condition holds.
    """
    started = time.time() - 300
    entry = _run(tmp_path, monkeypatch, "g_clean", 900, started)

    assert entry["status"] == "tracked"
    assert entry["degenerate"] is False and entry["resumed_partial"] is False
    assert entry["rows"] == 900


def test_leftovers_alone_never_downgrade_a_real_run(tmp_path, monkeypatch):
    """Contract B3: a stale file is not evidence of a bad run, only a thin one is."""
    started = time.time() - 300
    entry = _run(tmp_path, monkeypatch, "g_resume_ok", 900, started,
                 leftovers=("resolver_debug.json",))

    assert entry["status"] == "tracked"
    assert entry["resumed_partial"] is True and entry["degenerate"] is False


def test_every_row_carries_the_two_new_fields_and_keeps_the_old_ones(tmp_path, monkeypatch):
    """Contract B2: additive only. Nothing that existed is renamed or dropped."""
    started = time.time() - 300
    entry = _run(tmp_path, monkeypatch, "g_fields", 900, started)

    for field in ("game_id", "sport", "status", "adjudicated", "rows", "verdict",
                  "passed", "failure_heads", "failures", "coverage_pct",
                  "seconds", "finished_at", "decoded_frames", "evaluated_frames"):
        assert field in entry, field
    assert "degenerate" in entry and "resumed_partial" in entry

    corrupt = track_daemon_ledger.corrupt_entry("g_corrupt", "nba", 10, retained=True)
    assert corrupt["degenerate"] is True, "0 rows in 0 s is degenerate by D2"
    assert corrupt["resumed_partial"] is False, "no tracker ran, so no resume"
    assert corrupt["status"] == "corrupt" and corrupt["rows"] == 0


def test_the_two_thresholds_are_the_sealed_ones():
    """rows below 50 AND wall below 600 s, both sides of each boundary."""
    assert track_daemon_ledger.DEGENERATE_ROWS == 50
    assert track_daemon_ledger.DEGENERATE_SECONDS == 600
    assert track_daemon_ledger.is_degenerate(49, 599) is True
    assert track_daemon_ledger.is_degenerate(50, 599) is False
    assert track_daemon_ledger.is_degenerate(49, 600) is False
    assert track_daemon_ledger.is_degenerate(None, 599) is False
    assert track_daemon_ledger.is_degenerate(49, None) is False


def test_a_missing_data_dir_is_not_a_resume(tmp_path):
    """Absence is never a defect: no dir, an unusable start, both report False."""
    assert track_daemon_ledger.resumed_partial(tmp_path / "nope", time.time()) is False
    assert track_daemon_ledger.resumed_partial(tmp_path, None) is False
    assert track_daemon_ledger.resumed_partial(None, time.time()) is False
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    (fresh / "tracking_data.csv").write_text(_HEADER, encoding="utf-8")
    assert track_daemon_ledger.resumed_partial(fresh, time.time() - 300) is False


def test_the_census_reads_resume_from_the_two_append_log_fields(tmp_path):
    """The census derives its start from `finished_at` minus `seconds` only."""
    from scripts.platformkit.tracking import g329_degenerate_census as census

    log = tmp_path / "snapshot.jsonl"
    log.write_text("\n".join([
        json.dumps({"game_id": "old_dir", "sport": "nba", "status": "tracked",
                    "rows": 2, "seconds": 365, "finished_at": 2000}),
        json.dumps({"game_id": "new_dir", "sport": "nba", "status": "tracked",
                    "rows": 2, "seconds": 365, "finished_at": 2000}),
        json.dumps({"game_id": "slow", "sport": "nba", "status": "thin",
                    "rows": 0, "seconds": 4000, "finished_at": 9000,
                    "tail": "PREFLIGHT FAIL"}),
        json.dumps({"game_id": "full", "sport": "nba", "status": "tracked",
                    "rows": 900, "seconds": 365, "finished_at": 2000}),
    ]) + "\n", encoding="ascii")
    facts = tmp_path / "facts.txt"
    facts.write_text(
        "old_dir|minmtime=1000|corpus=no|bridge=no|quar=no|guardhits=1\n"
        "new_dir|minmtime=1900|corpus=yes|bridge=no|quar=no|guardhits=0\n"
        "slow|minmtime=none|corpus=no|bridge=yes|quar=no|guardhits=0\n",
        encoding="ascii")

    rows = {row["clip_id"]: row for row in
            census.build(census.read_log(log), census.read_pod_facts(facts))}

    assert "full" not in rows, "900 rows is not a LOW ROW"
    assert rows["old_dir"]["resume"] == "resume"
    assert rows["old_dir"]["degenerate"] == "true"
    assert rows["old_dir"]["source_state"] == "gone"
    assert rows["old_dir"]["guard_named"] == "true"
    assert rows["new_dir"]["resume"] == "fresh_dir"
    assert rows["new_dir"]["source_state"] == "corpus"
    assert rows["slow"]["resume"] == "no_data_dir"
    assert rows["slow"]["degenerate"] == "false", "4000 s is not a short run"
    assert rows["slow"]["class"] == "preflight_reject"
    assert rows["slow"]["source_state"] == "bridge"


def test_the_census_pads_every_integer_cell_to_six_digits(tmp_path):
    """Zero-padding is what keeps a restricted digit sequence out of a cell."""
    from scripts.platformkit.tracking import g329_degenerate_census as census

    assert census._pad(0) == "000000"
    assert census._pad(365) == "000365"
    assert census._pad(None) == "none"


def test_an_unrecorded_row_count_is_unknown_and_never_degenerate(tmp_path):
    """An absent `rows` field is UNKNOWN, not zero: it invents no thin run."""
    from scripts.platformkit.tracking import g329_degenerate_census as census

    entry = {"game_id": "no_count", "sport": "nba", "status": "thin",
             "seconds": 100, "finished_at": 2000}
    log = tmp_path / "snapshot.jsonl"
    log.write_text(json.dumps(entry), encoding="ascii")
    facts = tmp_path / "facts.txt"
    facts.write_text("no_count|minmtime=none|corpus=no|bridge=no|quar=no|guardhits=0",
                     encoding="ascii")

    assert census.row_count(entry) is None
    assert census.is_degenerate(entry) is False
    rows = census.build(census.read_log(log), census.read_pod_facts(facts))
    assert len(rows) == 1, "the row passes through instead of vanishing"
    assert rows[0]["rows"] == census.UNKNOWN
    assert rows[0]["degenerate"] == census.UNKNOWN
    assert "DEGENERATE n=0 of 1 LOW ROWS" in census.table(rows)


def test_a_clip_with_no_pod_facts_is_unknown_and_never_data_loss(tmp_path):
    """An unread holding place is not an absent mp4, so it is never data loss."""
    from scripts.platformkit.tracking import g329_degenerate_census as census

    log = tmp_path / "snapshot.jsonl"
    log.write_text(json.dumps({"game_id": "no_facts", "sport": "nba",
                               "status": "thin", "rows": 0, "seconds": 100,
                               "finished_at": 2000}), encoding="ascii")
    facts = tmp_path / "facts.txt"
    facts.write_text("", encoding="ascii")

    assert census.source_state({}) == census.UNKNOWN
    assert census.source_state({"corpus": "no", "bridge": "no", "quar": "no"}) == "gone"
    rows = census.build(census.read_log(log), census.read_pod_facts(facts))
    assert rows[0]["source_state"] == census.UNKNOWN
    assert rows[0]["degenerate"] == "true", "the row is still a measured thin run"
    lines = census.table(rows)
    assert "DATA LOSS n=0 of 1 degenerate rows (source in no holding place)" in lines
