"""Tests for the pod-side tracking daemon.

Each test locks a landmine that has actually bitten this pipeline.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import sys
from pathlib import Path

from scripts.platformkit import track_daemon


class FakeProc:
    def __init__(self, done=True):
        self._done = done

    def poll(self):
        return 0 if self._done else None


def _stage(tmp_path, monkeypatch):
    stage = tmp_path / "footage_bridge"
    stage.mkdir()
    monkeypatch.setattr(track_daemon, "STAGE", stage)
    monkeypatch.setattr(track_daemon, "TRACKING", tmp_path / "tracking")
    monkeypatch.setattr(track_daemon, "LEDGER", tmp_path / "ledger.jsonl")
    return stage


def test_partial_uploads_are_invisible(tmp_path, monkeypatch):
    """A .part file is an in-flight scp; tracking it ships a truncated video."""
    stage = _stage(tmp_path, monkeypatch)
    (stage / "tennis__t1.mp4.part").write_bytes(b"half")
    (stage / "tennis__t2.mp4").write_bytes(b"whole")

    ready = track_daemon.claimable({})

    assert [g for _, _, g in ready] == ["t2"]


def test_unparseable_names_are_skipped_not_guessed(tmp_path, monkeypatch):
    """Legacy uploads have no sport prefix; guessing the sport tracks it wrong."""
    stage = _stage(tmp_path, monkeypatch)
    (stage / "mlb_2026-08-30_0f36e8cc.mp4").write_bytes(b"x")

    assert track_daemon.claimable({}) == []


def test_active_jobs_are_not_launched_twice(tmp_path, monkeypatch):
    stage = _stage(tmp_path, monkeypatch)
    (stage / "soccer__s1.mp4").write_bytes(b"x")

    assert track_daemon.claimable({"soccer__s1.mp4": {}}) == []


def test_worker_cap_is_respected(tmp_path, monkeypatch):
    stage = _stage(tmp_path, monkeypatch)
    for i in range(5):
        (stage / ("tennis__g%d.mp4" % i)).write_bytes(b"x")
    launched = []
    monkeypatch.setattr(track_daemon.subprocess, "Popen",
                        lambda *a, **k: launched.append(a) or FakeProc(done=False))

    active = {}
    track_daemon.tick(active, workers=2)

    assert len(active) == 2


def test_finished_job_is_graded_and_video_deleted(tmp_path, monkeypatch):
    """The pod filled twice; a tracked video must never survive its run."""
    stage = _stage(tmp_path, monkeypatch)
    video = stage / "tennis__g1.mp4"
    video.write_bytes(b"x")
    log = stage / "tennis__g1.log"
    log.write_text("done", encoding="utf-8")
    csv_dir = track_daemon.TRACKING / "g1"
    csv_dir.mkdir(parents=True)
    (csv_dir / "tracking_data.csv").write_text(
        "h\n" + "row\n" * 900, encoding="utf-8")

    active = {"tennis__g1.mp4": {"proc": FakeProc(), "video": video, "log": log,
                                 "sport": "tennis", "game_id": "g1",
                                 "started": 0.0}}
    track_daemon.tick(active, workers=4)

    entry = json.loads(track_daemon.LEDGER.read_text(encoding="utf-8").strip())
    assert entry["status"] == "tracked" and entry["rows"] == 900
    assert not video.exists()


def test_thin_output_is_recorded_as_thin_with_a_tail(tmp_path, monkeypatch):
    """A 103-row CSV is non-empty and useless; it must not read as success."""
    stage = _stage(tmp_path, monkeypatch)
    video = stage / "kbo__k1.mp4"
    video.write_bytes(b"x")
    log = stage / "kbo__k1.log"
    log.write_text("Traceback: no frames decoded", encoding="utf-8")
    csv_dir = track_daemon.TRACKING / "k1"
    csv_dir.mkdir(parents=True)
    (csv_dir / "tracking_data.csv").write_text(
        "h\n" + "row\n" * 103, encoding="utf-8")

    active = {"kbo__k1.mp4": {"proc": FakeProc(), "video": video, "log": log,
                              "sport": "kbo", "game_id": "k1", "started": 0.0}}
    track_daemon.tick(active, workers=4)

    entry = json.loads(track_daemon.LEDGER.read_text(encoding="utf-8").strip())
    assert entry["status"] == "thin" and "no frames decoded" in entry["tail"]


def test_already_tracked_game_is_dropped_without_retracking(tmp_path, monkeypatch):
    """Re-tracking a done game burns a GPU slot the queue needs."""
    stage = _stage(tmp_path, monkeypatch)
    video = stage / "tennis__g9.mp4"
    video.write_bytes(b"x")
    csv_dir = track_daemon.TRACKING / "g9"
    csv_dir.mkdir(parents=True)
    (csv_dir / "tracking_data.csv").write_text(
        "h\n" + "row\n" * 5000, encoding="utf-8")
    monkeypatch.setattr(track_daemon.subprocess, "Popen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not re-track")))

    track_daemon.tick({}, workers=4)

    assert not video.exists()


def test_basketball_routes_to_run_clip_not_the_adapter_registry(tmp_path):
    """There is no basketball entry in ADAPTERS; adapter_run would exit 2."""
    command = track_daemon.build_command("wnba", tmp_path / "v.mp4", "w1")

    assert "scripts/run_clip.py" in command
    assert track_daemon.build_command("kbo", tmp_path / "v.mp4", "k1")[-3] == "baseball"


def test_clip_command_writes_where_tracking_rows_reads(tmp_path):
    """run_clip defaults data_dir to <repo>/data, so an omitted --data-dir sent
    every basketball job's rows to data/tracking_data.csv -- a path
    tracking_rows() never reads, and one file for all concurrent jobs to
    clobber. Four completed 3000-frame runs were graded "thin rows=0"."""
    command = track_daemon.build_command("ncaa_basketball", tmp_path / "v.mp4", "n1")

    assert "--data-dir" in command
    written = Path(command[command.index("--data-dir") + 1])
    read = track_daemon.TRACKING / "n1"
    assert written == read, "%s != %s" % (written, read)
    # Two concurrent games must not share one destination.
    other = track_daemon.build_command("wnba", tmp_path / "v.mp4", "w2")
    assert other[other.index("--data-dir") + 1] != command[command.index("--data-dir") + 1]


def test_ledger_carries_the_harness_verdict_not_just_row_count(tmp_path, monkeypatch):
    """A fat row count is not quality. Baseball can emit 4000+ rows whose
    coordinates are untrustworthy; by row count alone that is indistinguishable
    from a good tennis game."""
    stage = _stage(tmp_path, monkeypatch)
    monkeypatch.setattr(track_daemon, "REPORTS", tmp_path / "reports")
    video = stage / "baseball__b1.mp4"
    video.write_bytes(b"x")
    log = stage / "baseball__b1.log"
    log.write_text("ok", encoding="utf-8")
    csv_dir = track_daemon.TRACKING / "b1"
    csv_dir.mkdir(parents=True)
    (csv_dir / "tracking_data.csv").write_text(
        "h\n" + "row\n" * 4043, encoding="utf-8")
    report = track_daemon.REPORTS / "baseball" / "b1.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"passed": False,
                                  "failures": ["oob 0.6542 > 0.10"]}),
                      encoding="utf-8")

    active = {"baseball__b1.mp4": {"proc": FakeProc(), "video": video, "log": log,
                                   "sport": "baseball", "game_id": "b1",
                                   "started": 0.0}}
    track_daemon.tick(active, workers=4)

    entry = json.loads(track_daemon.LEDGER.read_text(encoding="utf-8").strip())
    assert entry["rows"] == 4043 and entry["status"] == "tracked"
    assert entry["passed"] is False
    assert "oob" in entry["failures"][0]


def test_grading_failure_never_kills_the_daemon(tmp_path, monkeypatch):
    """An unreadable CSV must not take down every other running job."""
    _stage(tmp_path, monkeypatch)
    monkeypatch.setattr(track_daemon, "REPORTS", tmp_path / "reports")

    result = track_daemon.verdict("tennis", "missing_game")

    assert result["passed"] is None
    assert result["failures"][0].startswith("ungraded")


def test_clip_sports_are_graded_as_basketball(tmp_path, monkeypatch):
    """run_clip.py writes no report, so wnba games went entirely ungraded."""
    _stage(tmp_path, monkeypatch)
    monkeypatch.setattr(track_daemon, "REPORTS", tmp_path / "reports")
    report = tmp_path / "reports" / "basketball" / "w1.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"passed": True, "failures": []}),
                      encoding="utf-8")

    assert track_daemon.verdict("wnba", "w1")["passed"] is True


class SlowProc:
    """A job that never exits, like the 5-hour run_clip that pinned a slot."""
    def __init__(self):
        self.killed = False

    def poll(self):
        return None

    def kill(self):
        self.killed = True


def test_a_job_that_never_finishes_is_killed_to_free_its_slot(tmp_path, monkeypatch):
    """run_clip.py was measured at 18216s (5.06h) still running. Two of those
    pinned two slots while 22 games queued behind them and jammed the stage."""
    stage = _stage(tmp_path, monkeypatch)
    monkeypatch.setattr(track_daemon, "REPORTS", tmp_path / "reports")
    video = stage / "wnba__w1.mp4"
    video.write_bytes(b"x")
    log = stage / "wnba__w1.log"
    log.write_text("slow", encoding="utf-8")
    proc = SlowProc()
    active = {"wnba__w1.mp4": {"proc": proc, "video": video, "log": log,
                               "sport": "wnba", "game_id": "w1",
                               "started": time.time() - 99999}}

    track_daemon.tick(active, workers=4)

    assert proc.killed is True
    assert not active
    entry = json.loads(track_daemon.LEDGER.read_text(encoding="utf-8").strip())
    assert entry["status"] == "timeout"


def test_a_timed_out_job_is_not_counted_as_tracked(tmp_path, monkeypatch):
    """Half a game is not a tracked game, even when the partial CSV is large."""
    stage = _stage(tmp_path, monkeypatch)
    monkeypatch.setattr(track_daemon, "REPORTS", tmp_path / "reports")
    video = stage / "wnba__w2.mp4"
    video.write_bytes(b"x")
    log = stage / "wnba__w2.log"
    log.write_text("partial", encoding="utf-8")
    csv_dir = track_daemon.TRACKING / "w2"
    csv_dir.mkdir(parents=True)
    (csv_dir / "tracking_data.csv").write_text("h\n" + "r\n" * 8000,
                                               encoding="utf-8")
    active = {"wnba__w2.mp4": {"proc": SlowProc(), "video": video, "log": log,
                               "sport": "wnba", "game_id": "w2",
                               "started": time.time() - 99999}}

    track_daemon.tick(active, workers=4)

    entry = json.loads(track_daemon.LEDGER.read_text(encoding="utf-8").strip())
    assert entry["rows"] == 8000
    assert entry["status"] == "timeout"


def test_a_job_inside_its_budget_is_left_alone(tmp_path, monkeypatch):
    stage = _stage(tmp_path, monkeypatch)
    video = stage / "tennis__t7.mp4"
    video.write_bytes(b"x")
    proc = SlowProc()
    active = {"tennis__t7.mp4": {"proc": proc, "video": video,
                                 "log": stage / "tennis__t7.log",
                                 "sport": "tennis", "game_id": "t7",
                                 "started": time.time() - 10}}

    track_daemon.tick(active, workers=4)

    assert proc.killed is False
    assert "tennis__t7.mp4" in active


def test_a_report_older_than_the_tracking_output_is_not_trusted(tmp_path, monkeypatch):
    """A re-tracked game keeps its old report when adapter_run fails to rewrite
    it. That returned an hour-stale verdict of 'empty' for a game that had just
    produced 18736 rows."""
    _stage(tmp_path, monkeypatch)
    monkeypatch.setattr(track_daemon, "REPORTS", tmp_path / "reports")
    csv_dir = track_daemon.TRACKING / "g1"
    csv_dir.mkdir(parents=True)
    csv = csv_dir / "tracking_data.csv"
    csv.write_text("h\n" + "r\n" * 900, encoding="utf-8")
    report = track_daemon.REPORTS / "tennis" / "g1.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"passed": True, "failures": []}), encoding="utf-8")
    os.utime(report, (1, 1))          # report is ancient
    os.utime(csv, (10_000, 10_000))   # tracking output is new

    result = track_daemon.verdict("tennis", "g1")

    assert result.get("passed") is not True, "stale report must not be trusted"


def test_a_report_newer_than_the_output_is_used(tmp_path, monkeypatch):
    _stage(tmp_path, monkeypatch)
    monkeypatch.setattr(track_daemon, "REPORTS", tmp_path / "reports")
    csv_dir = track_daemon.TRACKING / "g2"
    csv_dir.mkdir(parents=True)
    csv = csv_dir / "tracking_data.csv"
    csv.write_text("h\nr\n", encoding="utf-8")
    report = track_daemon.REPORTS / "tennis" / "g2.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"passed": True, "failures": []}), encoding="utf-8")
    os.utime(csv, (1, 1))
    os.utime(report, (10_000, 10_000))

    assert track_daemon.verdict("tennis", "g2")["passed"] is True


def test_orphans_from_a_dead_daemon_are_reaped(monkeypatch):
    """Orphans keep running unowned and a fresh daemon re-claims the same
    staged video, so two processes write one CSV. Cleaned up by hand twice."""
    listing = (
        "  PPID    PID COMMAND\n"
        "     1  111 python -m scripts.platformkit.adapter_run tennis /v/a.mp4 a\n"
        "  9999  222 python -m scripts.platformkit.adapter_run soccer /v/b.mp4 b\n"
        "     1  333 python scripts/run_clip.py --video /v/c.mp4 --game-id c\n"
        "     1  444 python -u -m scripts.platformkit.retrain_loop\n")
    killed = []
    monkeypatch.setattr(track_daemon.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, listing, ""))
    monkeypatch.setattr(track_daemon.os, "kill", lambda pid, sig: killed.append(pid))

    assert track_daemon.reap_orphans() == 2
    assert sorted(killed) == [111, 333]  # not 222 (owned) and not 444 (unrelated)


def test_reaping_never_raises_when_ps_is_unavailable(monkeypatch):
    def boom(*a, **k):
        raise OSError("no ps")

    monkeypatch.setattr(track_daemon.subprocess, "run", boom)

    assert track_daemon.reap_orphans() == 0
