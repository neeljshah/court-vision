"""G328: adjudicating jobs and the ``--workers`` count.

The daemon releases a worker slot the moment a job leaves tracking for
adjudication, so the count it prints can stand above ``--workers`` while a
threaded pandas pass is still burning CPU inside the daemon process. These
tests reproduce that on a construct with a fake tracker and a fake
adjudicator, pin that the opt-in flag removes it, and pin that the ledger row
is byte-identical in both modes.
"""
from __future__ import annotations

import json
import threading
import time

from scripts.platformkit import track_daemon
from scripts.platformkit import track_daemon_sources
from scripts.platformkit.track_daemon_slots import slots_in_use


_VIDEO = b"x" * (track_daemon.MIN_VIDEO_BYTES + 1)
_ROWS = 900
# Wall-clock fields differ between two runs by construction, so they are
# checked for presence and type instead of for equality.
_WALL_FIELDS = ("seconds", "finished_at")


class FakeProc:
    """A fake tracker. ``done`` decides whether it has already exited."""

    def __init__(self, done=True):
        self._done = done

    def poll(self):
        return 0 if self._done else None


def _fake_graded():
    return {"passed": False, "failure_heads": [], "coverage_pct": 0.0,
            "harness_coverage_pct": 0.0, "coordinate_space": "undeclared",
            "rung": "UNDECLARED", "evaluated_at": 1, "csv_fsynced": True,
            "decoded_frames": 17, "evaluated_frames": 17, "stride": 1}


def _run_mode(root, monkeypatch, adjudication_holds_slot):
    """Drive one daemon tick with a finished job plus one queued video.

    Returns the active count observed while the adjudication was in flight and
    the single ledger row the finished job produced.
    """
    stage = root / "footage_bridge"
    stage.mkdir(parents=True)
    monkeypatch.setattr(track_daemon, "STAGE", stage)
    monkeypatch.setattr(track_daemon, "CORPUS", root / "footage_corpus")
    monkeypatch.setattr(track_daemon, "QUARANTINE", root / "quarantine")
    monkeypatch.setattr(track_daemon, "TRACKING", root / "tracking")
    monkeypatch.setattr(track_daemon, "LEDGER", root / "ledger.jsonl")
    source = {"source_fps": None, "source_height": None, "source_duration": None}
    monkeypatch.setattr(track_daemon_sources, "probe_source", lambda _: source)
    monkeypatch.setattr(track_daemon, "probe_source", lambda _: source)

    finished = stage / "tennis__finished.mp4"
    queued = stage / "tennis__queued.mp4"
    finished.write_bytes(_VIDEO)
    queued.write_bytes(_VIDEO)
    log = stage / "tennis__finished.log"
    log.write_text("done", encoding="utf-8")
    csv_dir = track_daemon.TRACKING / "finished"
    csv_dir.mkdir(parents=True)
    (csv_dir / "tracking_data.csv").write_text(
        "h\n" + "row\n" * _ROWS, encoding="utf-8")

    # The fake adjudicator blocks until the test releases it, so the claim loop
    # in the same tick runs while the adjudication really is in flight.
    entered = threading.Event()
    release = threading.Event()

    def fake_verdict(*_args, **_kwargs):
        entered.set()
        assert release.wait(5)
        return _fake_graded()

    monkeypatch.setattr(track_daemon, "verdict", fake_verdict)
    monkeypatch.setattr(track_daemon.subprocess, "Popen",
                        lambda *a, **k: FakeProc(done=False))

    active = {finished.name: {"proc": FakeProc(done=True), "video": finished,
                              "log": log, "sport": "tennis",
                              "game_id": "finished", "started": (csv_dir / "tracking_data.csv").stat().st_mtime - 1}}
    track_daemon.tick(active, 1, adjudication_holds_slot)
    assert entered.wait(5), "the fake adjudicator never started"
    observed_active = len(active)

    release.set()
    for job in list(active.values()):
        adjudication = job.get("adjudication")
        if adjudication is not None:
            adjudication.join(5)
    track_daemon.tick(active, 1, adjudication_holds_slot)

    rows = [json.loads(line) for line
            in track_daemon.LEDGER.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 1, "expected exactly one ledger row, got %d" % len(rows)
    return observed_active, rows[0]


def test_uncapped_active_count_exceeds_workers_and_the_flag_stops_it(tmp_path, monkeypatch):
    """The premise on a construct, and the opt-in flag removing it."""
    uncapped_active, uncapped_row = _run_mode(
        tmp_path / "uncapped", monkeypatch, False)
    capped_active, capped_row = _run_mode(
        tmp_path / "capped", monkeypatch, True)

    # Default behaviour, unchanged: the adjudicating job freed its slot, so a
    # second clip was claimed on top of it at --workers 1.
    assert uncapped_active == 2 > 1

    # With the flag the adjudicating job keeps its slot, so nothing is claimed.
    assert capped_active == 1

    # B2: the ledger row is the same row either way.
    for field in _WALL_FIELDS:
        assert isinstance(uncapped_row.pop(field), int)
        assert isinstance(capped_row.pop(field), int)
    assert uncapped_row == capped_row
    assert uncapped_row["status"] == "tracked"
    assert uncapped_row["rows"] == _ROWS
    assert uncapped_row["adjudicated"] is True


def test_slots_in_use_defaults_to_todays_accounting():
    """The default must be the expression the daemon has always used."""
    active = {"a": {"adjudication": object()}, "b": {}, "c": {}}

    assert slots_in_use(active) == 2
    assert slots_in_use(active, False) == 2
    assert slots_in_use(active, True) == 3
    assert slots_in_use({}) == 0
    assert slots_in_use({}, True) == 0
