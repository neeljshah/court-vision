"""Keep the pod's independent long-running platformkit loops alive."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence


WORKSPACE = Path("/workspace/nba-ai-system")
DATA_DIR = Path("data")
REPORT_PATH = DATA_DIR / "ab_reports" / "pod_supervisor.jsonl"
MIN_BACKOFF_SECONDS = 30.0
MAX_BACKOFF_SECONDS = 600.0
CYCLE_SECONDS = 60.0


@dataclass(frozen=True)
class Spec:
    """One detached pod worker that should be kept alive."""

    name: str
    argv: tuple[str, ...]
    log: Path

    @property
    def module_name(self) -> str:
        try:
            return self.argv[self.argv.index("-m") + 1]
        except (ValueError, IndexError):
            return self.argv[0]


def build_specs(data_dir: Path = DATA_DIR) -> list[Spec]:
    """Return the fixed loops plus one worker for every footage queue file."""
    python = sys.executable
    specs = [
        Spec("foundry_runner", (python, "-m", "scripts.platformkit.foundry_runner"),
             data_dir / "ab_reports" / "foundry_runner.log"),
        Spec("retrain_loop", (python, "-m", "scripts.platformkit.retrain_loop"),
             data_dir / "ab_reports" / "retrain_loop.log"),
    ]
    for queue_path in sorted(data_dir.glob("footage_queue_*.json")):
        name = "queue_runner_" + queue_path.stem.removeprefix("footage_queue_")
        specs.append(Spec(
            name,
            (python, "-m", "scripts.platformkit.queue_runner", "--queues", str(queue_path)),
            data_dir / "ab_reports" / (name + ".log"),
        ))
    return specs


SPECS = build_specs()


def status(
    specs: Iterable[Spec] = SPECS,
    proc_root: Path = Path("/proc"),
    self_pid: int | None = None,
) -> list[dict[str, object]]:
    """Return liveness rows by reading proc cmdlines without pattern matching."""
    current_pid = os.getpid() if self_pid is None else self_pid
    rows = []
    for spec in specs:
        pids = []
        if proc_root.is_dir():
            for entry in proc_root.iterdir():
                if not entry.name.isdigit() or int(entry.name) == current_pid:
                    continue
                try:
                    command = (entry / "cmdline").read_bytes().decode("utf-8", "replace")
                except OSError:
                    continue
                if spec.module_name in command:
                    pids.append(int(entry.name))
        rows.append({"name": spec.name, "live": bool(pids), "pids": pids})
    return rows


class PodSupervisor:
    """Monitor worker specs and relaunch dead workers with per-worker backoff."""

    def __init__(
        self,
        specs: Sequence[Spec] = SPECS,
        workspace: Path = WORKSPACE,
        report_path: Path = REPORT_PATH,
        proc_root: Path = Path("/proc"),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.specs = list(specs)
        self.workspace = workspace
        self.report_path = report_path
        self.proc_root = proc_root
        self.clock = clock
        self.restarts: dict[str, int] = {spec.name: 0 for spec in self.specs}
        self.next_restart: dict[str, float] = {spec.name: 0.0 for spec in self.specs}

    def _launch(self, spec: Spec) -> None:
        spec.log.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        previous = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(self.workspace) + (os.pathsep + previous if previous else "")
        with spec.log.open("ab") as output:
            subprocess.Popen(
                spec.argv,
                cwd=self.workspace,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

    def _record_restart(self, spec: Spec) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "name": spec.name,
            "action": "restart",
            "restarts_total": self.restarts[spec.name],
        }
        with self.report_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    def cycle(self) -> list[dict[str, object]]:
        """Check every spec once and relaunch only when its backoff permits it."""
        rows = status(self.specs, self.proc_root)
        now = self.clock()
        for spec, row in zip(self.specs, rows):
            if row["live"] or now < self.next_restart[spec.name]:
                continue
            self._launch(spec)
            self.restarts[spec.name] += 1
            delay = min(MAX_BACKOFF_SECONDS, MIN_BACKOFF_SECONDS * 2 ** (self.restarts[spec.name] - 1))
            self.next_restart[spec.name] = now + delay
            self._record_restart(spec)
        for row in rows:
            row["restarts_total"] = self.restarts[str(row["name"])]
        return rows

    def run(self, max_cycles: int | None = None, sleep: Callable[[float], None] = time.sleep) -> None:
        """Run supervisor cycles until stopped or bounded for testing."""
        if max_cycles is not None and max_cycles < 0:
            raise ValueError("max_cycles must be non-negative")
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            for row in self.cycle():
                print("name={0} live={1} pids={2} restarts={3}".format(
                    row["name"], row["live"], row["pids"], row["restarts_total"]))
            cycles += 1
            if max_cycles is None or cycles < max_cycles:
                sleep(CYCLE_SECONDS)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the pod keep-alive loop."""
    parser = argparse.ArgumentParser(description="Keep pod platformkit loops alive")
    parser.add_argument("--max-cycles", type=int)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    max_cycles = 1 if args.once else args.max_cycles
    PodSupervisor().run(max_cycles=max_cycles)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
