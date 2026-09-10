"""G376 controlled re-run -- observe the producer schedule directly, once, in a scratch tree.

The deployed producer offers no evaluated-tick log, so this module WRAPS `UnifiedPipeline.run`
from THIS lane at import time and records the frame index of every entry the producer appends to
`predictions`, which is the same frame and the same line pair as its evaluated counter
(src/pipeline/unified_pipeline.py:2079, returned as `evaluated_frames` at :3063). The deploy tree
is never written: only `--data-dir`, which points at the scratch directory, receives output.
Control a compares that log with the `live = 1` frames of the run's own ball table.
"""
from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g361_source_identity import sha256_file
from scripts.platformkit.tracking.g376_schedule import reconstructed_schedule

DEPLOY = "/workspace/deploy/nba-ai-system"
_f = "{:.6f}".format


def _route_identity(deploy: Path) -> dict[str, str]:
    """A11: name the code that ran, by digest, because the pod is not a git checkout."""
    return {name: sha256_file(deploy / name) for name in
            ("scripts/run_clip.py", "src/pipeline/unified_pipeline.py")}


def run_wrapped(deploy: Path, video: Path, data_dir: Path, frames: int, log_path: Path) -> None:
    """Run the DEPLOYED route once with the evaluated-tick log attached."""
    sys.path.insert(0, str(deploy))
    from src.pipeline.unified_pipeline import UnifiedPipeline  # deployed module, read only
    import src.data.db as deployed_db      # its SQLite lives INSIDE the deploy tree

    # The route's non-fatal shot/scoreboard writes would otherwise touch
    # <deploy>/data/nba_ai.db (src/data/db.py:29-31). Redirect that one path into the
    # scratch so this run writes nothing whatsoever under /workspace/deploy.
    deployed_db._SQLITE_PATH = str(Path(data_dir).parent / "g376_scratch.db")

    original = UnifiedPipeline.run

    def logged_run(self: Any) -> dict:
        results = original(self)
        payload = {
            "evaluated_frame_ids": sorted({int(entry["frame"]) for entry
                                           in results.get("predictions", [])
                                           if entry.get("frame") is not None}),
            "evaluated_frames_returned": results.get("evaluated_frames"),
            "suspended_frames_returned": results.get("suspended_frames"),
            "total_frames_returned": results.get("total_frames"),
            "predictions_entries": len(results.get("predictions", [])),
        }
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        return results

    UnifiedPipeline.run = logged_run
    sys.argv = ["run_clip.py", "--video", str(video), "--no-show",
                "--frames", str(frames), "--data-dir", str(data_dir)]
    try:
        runpy.run_path(str(deploy / "scripts" / "run_clip.py"), run_name="__main__")
    except SystemExit as exit_code:      # run_clip ends with sys.exit on its own paths
        print("run_clip exited with %s" % exit_code.code, flush=True)


def compare(log_path: Path, data_dir: Path, deploy: Path) -> dict[str, Any]:
    """Control a: the producer log against the run's own ball table. Absence is never a pass."""
    log = json.loads(Path(log_path).read_text(encoding="utf-8"))
    logged = set(log["evaluated_frame_ids"])
    schedule = reconstructed_schedule(Path(data_dir) / "ball_tracking.csv")
    evaluated = schedule["evaluated"]
    difference = logged.symmetric_difference(evaluated)
    return {
        "logged_evaluated_ticks": len(logged),
        "ball_live_ticks": len(evaluated),
        "suspended_ticks": len(schedule["suspended"]),
        "schedule_reason": schedule["reason"],
        "observed_stride": schedule["observed_stride"],
        "intersection": len(logged & evaluated),
        "symmetric_difference": len(difference),
        "symmetric_difference_head": sorted(difference)[:20],
        "reproduction": _f(len(logged & evaluated) / len(logged)) if logged else "ABSENT",
        "evaluated_frames_returned": log["evaluated_frames_returned"],
        "predictions_entries": log["predictions_entries"],
        "route_identity_sha256": _route_identity(Path(deploy)),
    }


def build_parser() -> argparse.ArgumentParser:
    """The command line, factored out so a recorded command can be checked against it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--frames", type=int, default=3000)
    parser.add_argument("--deploy", default=DEPLOY)
    parser.add_argument("--log", required=True)
    parser.add_argument("--summary", default="")
    parser.add_argument("--compare-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    deploy, data_dir = Path(args.deploy), Path(args.data_dir)
    if not args.compare_only:
        run_wrapped(deploy, Path(args.video), data_dir, args.frames, Path(args.log))
    summary = compare(Path(args.log), data_dir, deploy)
    if args.summary:
        Path(args.summary).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                      encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
