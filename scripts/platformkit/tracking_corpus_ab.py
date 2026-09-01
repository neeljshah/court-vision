"""Bounded corpus tracking measurement with per-game baseline diffs.

Run on the pod from the repository root:
  nice -n 10 python -m scripts.platformkit.tracking_corpus_ab tennis --games 3
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from scripts.platformkit.adapter_run import ADAPTERS
from scripts.platformkit.tracking_harness import evaluate
from scripts.platformkit.tracking_quality_scan import scan


VIDEO_SUFFIXES = {".avi", ".mkv", ".mov", ".mp4", ".webm"}
LOWER_IS_BETTER = {"oob_pct", "jump_p95"}
FIELDS = ("rows", "coverage_pct", "oob_pct", "jump_p95", "ball_valid_pct",
          "median_track_len")


def _game_id(clip: Path) -> str:
    prefix, separator, game_id = clip.stem.partition("__")
    return game_id if separator and prefix and game_id else clip.stem


def corpus_clips(corpus: Path, sport: str, limit: int) -> tuple[list[Path], int]:
    """Return stable sport clips and the number excluded by the explicit cap."""
    clips = sorted(path for path in corpus.glob("{}__*".format(sport))
                   if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES)
    return clips[:limit], max(0, len(clips) - limit)


def _report_row(game_id: str, report: Mapping[str, Any], quality: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "game_id": game_id, "status": "completed", "rows": int(quality.get("rows", 0)),
        "coverage_pct": report.get("coverage_pct"), "oob_pct": report.get("oob_pct"),
        "jump_p95": report.get("jump_p95"), "ball_valid_pct": report.get("ball_valid_pct"),
        "median_track_len": quality.get("median_track_frames"),
        "passed": bool(report.get("passed")), "failures": list(report.get("failures", [])),
    }


def run_clip(sport: str, clip: Path, scratch: Path, max_frames: int,
             stride: int, timeout_seconds: int) -> dict[str, Any]:
    """Track, score, and retain all failure modes as an explicit result row."""
    game_id = _game_id(clip)
    output = scratch / game_id / "tracking_data.csv"
    worker = Path(__file__).with_name("tracking_corpus_worker.py")
    command = [sys.executable, str(worker), sport,
               str(clip), str(output), "--max-frames", str(max_frames),
               "--stride", str(stride)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        return {"game_id": game_id, "status": "timeout", "rows": None,
                "detail": "exceeded {} seconds".format(timeout_seconds)}
    if completed.returncode:
        detail = (completed.stderr or completed.stdout or "worker failed").strip().replace("\n", " ")
        return {"game_id": game_id, "status": "error", "rows": None,
                "detail": detail[:160]}
    if not output.is_file():
        return {"game_id": game_id, "status": "error", "rows": None,
                "detail": "worker completed without tracking_data.csv"}
    try:
        frame = pd.read_csv(output)
        report = asdict(evaluate(frame, sport, source=str(output)))
        return _report_row(game_id, report, scan(output))
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        return {"game_id": game_id, "status": "error", "rows": None,
                "detail": "unscorable: {}".format(exc)}


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _format(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return "{:.3f}".format(value)
    return str(value)


def render_table(results: list[Mapping[str, Any]], requested: int, capped: int) -> str:
    """Render every requested game outcome as an ASCII-only table."""
    headers = ("GAME", "ROWS", "COVER", "OOB", "JUMP95", "BALL", "MEDLEN", "VERDICT")
    lines = ["%-18s %6s %6s %6s %7s %6s %6s %s" % headers,
             "-" * 92]
    for row in results:
        if row["status"] != "completed":
            verdict = "{}: {}".format(row["status"].upper(), row.get("detail", "unknown"))
            values = (row["game_id"][:18], "NA", "NA", "NA", "NA", "NA", "NA", verdict)
        else:
            verdict = "PASS" if row["passed"] else "FAIL: {}".format("; ".join(row["failures"]))
            values = (row["game_id"][:18], _format(row["rows"]),
                      _format(row["coverage_pct"]), _format(row["oob_pct"]),
                      _format(row["jump_p95"]), _format(row["ball_valid_pct"]),
                      _format(row["median_track_len"]), verdict)
        lines.append("%-18s %6s %6s %6s %7s %6s %6s %s" % values)
    lines.append("requested={} completed={} incomplete={} capped={}".format(
        requested, sum(row["status"] == "completed" for row in results),
        sum(row["status"] != "completed" for row in results), capped))
    if capped:
        lines.append("CAP: {} corpus clips were not run because --games capped this measurement.".format(capped))
    return "\n".join(lines)


def _load_baseline(path: Path) -> dict[str, Mapping[str, Any]]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("games", []) if isinstance(raw, dict) else []
    return {str(row["game_id"]): row for row in rows if isinstance(row, dict) and "game_id" in row}


def baseline_diff(baseline: Mapping[str, Mapping[str, Any]],
                  results: list[Mapping[str, Any]]) -> list[str]:
    """Name each game and metric that regressed; absent baselines remain explicit."""
    lines = ["BEFORE/AFTER DIFF"]
    for current in results:
        before = baseline.get(str(current["game_id"]))
        if before is None:
            lines.append("{} NEW (no stored baseline)".format(current["game_id"]))
            continue
        worse = []
        if before.get("status") == "completed" and current.get("status") != "completed":
            worse.append("status {}->{}".format(before["status"], current["status"]))
        for field in FIELDS:
            old, new = before.get(field), current.get(field)
            if _number(old) and _number(new):
                regressed = new > old if field in LOWER_IS_BETTER else new < old
                if regressed:
                    worse.append("{} {}->{}".format(field, _format(old), _format(new)))
        if bool(before.get("passed")) and not bool(current.get("passed")):
            worse.append("verdict PASS->FAIL")
        lines.append("{} {}".format(current["game_id"], "WORSE: " + ", ".join(worse) if worse else "not worse"))
    return lines


def write_baseline(path: Path, sport: str, results: list[Mapping[str, Any]],
                   corpus: Path, max_frames: int, stride: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "sport": sport, "games": results,
                                "measurement": {"corpus": str(corpus),
                                                "max_frames": max_frames, "stride": stride}},
                               indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a bounded tracking corpus A/B measurement.")
    parser.add_argument("sport", choices=sorted(ADAPTERS))
    parser.add_argument("--corpus", type=Path, default=Path("data/footage_corpus"))
    parser.add_argument("--games", type=int, default=3)
    parser.add_argument("--max-frames", type=int, default=600)
    parser.add_argument("--stride", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)
    clips, capped = corpus_clips(args.corpus, args.sport, args.games)
    baseline = args.baseline or Path("docs/evidence/tracking/{}_baseline.json".format(args.sport))
    if not clips:
        print("no corpus clips found sport={} corpus={}".format(args.sport, args.corpus))
        return 2
    if args.scratch:
        args.scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="tracking_corpus_ab_", dir=str(args.scratch) if args.scratch else None) as directory:
        results = [run_clip(args.sport, clip, Path(directory), args.max_frames,
                            args.stride, args.timeout_seconds) for clip in clips]
    print(render_table(results, len(clips), capped))
    print("\n".join(baseline_diff(_load_baseline(baseline), results)))
    if args.write_baseline:
        write_baseline(baseline, args.sport, results, args.corpus,
                       args.max_frames, args.stride)
        print("baseline written={}".format(baseline))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
