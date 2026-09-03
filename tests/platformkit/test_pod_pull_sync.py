"""Focused durability checks for the pod-to-local pull helper."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_pod_pull_sync_reports_each_failed_target(tmp_path: Path) -> None:
    """An unreachable endpoint must make a one-pass pull fail visibly."""
    repository = Path(__file__).resolve().parents[2]
    script = repository / "scripts" / "platformkit" / "pod_pull_sync.sh"
    environment = os.environ.copy()
    environment.update(
        {
            "CV_POD_HOST": "127.0.0.1",
            "CV_POD_PORT": "1",
            "POD_SYNC_DST": tmp_path.as_posix(),
        }
    )

    completed = subprocess.run(
        ["bash", str(script)],
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode != 0
    assert "pod_pull_sync: WARN " in completed.stderr
    assert "pod_pull_sync: pass INCOMPLETE" in completed.stdout
    assert "pod_pull_sync: pass complete" not in completed.stdout

    scp_lines = [
        line
        for line in script.read_text(encoding="utf-8").splitlines()
        if "scp " in line and not line.lstrip().startswith("#")
    ]
    assert len(scp_lines) == 8
    assert all("2>/dev/null" not in line for line in scp_lines)
