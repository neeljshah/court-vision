"""Watch footage output and recover queues that stop making progress."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from scripts.platformkit import pod_supervisor, queue_expander


def snapshot(root: Path) -> dict[str, object]:
    """Return a compact, output-focused view of footage processing progress."""
    data = root / "data"
    tracking = data / "tracking"
    ledger = tracking / "footage_cycle_ledger.jsonl"
    footage = data / "footage"
    reports = data / "ab_reports"
    tracked = sum(1 for _ in tracking.glob("*/tracking_data.csv")) if tracking.is_dir() else 0
    ledger_lines = len(ledger.read_text(encoding="utf-8").splitlines()) if ledger.is_file() else 0
    staged_bytes = sum(path.stat().st_size for path in footage.rglob("*") if path.is_file()) if footage.is_dir() else 0
    report_files = [path for path in reports.rglob("*") if path.is_file()] if reports.is_dir() else []
    newest_report_age_s = None
    if report_files:
        newest_report_age_s = max(0.0, time.time() - max(path.stat().st_mtime for path in report_files))
    gpu_util = _gpu_util()
    return {
        "tracked_games": tracked,
        "ledger_lines": ledger_lines,
        "staged_bytes": staged_bytes,
        "newest_report_age_s": newest_report_age_s,
        "gpu_util": gpu_util,
    }


def _gpu_util() -> int | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    values = []
    for line in result.stdout.splitlines():
        try:
            values.append(int(line.strip()))
        except ValueError:
            pass
    return max(values) if values else None


def _read_json(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("Queue must be a JSON list: %s" % path)
    return [item for item in value if isinstance(item, dict)]


def _write_json(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _failure_ids(ledger_path: Path) -> set[str]:
    counts: dict[str, int] = {}
    if not ledger_path.is_file():
        return set()
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        game_id = row.get("game_id")
        if game_id and row.get("status") in {"failed", "download_failed"}:
            counts[str(game_id)] = counts.get(str(game_id), 0) + 1
    return {game_id for game_id, count in counts.items() if count >= 2}


def quarantine_failures(root: Path) -> dict[str, list[str]]:
    """Move repeatedly failed queue records to per-sport quarantine files."""
    data = root / "data"
    failures = _failure_ids(data / "tracking" / "footage_cycle_ledger.jsonl")
    moved: dict[str, list[str]] = {}
    for queue_path in sorted(data.glob("footage_queue_*.json")):
        sport = queue_path.stem.removeprefix("footage_queue_")
        items = _read_json(queue_path)
        bad = [item for item in items if str(item.get("game_id", "")) in failures]
        if not bad:
            continue
        _write_json(queue_path, [item for item in items if item not in bad])
        quarantine = data / ("footage_queue_%s_quarantine.json" % sport)
        existing = _read_json(quarantine)
        known = {str(item.get("game_id", "")) for item in existing}
        existing.extend(item for item in bad if str(item.get("game_id", "")) not in known)
        _write_json(quarantine, existing)
        moved[sport] = [str(item["game_id"]) for item in bad]
    return moved


class ProgressWatchdog:
    """Escalate from stale output to queue recovery, loop recovery, and incident logs."""

    def __init__(
        self, root: Path = Path("."), interval_s: float = 600, stall_after_s: float = 1800,
        snapshot_fn: Callable[[Path], dict[str, object]] = snapshot,
        supervisor_factory: Callable[..., pod_supervisor.PodSupervisor] = pod_supervisor.PodSupervisor,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.root, self.interval_s, self.stall_after_s = Path(root), interval_s, stall_after_s
        self.snapshot_fn, self.clock = snapshot_fn, clock
        specs = pod_supervisor.build_specs(self.root / "data")
        self.specs = specs
        self.supervisor = supervisor_factory(
            specs=specs, workspace=self.root,
            report_path=self.root / "data" / "ab_reports" / "pod_supervisor.jsonl",
        )
        self.previous: dict[str, object] | None = None
        self.last_progress = clock()
        self.stalled_cycles = 0
        self.report_path = self.root / "data" / "ab_reports" / "progress_watchdog.jsonl"

    def _record(self, action: str, **fields: object) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        row = {"ts": datetime.now(timezone.utc).isoformat(), "action": action, **fields}
        with self.report_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    def _expand_empty_queues(self) -> list[str]:
        expanded = []
        for path in sorted((self.root / "data").glob("footage_queue_*.json")):
            sport = path.stem.removeprefix("footage_queue_")
            if _read_json(path):
                continue
            if sport not in queue_expander.SOURCES:
                self._record("expand_queue_skipped", sport=sport, reason="no_source")
                continue
            queue_expander.expand_queue(sport, queue_expander.SOURCES[sport])
            self._record("expand_queue", sport=sport)
            expanded.append(sport)
        return expanded

    def _incident(self) -> None:
        logs = {}
        for spec in self.specs:
            path = spec.log if spec.log.is_absolute() else self.root / spec.log
            logs[spec.name] = path.read_text(encoding="utf-8", errors="replace").splitlines()[-20:] if path.is_file() else []
        self._record("INCIDENT", stalled_cycles=self.stalled_cycles, runner_logs=logs)

    def cycle(self) -> str:
        """Take one snapshot and run the escalation ladder after an eligible stall."""
        current = self.snapshot_fn(self.root)
        if self.previous is None:
            self.previous = current
            self._record("INITIAL", snapshot=current)
            return "INITIAL"
        progressed = any(current[key] > self.previous[key] for key in ("tracked_games", "ledger_lines"))
        self.previous = current
        if progressed:
            self.last_progress, self.stalled_cycles = self.clock(), 0
            self._record("PROGRESS", snapshot=current)
            return "PROGRESS"
        self._record("STALL", snapshot=current)
        if self.clock() - self.last_progress < self.stall_after_s:
            return "STALL"
        moved = quarantine_failures(self.root)
        self._record("quarantine", moved=moved)
        expanded = self._expand_empty_queues()
        self._record("expand_empty_queues", expanded=expanded)
        rows = self.supervisor.cycle()
        self._record("restart_dead_loops", rows=rows, expanded=expanded)
        self.stalled_cycles += 1
        if self.stalled_cycles >= 2:
            self._incident()
        return "STALL"

    def watch(self, max_cycles: int | None = None, sleep: Callable[[float], None] = time.sleep) -> None:
        """Run bounded or continuous output-progress checks."""
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            print("classification=%s" % self.cycle())
            cycles += 1
            if max_cycles is None or cycles < max_cycles:
                sleep(self.interval_s)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Watch platform output progress")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--max-cycles", type=int)
    parser.add_argument("--interval-s", type=float, default=600)
    parser.add_argument("--stall-after-s", type=float, default=1800)
    args = parser.parse_args(argv)
    ProgressWatchdog(interval_s=args.interval_s, stall_after_s=args.stall_after_s).watch(
        max_cycles=1 if args.once else args.max_cycles)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
