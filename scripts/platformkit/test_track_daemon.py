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


# claimable() drops anything too small to be a video, so fixtures that
# stand in for a staged game have to clear that floor.
_VIDEO = b"x" * (track_daemon.MIN_VIDEO_BYTES + 1)


class FakeProc:
    def __init__(self, done=True):
        self._done = done

    def poll(self):
        return 0 if self._done else None


def _stage(tmp_path, monkeypatch):
    stage = tmp_path / "footage_bridge"
    stage.mkdir()
    monkeypatch.setattr(track_daemon, "STAGE", stage)
    monkeypatch.setattr(track_daemon, "CORPUS", tmp_path / "footage_corpus")
    monkeypatch.setattr(track_daemon, "QUARANTINE", tmp_path / "quarantine")
    monkeypatch.setattr(track_daemon, "TRACKING", tmp_path / "tracking")
    monkeypatch.setattr(track_daemon, "LEDGER", tmp_path / "ledger.jsonl")
    return stage


def test_partial_uploads_are_invisible(tmp_path, monkeypatch):
    """A .part file is an in-flight scp; tracking it ships a truncated video."""
    stage = _stage(tmp_path, monkeypatch)
    (stage / "tennis__t1.mp4.part").write_bytes(b"half")
    (stage / "tennis__t2.mp4").write_bytes(_VIDEO)

    ready = track_daemon.claimable({})

    assert [g for _, _, g in ready] == ["t2"]


def test_unparseable_names_are_skipped_not_guessed(tmp_path, monkeypatch):
    """Legacy uploads have no sport prefix; guessing the sport tracks it wrong."""
    stage = _stage(tmp_path, monkeypatch)
    (stage / "mlb_2026-08-30_0f36e8cc.mp4").write_bytes(_VIDEO)

    assert track_daemon.claimable({}) == []


def test_active_jobs_are_not_launched_twice(tmp_path, monkeypatch):
    stage = _stage(tmp_path, monkeypatch)
    (stage / "soccer__s1.mp4").write_bytes(_VIDEO)

    assert track_daemon.claimable({"soccer__s1.mp4": {}}) == []


def test_worker_cap_is_respected(tmp_path, monkeypatch):
    stage = _stage(tmp_path, monkeypatch)
    for i in range(5):
        (stage / ("tennis__g%d.mp4" % i)).write_bytes(_VIDEO)
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
    video.write_bytes(_VIDEO)
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
    assert entry["adjudicated"] is True
    assert not video.exists()


def test_direct_run_clip_output_writes_no_ball_capability_sidecar(tmp_path, monkeypatch):
    """run_clip writes the CSV itself, so the daemon owns its capability sidecar."""
    stage = _stage(tmp_path, monkeypatch)
    video = stage / "wnba__w1.mp4"
    video.write_bytes(_VIDEO)
    log = stage / "wnba__w1.log"
    log.write_text("done", encoding="utf-8")
    csv_dir = track_daemon.TRACKING / "w1"
    csv_dir.mkdir(parents=True)
    (csv_dir / "tracking_data.csv").write_text(
        "h\n" + "row\n" * 900, encoding="utf-8")

    active = {"wnba__w1.mp4": {"proc": FakeProc(), "video": video, "log": log,
                               "sport": "wnba", "game_id": "w1", "started": 0.0}}
    track_daemon.tick(active, workers=4)

    payload = json.loads(
        (csv_dir / "tracking_capability.json").read_text(encoding="utf-8"))
    assert payload == {"sport": "wnba", "ball_telemetry_available": False}


def test_nonempty_output_is_adjudicated_even_when_the_harness_fails(tmp_path, monkeypatch):
    """Completion means a verdict, not a minimum row count or a PASS."""
    stage = _stage(tmp_path, monkeypatch)
    video = stage / "kbo__k1.mp4"
    video.write_bytes(_VIDEO)
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
    assert entry["status"] == "tracked" and entry["passed"] is False
    assert entry["adjudicated"] is True


def _tracked_game(tmp_path, monkeypatch, game_id, passed):
    """Stage a game with a durable sidecar and retained original footage."""
    stage = _stage(tmp_path, monkeypatch)
    monkeypatch.setattr(track_daemon, "REPORTS", tmp_path / "reports")
    video = stage / ("tennis__%s.mp4" % game_id)
    video.write_bytes(_VIDEO)
    csv_dir = track_daemon.TRACKING / game_id
    csv_dir.mkdir(parents=True)
    (csv_dir / "tracking_data.csv").write_text(
        "h\n" + "row\n" * 5000, encoding="utf-8")
    sidecar = csv_dir / "harness_verdict.json"
    sidecar.write_text(json.dumps({"passed": passed,
                                   "failure_heads": [] if passed else ["oob 0.59 > 0.08"],
                                   "coverage_pct": 0.9, "coordinate_space": "court_feet",
                                   "rung": "COURT_FEET", "evaluated_at": 1,
                                   "csv_fsynced": True}), encoding="utf-8")
    track_daemon.CORPUS.mkdir(parents=True)
    (track_daemon.CORPUS / video.name).write_bytes(_VIDEO)
    return video


def test_already_tracked_game_is_dropped_without_retracking(tmp_path, monkeypatch):
    """Re-tracking a done and PASSING game burns a GPU slot the queue needs."""
    video = _tracked_game(tmp_path, monkeypatch, "g9", passed=True)
    monkeypatch.setattr(track_daemon.subprocess, "Popen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("must not re-track")))

    track_daemon.tick({}, workers=4)

    assert not video.exists()


def test_a_restaged_failing_game_is_dropped_when_already_adjudicated(tmp_path, monkeypatch):
    """A FAIL is honestly done once its durable sidecar exists."""
    video = _tracked_game(tmp_path, monkeypatch, "g8", passed=False)
    launched = []
    monkeypatch.setattr(
        track_daemon.subprocess, "Popen",
        lambda *a, **k: (launched.append(a), FakeProc(done=False))[1])

    track_daemon.tick({}, workers=4)

    assert not launched
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
    video.write_bytes(_VIDEO)
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
    assert entry["failure_heads"]


def test_grading_failure_never_kills_the_daemon(tmp_path, monkeypatch):
    """An unreadable CSV must not take down every other running job."""
    _stage(tmp_path, monkeypatch)
    monkeypatch.setattr(track_daemon, "REPORTS", tmp_path / "reports")

    result = track_daemon.verdict("tennis", "missing_game", tmp_path / "missing.mp4")

    assert result is None


def test_clip_sports_route_to_the_basketball_harness(tmp_path, monkeypatch):
    """run_clip output is adjudicated with basketball's frozen thresholds."""
    _stage(tmp_path, monkeypatch)
    monkeypatch.setattr(track_daemon, "REPORTS", tmp_path / "reports")
    assert "scripts/run_clip.py" in track_daemon.build_command("wnba", tmp_path / "v.mp4", "w1")


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
    video.write_bytes(_VIDEO)
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
    video.write_bytes(_VIDEO)
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
    video.write_bytes(_VIDEO)
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

    result = track_daemon.verdict("tennis", "g1", tmp_path / "g1.mp4")

    assert result is not None and result["passed"] is False


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

    assert track_daemon.verdict("tennis", "g2", tmp_path / "g2.mp4")["passed"] is False


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


def test_every_ledger_entry_is_dated(tmp_path, monkeypatch):
    """An undated append-only log has to be dated by inference, and inference
    is wrong: a "timeout at 2707s" read as current was actually written under
    an older, shorter budget."""
    stage = _stage(tmp_path, monkeypatch)
    monkeypatch.setattr(track_daemon, "REPORTS", tmp_path / "reports")
    video = stage / "tennis__t1.mp4"
    video.write_bytes(_VIDEO)
    log = stage / "tennis__t1.log"
    log.write_text("ok", encoding="utf-8")

    active = {"tennis__t1.mp4": {"proc": FakeProc(), "video": video, "log": log,
                                 "sport": "tennis", "game_id": "t1",
                                 "started": time.time() - 5}}
    track_daemon.tick(active, workers=4)

    entry = json.loads(track_daemon.LEDGER.read_text(encoding="utf-8").strip())
    assert entry["finished_at"] >= entry["seconds"]
    assert abs(entry["finished_at"] - time.time()) < 60


def test_a_tracked_video_is_retained_not_destroyed(tmp_path, monkeypatch):
    """Deleting source footage after one attempt is what made a 0%-pass corpus
    unrecoverable: re-measuring a fix meant re-downloading over an 88.6 Mbps
    ceiling. 67 MB a game against 334 TB free is not a reason to destroy it."""
    stage = _stage(tmp_path, monkeypatch)
    monkeypatch.setattr(track_daemon, "REPORTS", tmp_path / "reports")
    video = stage / "soccer__s1.mp4"
    video.write_bytes(_VIDEO)
    log = stage / "soccer__s1.log"
    log.write_text("ok", encoding="utf-8")

    active = {"soccer__s1.mp4": {"proc": FakeProc(), "video": video, "log": log,
                                 "sport": "soccer", "game_id": "s1",
                                 "started": time.time()}}
    track_daemon.tick(active, workers=4)

    assert not video.exists(), "the stage must be reclaimed"
    assert not log.exists()
    retained = track_daemon.CORPUS / "soccer__s1.mp4"
    assert retained.read_bytes() == _VIDEO


def test_the_retained_corpus_is_not_reclaimed_as_staged_work(tmp_path, monkeypatch):
    """CORPUS inside STAGE would make claimable() re-claim every retained game
    forever. They must be separate directories."""
    _stage(tmp_path, monkeypatch)
    track_daemon.CORPUS.mkdir(parents=True)
    (track_daemon.CORPUS / "soccer__s2.mp4").write_bytes(b"x")

    assert track_daemon.claimable({}) == []


def test_the_basketball_path_gets_the_budget_its_checkpoints_need():
    """run_clip output is quantized: unified_pipeline checkpoints every 2000
    frames and never flushes the residual, so a job is worth nothing until it
    crosses frame 2000 and ~2700 rows once it does. Measured on four concurrent
    NCAA jobs, the slowest crossed at ~3610s -- ten seconds past a 3600s
    deadline, losing everything. A light adapter has no such cliff."""
    assert track_daemon.job_timeout("ncaa_basketball") > 3610
    assert track_daemon.job_timeout("wnba") == track_daemon.CLIP_JOB_TIMEOUT_SECONDS
    assert track_daemon.job_timeout("tennis") == track_daemon.JOB_TIMEOUT_SECONDS
    assert track_daemon.job_timeout("baseball") == track_daemon.JOB_TIMEOUT_SECONDS


def test_a_slow_basketball_job_is_not_killed_at_the_adapter_deadline(tmp_path, monkeypatch):
    """The regression this guards: a run_clip job killed at 3600s while still
    short of its first durable checkpoint reports success and writes four rows."""
    stage = _stage(tmp_path, monkeypatch)
    monkeypatch.setattr(track_daemon, "REPORTS", tmp_path / "reports")
    video = stage / "wnba__w9.mp4"
    video.write_bytes(_VIDEO)
    log = stage / "wnba__w9.log"
    log.write_text("Frame 1999...", encoding="utf-8")

    killed = []
    proc = FakeProc(done=False)
    proc.kill = lambda: killed.append(True)
    active = {"wnba__w9.mp4": {"proc": proc, "video": video, "log": log,
                               "sport": "wnba", "game_id": "w9",
                               "started": time.time() - 3700}}
    track_daemon.tick(active, workers=4)

    assert not killed, "3700s is past the adapter deadline but inside the clip budget"
    assert "wnba__w9.mp4" in active


def test_a_completed_upload_that_is_not_a_video_is_dropped(tmp_path, monkeypatch):
    """Atomic rename proves the upload finished, not that it holds a video. A
    262-byte tennis__tennis_10.mp4 was claimed, failed, re-claimed, and also
    read to a sport agent as "the corpus has a tennis clip"."""
    stage = _stage(tmp_path, monkeypatch)
    tiny = stage / "tennis__t10.mp4"
    tiny.write_bytes(b"x" * 262)
    real = stage / "tennis__t11.mp4"
    real.write_bytes(b"x" * (2 * track_daemon.MIN_VIDEO_BYTES))

    ready = track_daemon.claimable({})

    assert [g for _, _, g in ready] == ["t11"]
    assert not tiny.exists(), "a non-video must not sit in the stage being re-claimed"
    entry = json.loads(track_daemon.LEDGER.read_text(encoding="utf-8").strip())
    assert entry["status"] == "corrupt" and "262 bytes" in entry["failure_heads"][0]


def test_failed_corrupt_retain_is_renamed_once_not_reclaimed(tmp_path, monkeypatch):
    """A failed quarantine move must not append a corrupt row every tick."""
    stage = _stage(tmp_path, monkeypatch)
    tiny = stage / "tennis__bad.mp4"
    tiny.write_bytes(b"x" * 262)
    original_replace = Path.replace

    def fail_quarantine(source, target):
        if target.parent == track_daemon.QUARANTINE:
            raise OSError("quarantine unavailable")
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_quarantine)
    track_daemon.tick({}, workers=1)
    track_daemon.tick({}, workers=1)

    entries = [json.loads(line) for line in track_daemon.LEDGER.read_text().splitlines()]
    assert len(entries) == 1 and entries[0]["status"] == "corrupt"
    assert entries[0]["retain_failed"] is True
    assert not tiny.exists() and (stage / "tennis__bad.mp4.failed").exists()
