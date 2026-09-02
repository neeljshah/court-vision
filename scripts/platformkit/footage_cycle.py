"""Run a download, tracking, scoring, and cleanup cycle for footage queues."""
from __future__ import annotations

import argparse
import importlib
import json
import logging
import subprocess
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from scripts.platformkit.wnba_preflight import preflight as _wnba_preflight
except Exception:  # pragma: no cover
    _wnba_preflight = None

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
MAX_ITEM_SECONDS = 2400
TRACKING_LOCK = threading.Lock()
LOGGER = logging.getLogger(__name__)
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
    attempts = [
        ("default", ["-f", item["format"]]),
        # Standard yt-dlp workaround for YouTube bot-checks.
        ("android_web_safari", ["--extractor-args", "youtube:player_client=android,web_safari",
                                "-f", item["format"]]),
        ("tv", ["--extractor-args", "youtube:player_client=tv", "-f", item["format"]]),
        ("720p_mp4", ["--format-sort", "res,ext:mp4", "-f", "b[height<=720]"]),
    ]
    last_error = ""
    for rung, arguments in attempts:
        LOGGER.info("yt-dlp download rung=%s game_id=%s", rung, item.get("game_id", "unknown"))
        try:
            subprocess.run(
                command + arguments + [item["url"]],
                check=True,
                capture_output=True,
                text=True,
                timeout=MAX_ITEM_SECONDS,
            )
            if destination.exists():
                return destination
            # yt-dlp falls back to .mkv (and other containers) when the chosen
            # streams cannot be merged into mp4; the tracker then looks for a
            # file that does not exist and the GPU sits idle. Resolve the real
            # artifact. Regression note: this fix was silently dropped once by a
            # stale-worktree merge -- keep it inside the retry ladder.
            produced = sorted(
                (path for path in destination.parent.glob(destination.name + "*")
                 if path.is_file() and not path.name.endswith(".part")),
                key=lambda path: path.stat().st_size, reverse=True)
            if produced:
                return produced[0]
            last_error = "yt-dlp reported success but produced no file"
            continue
        except subprocess.TimeoutExpired as exc:
            last_error = str(getattr(exc, "stderr", "") or exc)
        except subprocess.CalledProcessError as exc:
            last_error = str(exc.stderr or exc)
    tail = last_error[-1000:].strip() or "no stderr captured"
    raise RuntimeError("yt-dlp failed after retry ladder; last stderr: %s" % tail)


def _normalize_tracking(frame: pd.DataFrame) -> pd.DataFrame:
    # ft_x/ft_y are NOT court feet. They are an affine rescale of map_2d pixel
    # space (unified_pipeline computes ft_x = (x2d / map_w) * 94.0), and map_2d
    # falls back to a hardcoded 940x500 when court rectification fails. Aliasing
    # them to the canonical x/y made identify_tracking_schema report NORMALIZED,
    # so tracking_harness scored image-affine pixels against court-feet gates
    # and every basketball/wnba report down this path passed on a fiction.
    # The harness must fail closed with coordinate_contract instead.
    aliases = {"player_id": "track_id"}
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
        # Sports whose adapter cannot honestly produce ball positions must be
        # asked for player-only tracking or they raise. adapter_run owns that
        # set; duplicating it here is how this caller silently broke when
        # soccer was added to it.
        from scripts.platformkit.adapter_run import (
            BALL_TELEMETRY_AVAILABLE,
            PLAYER_ONLY,
        )
        from scripts.platformkit.tracking_schema import write_ball_telemetry_declaration

        options = {"max_frames": 30000, "stride": 3}
        if sport in PLAYER_ONLY:
            options["player_only"] = True
        rows = getattr(module, SPORT_ADAPTERS[sport])().process_video(
            video, **options)
        module.write_csv(rows, output)
        write_ball_telemetry_declaration(output, sport, BALL_TELEMETRY_AVAILABLE[sport])
        return output
    if sport in {"basketball", "wnba"}:
        subprocess.run([
            sys.executable, "scripts/run_clip.py", "--video", str(video),
            "--game-id", item["game_id"], "--no-show", "--frames", "18000",
            "--data-dir", str(output_dir),
        ], check=True)
        if not output.is_file():
            raise FileNotFoundError("Basketball runner did not write %s" % output)
        from scripts.platformkit.adapter_run import BALL_TELEMETRY_AVAILABLE
        from scripts.platformkit.tracking_schema import write_ball_telemetry_declaration
        write_ball_telemetry_declaration(output, sport, BALL_TELEMETRY_AVAILABLE[sport])
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
                if item.get("sport") == "wnba" and _wnba_preflight is not None:
                    try:
                        result["preflight"] = _wnba_preflight(str(video)).get("verdict", "NA")
                    except Exception:  # pragma: no cover
                        result["preflight"] = "preflight_error"
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
