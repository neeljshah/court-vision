"""Run a download, tracking, scoring, and cleanup cycle for footage queues."""
from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from scripts.platformkit.io_atomic import append_jsonl_atomic, write_json_atomic
from scripts.platformkit.provenance import record_provenance
from scripts.platformkit.demo_render import render_csv
from scripts.platformkit.tracking_harness import evaluate

DATA_DIR = Path("data")
DOWNLOAD_DIR = DATA_DIR / "footage"
TRACKING_DIR = DATA_DIR / "tracking"
LEDGER_PATH = TRACKING_DIR / "footage_cycle_ledger.jsonl"
DEMO_DIR = Path("docs/evidence/demos")
COOKIES_PATH = Path("cookies.txt")
TRACKING_LOCK = threading.Lock()
SPORT_ADAPTERS = {
    "tennis": "TennisAdapter",
    "soccer": "SoccerAdapter",
    "baseball": "BaseballAdapter",
}


def _video_path(item: dict[str, str]) -> Path:
    """Return the temporary local video path for one queue item."""
    suffix = Path(item["url"].split("?", 1)[0]).suffix or ".mp4"
    return DOWNLOAD_DIR / (item["game_id"] + suffix)


def download_item(item: dict[str, str], destination: Path) -> Path:
    """Download one queue item with yt-dlp or urllib for direct URLs."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if item.get("format") == "direct":
        urllib.request.urlretrieve(item["url"], destination)
        return destination
    command = ["yt-dlp", "-o", str(destination)]
    if COOKIES_PATH.is_file():
        command.extend(["--cookies", str(COOKIES_PATH)])
    command.extend(["-f", item["format"], item["url"]])
    subprocess.run(command, check=True)
    return destination


def _normalize_tracking(frame: pd.DataFrame) -> pd.DataFrame:
    aliases = {"player_id": "track_id", "ft_x": "x", "ft_y": "y"}
    normalized = frame.rename(columns={key: value for key, value in aliases.items()
                                       if key in frame and value not in frame})
    if "cls" not in normalized:
        normalized = normalized.assign(cls="player")
    return normalized


def track_item(item: dict[str, str], video: Path) -> Path:
    """Track a downloaded video and return its normalized CSV path."""
    sport = item["sport"].lower()
    output_dir = TRACKING_DIR / item["game_id"]
    output = output_dir / "tracking_data.csv"
    output_dir.mkdir(parents=True, exist_ok=True)
    if sport in SPORT_ADAPTERS:
        module = importlib.import_module("domains.%s.tracking.adapter" % sport)
        rows = getattr(module, SPORT_ADAPTERS[sport])().process_video(
            video, max_frames=30000, stride=3)
        module.write_csv(rows, output)
        return output
    if sport in {"basketball", "wnba"}:
        subprocess.run([
            sys.executable, "scripts/run_clip.py", "--video", str(video),
            "--game-id", item["game_id"], "--no-show", "--frames", "18000",
            "--data-dir", str(output_dir),
        ], check=True)
        if not output.is_file():
            raise FileNotFoundError("Basketball runner did not write %s" % output)
        return output
    raise ValueError("Unsupported sport: %s" % sport)


def _adapter_module(item: dict[str, str]) -> str:
    """Return the adapter identity recorded for a queue item."""
    if item.get("adapter_module"):
        return item["adapter_module"]
    sport = item["sport"].lower()
    if sport in SPORT_ADAPTERS:
        return "domains.%s.tracking.adapter" % sport
    if sport in {"basketball", "wnba"}:
        return "scripts.run_clip"
    return "unknown"


def score_item(item: dict[str, str], tracking_csv: Path) -> dict[str, Any]:
    """Evaluate tracking quality and persist the report and cycle ledger row."""
    sport = "basketball" if item["sport"].lower() == "wnba" else item["sport"].lower()
    report = asdict(evaluate(_normalize_tracking(pd.read_csv(tracking_csv)), sport))
    report.update({"game_id": item["game_id"], "status": "ok"})
    report_path = tracking_csv.with_name("quality_report.json")
    write_json_atomic(report_path, report, indent=2, trailing_newline=True)
    append_jsonl_atomic(LEDGER_PATH, report)
    try:
        stem = "%s_demo" % item["game_id"]
        render_csv(
            tracking_csv,
            item["sport"].lower(),
            out_path=DEMO_DIR / (stem + ".mp4"),
            gif_path=DEMO_DIR / (stem + ".gif"),
            max_seconds=15,
        )
    except Exception as exc:
        failure = {"game_id": item["game_id"], "status": "demo_failed", "error": str(exc)}
        try:
            append_jsonl_atomic(LEDGER_PATH, failure)
        except Exception as ledger_exc:
            print("%s demo_failed ledger_error=%s" % (item["game_id"], ledger_exc))
    return report


def _run_item(item: dict[str, str]) -> dict[str, Any]:
    video = _video_path(item)
    result: dict[str, Any] = {"game_id": item.get("game_id"), "sport": item.get("sport")}
    try:
        try:
            download_item(item, video)
        except Exception as exc:
            result.update(status="download_failed", error=str(exc))
            return result
        try:
            record_provenance(
                item["game_id"], item["sport"], item["url"], video,
                _adapter_module(item),
            )
            with TRACKING_LOCK:
                tracking_csv = track_item(item, video)
            result.update(score_item(item, tracking_csv))
            return result
        except Exception as exc:
            result.update(status="failed", error=str(exc))
            return result
    finally:
        video.unlink(missing_ok=True)


def run_queue(items: list[dict[str, str]], workers: int = 3) -> list[dict[str, Any]]:
    """Run queued downloads concurrently while serializing GPU tracking work."""
    if workers <= 1:
        # LOCKSTEP: download->track->score->delete per item before the next
        # download starts. Prevents the staging pileup that maxed the volume
        # twice on 2026-08-31 (downloads outpace tracking ~4:1).
        return [_run_item(item) for item in items]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run_item, item) for item in items]
        return [future.result() for future in as_completed(futures)]


def main(queue_path: Path, workers: int = 3) -> list[dict[str, Any]]:
    """Load and execute a footage queue JSON file."""
    items = json.loads(queue_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("Queue must be a JSON list")
    results = run_queue(items, workers)
    for result in results:
        print("%s %s" % (result["game_id"], result["status"]))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a footage tracking cycle")
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    main(args.queue, args.workers)
