"""Focused coverage for the dependency-free pod supervisor."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from scripts.platformkit import pod_supervisor


def _spec(tmp_path: Path, name: str = "fake") -> pod_supervisor.Spec:
    return pod_supervisor.Spec(
        name,
        (sys.executable, "-c", "import sys; sys.exit(0)"),
        tmp_path / (name + ".log"),
    )


def test_dead_command_restarts_with_growing_backoff_and_ledger(tmp_path: Path) -> None:
    moment = [0.0]
    supervisor = pod_supervisor.PodSupervisor(
        [_spec(tmp_path)], workspace=tmp_path, report_path=tmp_path / "ledger.jsonl",
        proc_root=tmp_path / "proc", clock=lambda: moment[0],
    )
    supervisor.cycle()
    time.sleep(0.03)
    moment[0] = 30.0
    supervisor.cycle()
    time.sleep(0.03)
    moment[0] = 90.0
    supervisor.cycle()
    rows = [json.loads(line) for line in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert [row["restarts_total"] for row in rows] == [1, 2, 3]
    assert supervisor.next_restart["fake"] == 210.0
    assert all(row["action"] == "restart" for row in rows)


def test_long_lived_matching_process_is_not_restarted(tmp_path: Path) -> None:
    spec = _spec(tmp_path, "alive")
    proc = tmp_path / "proc" / "55"
    proc.mkdir(parents=True)
    (proc / "cmdline").write_bytes(b"python\x00" + spec.module_name.encode())
    supervisor = pod_supervisor.PodSupervisor(
        [spec], workspace=tmp_path, report_path=tmp_path / "ledger.jsonl", proc_root=tmp_path / "proc",
    )
    assert supervisor.cycle()[0]["live"] is True
    assert supervisor.restarts["alive"] == 0
    assert not (tmp_path / "ledger.jsonl").exists()


def test_status_skips_its_own_pid(tmp_path: Path) -> None:
    spec = _spec(tmp_path, "self")
    proc = tmp_path / "proc" / "77"
    proc.mkdir(parents=True)
    (proc / "cmdline").write_bytes(b"python\x00" + spec.module_name.encode())
    assert pod_supervisor.status([spec], tmp_path / "proc", self_pid=77) == [
        {"name": "self", "live": False, "pids": []}
    ]
