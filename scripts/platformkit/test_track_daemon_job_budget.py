"""Regression coverage for G73's global scheduling budget."""

import json
import time

from scripts.platformkit import track_daemon


class _RunningProcess:
    def __init__(self):
        self.killed = False

    def poll(self):
        return None

    def kill(self):
        self.killed = True


def test_job_past_global_budget_writes_g55_timeout_verdict(tmp_path, monkeypatch):
    """A global-budget overrun still takes G55's explicit timeout path."""
    stage = tmp_path / "stage"
    stage.mkdir()
    ledger = tmp_path / "track_daemon_ledger.jsonl"
    log = tmp_path / "tennis_timeout.log"
    log.write_text("past global budget", encoding="utf-8")
    process = _RunningProcess()
    monkeypatch.setattr(track_daemon, "STAGE", stage)
    monkeypatch.setattr(track_daemon, "LEDGER", ledger)
    monkeypatch.setattr(track_daemon, "TRACKING", tmp_path / "tracking")
    monkeypatch.setattr(track_daemon, "CORPUS", tmp_path / "corpus")
    monkeypatch.setattr(track_daemon, "retain", lambda *_args: True)

    active = {"tennis_timeout.mp4": {
        "proc": process, "video": tmp_path / "tennis_timeout.mp4", "log": log,
        "sport": "tennis", "game_id": "tennis_timeout",
        "started": time.time() - track_daemon.JOB_TIMEOUT_SECONDS - 1,
    }}
    track_daemon.tick(active, workers=0)

    entry = json.loads(ledger.read_text(encoding="utf-8"))
    assert track_daemon.JOB_TIMEOUT_SECONDS == 12_000
    assert process.killed is True
    assert entry["status"] == "timeout"
    assert entry["verdict"] == "TIMEOUT"
