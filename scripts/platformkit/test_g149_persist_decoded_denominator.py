"""G149: successful daemon rows retain the decoder-backed frame denominator."""

from __future__ import annotations

import json
import time

from scripts.platformkit import track_daemon


def test_successful_row_persists_decoded_frames_without_rewriting_existing_fields(
    tmp_path, monkeypatch,
):
    ledger = tmp_path / "track_daemon_ledger.jsonl"
    tracking = tmp_path / "tracking"
    game_id = "g149_real_cycle_shape"
    output = tracking / game_id
    output.mkdir(parents=True)
    (output / "tracking_data.csv").write_text(
        "frame,track_id,cls,x,y\n0,1,player,1.0,2.0\n",
        encoding="utf-8",
    )
    log = tmp_path / "complete.log"
    log.write_text("completed", encoding="utf-8")
    monkeypatch.setattr(track_daemon, "LEDGER", ledger)
    monkeypatch.setattr(track_daemon, "TRACKING", tracking)
    monkeypatch.setattr(track_daemon, "CORPUS", tmp_path / "corpus")
    monkeypatch.setattr(track_daemon, "retain", lambda *_args: True)
    monkeypatch.setattr(
        track_daemon,
        "verdict",
        lambda *_args: {
            "passed": False,
            "failure_heads": ["coverage below frozen bar"],
            "coverage_pct": 0.25,
            "coordinate_space": "court_feet",
            "rung": "COURT_FEET",
            "evaluated_at": 123,
            "decoded_frames": 480,
        },
    )

    track_daemon._finish(
        "tennis__g149.mp4",
        {
            "game_id": game_id,
            "sport": "tennis",
            "video": tmp_path / "g149.mp4",
            "log": log,
            "started": time.time() - 2,
            "source": None,
        },
    )

    entry = json.loads(ledger.read_text(encoding="utf-8"))
    assert entry["decoded_frames"] == 480
    assert entry["status"] == "tracked"
    assert entry["adjudicated"] is True
    assert entry["rows"] == 1
    assert entry["passed"] is False
    assert entry["failure_heads"] == ["coverage below frozen bar"]
    assert entry["coverage_pct"] == 0.25
    assert entry["coordinate_space"] == "court_feet"
    assert entry["rung"] == "COURT_FEET"
    assert entry["evaluated_at"] == 123
