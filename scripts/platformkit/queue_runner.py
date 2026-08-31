"""Run multiple footage queues forever with one GPU worker."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Callable, Sequence

from scripts.platformkit import footage_cycle

TRACKING_DIR = Path("data/tracking")
PASS_SLEEP_SECONDS = 300
Cycle = Callable[..., list[dict[str, object]]]


def _load_queue(path: Path) -> list[dict[str, str]]:
    items = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("Queue must be a JSON list: %s" % path)
    return items


def run_pass(
    queue_paths: Sequence[Path],
    cycle: Cycle | None = None,
    tracking_dir: Path = TRACKING_DIR,
) -> None:
    """Run each queue in order, omitting games with completed tracking CSVs."""
    runner = cycle or footage_cycle.run_queue
    for queue_path in queue_paths:
        items = _load_queue(Path(queue_path))
        pending = [
            item for item in items
            if not (tracking_dir / item["game_id"] / "tracking_data.csv").is_file()
        ]
        skipped = len(items) - len(pending)
        print("queue=%s pending=%d skipped=%d" % (queue_path, len(pending), skipped))
        if pending:
            runner(pending, workers=1)


def run_forever(
    queue_paths: Sequence[Path],
    max_passes: int | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    cycle: Cycle | None = None,
    tracking_dir: Path = TRACKING_DIR,
) -> None:
    """Run full queue passes forever, or for max_passes when testing."""
    if max_passes is not None and max_passes < 0:
        raise ValueError("max_passes must be non-negative")
    passes = 0
    while max_passes is None or passes < max_passes:
        passes += 1
        print("pass=%d start queues=%d" % (passes, len(queue_paths)))
        run_pass(queue_paths, cycle, tracking_dir)
        print("pass=%d complete" % passes)
        if max_passes is None or passes < max_passes:
            sleep_fn(PASS_SLEEP_SECONDS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run footage queues sequentially forever")
    parser.add_argument("--queues", required=True, help="Comma-separated queue JSON paths")
    args = parser.parse_args()
    queue_paths = [Path(value.strip()) for value in args.queues.split(",") if value.strip()]
    if not queue_paths:
        raise ValueError("--queues must contain at least one path")
    run_forever(queue_paths)


if __name__ == "__main__":
    main()
