"""Regression tests for verdict-defined daemon completion."""
from __future__ import annotations

import json
from dataclasses import dataclass

from scripts.platformkit import track_daemon
from scripts.platformkit.track_daemon_done import adjudicate, read_adjudicated


@dataclass
class FakeReport:
    passed: bool
    failures: list[str]


class DoneProc:
    def poll(self):
        return 0


def _paths(tmp_path, monkeypatch):
    stage = tmp_path / "stage"
    stage.mkdir()
    monkeypatch.setattr(track_daemon, "STAGE", stage)
    monkeypatch.setattr(track_daemon, "CORPUS", tmp_path / "corpus")
    monkeypatch.setattr(track_daemon, "QUARANTINE", tmp_path / "quarantine")
    monkeypatch.setattr(track_daemon, "TRACKING", tmp_path / "tracking")
    monkeypatch.setattr(track_daemon, "LEDGER", tmp_path / "ledger.jsonl")
    return stage


def _csv(tracking, game_id, contents):
    path = tracking / game_id / "tracking_data.csv"
    path.parent.mkdir(parents=True)
    path.write_text(contents, encoding="utf-8")
    return path


def test_no_verdict_is_not_done_and_footage_stays_staged(tmp_path, monkeypatch):
    stage = _paths(tmp_path, monkeypatch)
    video = stage / "tennis__missing.mp4"
    video.write_bytes(b"x" * (track_daemon.MIN_VIDEO_BYTES + 1))
    _csv(track_daemon.TRACKING, "missing", "frame,track_id,cls,x,y\n0,1,player,1,1\n")
    launched = []
    monkeypatch.setattr(track_daemon.subprocess, "Popen",
                        lambda *args, **kwargs: launched.append(args) or DoneProc())

    track_daemon.tick({}, workers=1)

    assert launched and video.exists()
    assert read_adjudicated(track_daemon.TRACKING, "missing") is None


def test_failed_harness_verdict_is_done_and_durable(tmp_path, monkeypatch):
    stage = _paths(tmp_path, monkeypatch)
    video = stage / "tennis__failed.mp4"
    video.write_bytes(b"x" * (track_daemon.MIN_VIDEO_BYTES + 1))
    log = stage / "tennis__failed.log"
    log.write_text("finished", encoding="utf-8")
    _csv(track_daemon.TRACKING, "failed", "frame,track_id,cls,x,y,coordinate_space\n"
         "0,1,player,1,1,court_feet\n1,1,player,2,1,court_feet\n")
    seen = {}

    def fake_harness(frame, sport, source):
        seen["frames"] = frame["frame"].nunique()
        seen["sport"] = sport
        return FakeReport(False, ["coverage 0.00 < 0.90"])

    monkeypatch.setattr(
        track_daemon, "verdict",
        lambda sport, game_id, source: adjudicate(
            source, sport, game_id, track_daemon.TRACKING, fake_harness, lambda _: 4))
    active = {video.name: {"proc": DoneProc(), "video": video, "log": log,
                           "sport": "tennis", "game_id": "failed", "started": 0}}

    track_daemon.tick(active, workers=1)

    sidecar = read_adjudicated(track_daemon.TRACKING, "failed")
    ledger = json.loads(track_daemon.LEDGER.read_text(encoding="utf-8"))
    assert seen == {"frames": 4, "sport": "tennis"}
    assert sidecar and sidecar["passed"] is False
    assert {"passed", "failure_heads", "coverage_pct", "coordinate_space", "rung",
            "evaluated_at"} <= sidecar.keys()
    assert ledger["status"] == "tracked" and ledger["passed"] is False
    assert ledger["adjudicated"] is True and ledger["failures"] == ledger["failure_heads"]
    assert not video.exists() and (track_daemon.CORPUS / video.name).exists()


def test_empty_csv_is_unadjudicated_and_footage_is_never_deleted(tmp_path, monkeypatch):
    stage = _paths(tmp_path, monkeypatch)
    video = stage / "tennis__empty.mp4"
    video.write_bytes(b"x" * (track_daemon.MIN_VIDEO_BYTES + 1))
    log = stage / "tennis__empty.log"
    log.write_text("no output", encoding="utf-8")
    _csv(track_daemon.TRACKING, "empty", "")
    active = {video.name: {"proc": DoneProc(), "video": video, "log": log,
                           "sport": "tennis", "game_id": "empty", "started": 0}}

    track_daemon.tick(active, workers=1)

    ledger = json.loads(track_daemon.LEDGER.read_text(encoding="utf-8"))
    assert ledger["status"] == "thin" and ledger["adjudicated"] is False
    assert read_adjudicated(track_daemon.TRACKING, "empty") is None
    assert (track_daemon.CORPUS / video.name).exists()


def test_every_acquisition_label_maps_to_a_sport_the_harness_knows():
    """No staged game may reach the harness under its acquisition lane name.

    The regression: only the basketball feeders were folded, so `mlb` went to
    the harness raw and came back "unknown sport mlb". The first MLB game
    tracked after the footage bridge was repaired was never quality scored --
    it produced 78,315 rows and no verdict. `kbo` and `npb` survived only
    because tracking_harness.SPORTS happens to carry them as byte-identical
    aliases of baseball, which is luck, not routing.
    """
    from scripts.platformkit.track_daemon import CLIP_SPORTS, SPORT_ADAPTER
    from scripts.platformkit.track_daemon_done import HARNESS_SPORT
    from scripts.platformkit.tracking_harness import SPORTS

    for label in set(SPORT_ADAPTER) | CLIP_SPORTS:
        assert label in HARNESS_SPORT, "acquisition label %r has no harness sport" % label
        assert HARNESS_SPORT[label] in SPORTS, (
            "%r maps to %r which the harness does not score" % (label, HARNESS_SPORT[label]))

    assert HARNESS_SPORT["mlb"] == "baseball"
    assert HARNESS_SPORT["ncaa_basketball"] == "basketball"
