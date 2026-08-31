"""Focused tests for sequential, resumable footage queue processing."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit import queue_runner


def _write_queue(path: Path, game_ids: list[str]) -> None:
    items = [
        {"game_id": game_id, "sport": "tennis", "url": "x", "format": "direct"}
        for game_id in game_ids
    ]
    path.write_text(json.dumps(items), encoding="utf-8")


def test_run_pass_is_sequential_and_skips_existing(tmp_path: Path) -> None:
    queue_one = tmp_path / "one.json"
    queue_two = tmp_path / "two.json"
    _write_queue(queue_one, ["one_pending", "one_done"])
    _write_queue(queue_two, ["two_pending"])
    tracking_dir = tmp_path / "tracking"
    done_csv = tracking_dir / "one_done" / "tracking_data.csv"
    done_csv.parent.mkdir(parents=True)
    done_csv.write_text("done", encoding="utf-8")
    calls: list[tuple[list[str], int]] = []

    def fake_cycle(items: list[dict[str, str]], workers: int) -> list[dict[str, object]]:
        calls.append(([item["game_id"] for item in items], workers))
        return []

    queue_runner.run_pass(
        [queue_one, queue_two], fake_cycle, tracking_dir
    )

    assert calls == [(["one_pending"], 1), (["two_pending"], 1)]


def test_run_forever_honors_max_passes(tmp_path: Path) -> None:
    queue_path = tmp_path / "queue.json"
    _write_queue(queue_path, ["pending"])
    calls: list[str] = []
    sleeps: list[float] = []

    def fake_cycle(items: list[dict[str, str]], workers: int) -> list[dict[str, object]]:
        calls.extend(item["game_id"] for item in items)
        return []

    queue_runner.run_forever(
        [queue_path],
        max_passes=2,
        sleep_fn=sleeps.append,
        cycle=fake_cycle,
        tracking_dir=tmp_path / "tracking",
    )

    assert calls == ["pending", "pending"]
    assert sleeps == [300]
