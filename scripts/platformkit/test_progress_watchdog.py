"""Focused tests for output-based footage progress recovery."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit import progress_watchdog


class _Supervisor:
    def __init__(self, **_kwargs) -> None:
        self.calls = 0

    def cycle(self):
        self.calls += 1
        return [{"name": "queue_runner_kbo", "live": True}]


def _snapshot(_root: Path) -> dict[str, object]:
    return {"tracked_games": 2, "ledger_lines": 4, "staged_bytes": 99,
            "newest_report_age_s": 1.0, "gpu_util": 0}


def test_fake_snapshots_classify_stalls_exactly_and_write_incident(tmp_path: Path) -> None:
    log = tmp_path / "data" / "ab_reports" / "foundry_runner.log"
    log.parent.mkdir(parents=True)
    log.write_text("\n".join("line%d" % value for value in range(25)), encoding="utf-8")
    watchdog = progress_watchdog.ProgressWatchdog(
        tmp_path, stall_after_s=0, snapshot_fn=_snapshot, supervisor_factory=_Supervisor,
    )
    assert [watchdog.cycle(), watchdog.cycle(), watchdog.cycle()] == ["INITIAL", "STALL", "STALL"]
    rows = [json.loads(line) for line in watchdog.report_path.read_text(encoding="utf-8").splitlines()]
    incident = [row for row in rows if row["action"] == "INCIDENT"]
    assert len(incident) == 1
    assert incident[0]["stalled_cycles"] == 2
    assert incident[0]["runner_logs"]["foundry_runner"] == ["line%d" % value for value in range(5, 25)]


def test_quarantine_moves_only_repeatedly_failed_ids(tmp_path: Path) -> None:
    data = tmp_path / "data"
    tracking = data / "tracking"
    tracking.mkdir(parents=True)
    (tracking / "footage_cycle_ledger.jsonl").write_text("\n".join(json.dumps(row) for row in [
        {"game_id": "kbo_bad", "status": "failed"},
        {"game_id": "kbo_bad", "status": "download_failed"},
        {"game_id": "kbo_once", "status": "failed"},
    ]), encoding="utf-8")
    queue = data / "footage_queue_kbo.json"
    queue.write_text(json.dumps([
        {"game_id": "kbo_bad", "sport": "kbo"},
        {"game_id": "kbo_once", "sport": "kbo"},
    ]), encoding="utf-8")
    assert progress_watchdog.quarantine_failures(tmp_path) == {"kbo": ["kbo_bad"]}
    assert [row["game_id"] for row in json.loads(queue.read_text(encoding="utf-8"))] == ["kbo_once"]
    quarantine = data / "footage_queue_kbo_quarantine.json"
    assert [row["game_id"] for row in json.loads(quarantine.read_text(encoding="utf-8"))] == ["kbo_bad"]


def test_empty_queue_invokes_expander(monkeypatch, tmp_path: Path) -> None:
    queue = tmp_path / "data" / "footage_queue_kbo.json"
    queue.parent.mkdir(parents=True)
    queue.write_text("[]", encoding="utf-8")
    calls = []
    monkeypatch.setattr(progress_watchdog.queue_expander, "expand_queue",
                        lambda sport, urls: calls.append((sport, tuple(urls))) or [])
    watchdog = progress_watchdog.ProgressWatchdog(
        tmp_path, stall_after_s=0, snapshot_fn=_snapshot, supervisor_factory=_Supervisor,
    )
    watchdog.cycle()
    assert watchdog.cycle() == "STALL"
    assert calls == [("kbo", progress_watchdog.queue_expander.SOURCES["kbo"])]


def test_snapshot_counts_only_usable_games_and_both_ledgers(tmp_path):
    """Thin CSVs are not tracked games, and both ledger producers are read."""
    tracking = tmp_path / "data" / "tracking"
    (tracking / "real_game").mkdir(parents=True)
    (tracking / "thin_game").mkdir(parents=True)
    header = "frame,track_id,cls,x,y\n"
    (tracking / "real_game" / "tracking_data.csv").write_text(
        header + "".join("%d,1,player,1,1\n" % i for i in range(900)), encoding="utf-8")
    (tracking / "thin_game" / "tracking_data.csv").write_text(
        header + "".join("%d,1,player,1,1\n" % i for i in range(103)), encoding="utf-8")
    (tracking / "footage_cycle_ledger.jsonl").write_text('{"a":1}\n', encoding="utf-8")
    (tracking / "footage_bridge_ledger.jsonl").write_text('{"b":2}\n{"c":3}\n',
                                                          encoding="utf-8")

    snap = progress_watchdog.snapshot(tmp_path)

    assert snap["tracked_games"] == 1, "the 103-row game must not count as tracked"
    assert snap["ledger_lines"] == 3, "both ledger producers must be counted"
