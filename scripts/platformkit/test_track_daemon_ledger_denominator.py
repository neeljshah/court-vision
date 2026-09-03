"""Mixed-schema compatibility coverage for G56's additive daemon ledger fields."""

import csv
import json
import time

from scripts.platformkit import track_daemon
from scripts.platformkit.night_report import build_report
from scripts.platformkit.track_daemon_ledger import corrupt_entry


def _tracking_output(directory, game_id, rows, fresh_solves):
    output = directory / game_id
    output.mkdir(parents=True)
    (output / "tracking_data.csv").write_text(
        "frame,track_id,cls,x,y\n" + "0,1,player,1,1\n" * rows,
        encoding="utf-8",
    )
    with (output / "frame_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("frame", "fresh_solve_count"))
        writer.writeheader()
        writer.writerows({"frame": frame, "fresh_solve_count": fresh_solves}
                         for frame in range(100))


def test_ledger_denominators_are_additive_and_old_rows_still_report(tmp_path, monkeypatch):
    ledger = tmp_path / "track_daemon_ledger.jsonl"
    tracking = tmp_path / "tracking"
    monkeypatch.setattr(track_daemon, "LEDGER", ledger)
    monkeypatch.setattr(track_daemon, "TRACKING", tracking)
    monkeypatch.setattr(track_daemon, "CORPUS", tmp_path / "corpus")
    monkeypatch.setattr(track_daemon, "retain", lambda *_args: True)

    old_row = {"game_id": "legacy", "sport": "tennis", "status": "tracked",
               "rows": 1000, "passed": True, "failures": [], "seconds": 1}
    track_daemon._record(old_row)
    track_daemon._record(corrupt_entry("bad", "baseball", 10, retained=True))

    source = {"source_fps": 30.0, "source_width": 1920, "source_height": 1080,
              "source_resolution": "1920x1080", "source_duration": 4.0}
    for game_id, rows, fresh_solves in (("normal", 600, 3), ("collapse", 10, 1)):
        _tracking_output(tracking, game_id, rows, fresh_solves)
        log = tmp_path / (game_id + ".log")
        log.write_text("timed out", encoding="utf-8")
        track_daemon._finish(game_id, {"game_id": game_id, "sport": "tennis",
                                      "video": tmp_path / (game_id + ".mp4"),
                                      "log": log, "started": time.time() - 1,
                                      "source": source}, timed_out=True)

    entries = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    newly_written = entries[1:]
    assert all({"decoded_frames", "evaluated_frames", "stride", "harness_coverage_pct",
                "source_resolution", "fresh_solves"} <= entry.keys()
               for entry in newly_written)
    assert entries[0] == old_row
    assert entries[2]["decoded_frames"] == 100
    assert entries[2]["source_resolution"] == "1920x1080"
    assert entries[2]["fresh_solves"] == 3
    marker = entries[3]["rows_per_decoded_frame_step_change"]
    assert marker["previous_game_id"] == "normal"
    assert marker["direction"] == "decrease"
    assert marker["factor"] > track_daemon.ROW_DENSITY_STEP_FACTOR

    report = build_report(ledger, tmp_path / "missing-bridge.jsonl",
                          tmp_path / "missing-supervisor.json")
    assert "tennis: tracked=1 thin=0 PASSING=1 best_rows=1000" in report
