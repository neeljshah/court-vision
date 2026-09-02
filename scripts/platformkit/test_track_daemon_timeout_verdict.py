"""G55 regression coverage for explicit daemon timeout ledger verdicts."""

import json
import time

from scripts.platformkit import track_daemon


def test_timeout_entry_has_additive_explicit_timeout_verdict(tmp_path, monkeypatch):
    """A killed job stays distinct from a zero-row ordinary completion."""
    ledger = tmp_path / "track_daemon_ledger.jsonl"
    monkeypatch.setattr(track_daemon, "LEDGER", ledger)
    monkeypatch.setattr(track_daemon, "TRACKING", tmp_path / "tracking")
    monkeypatch.setattr(track_daemon, "CORPUS", tmp_path / "corpus")
    monkeypatch.setattr(track_daemon, "retain", lambda *_args: True)
    log = tmp_path / "job.log"
    log.write_text("killed after deadline", encoding="utf-8")
    job = {"game_id": "tennis_timeout", "sport": "tennis",
           "video": tmp_path / "tennis_timeout.mp4", "log": log,
           "started": time.time() - 10}

    track_daemon._finish("tennis_timeout", job, timed_out=True)

    entry = json.loads(ledger.read_text(encoding="utf-8"))
    assert entry["status"] == "timeout"
    assert entry["verdict"] == "TIMEOUT"
    assert entry["rows"] == 0
    assert entry["adjudicated"] is False
