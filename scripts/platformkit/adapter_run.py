"""Track one video with a sport adapter, score it, and write the harness report.

This is the entry point the footage bridge invokes on the pod. It lived only on
the pod as an untracked root-level adapter_run.py, so it was never reviewed or
tested; it is versioned here and deployed from here.

Baseball note: the baseball adapter now fails closed on ball tracking, because
it only ever requested COCO class 0 (person) and stubbed ball rows -- ball_valid
was guaranteed 0.00. Baseball therefore runs with player_only=True: real
pitcher/batter tracking, and honestly no ball, rather than fabricated ball rows.

Soccer note: same situation, now made explicit. The soccer adapter also runs
person class 0 only; its ball path was a stub returning [] whose return value
was discarded, so ball_valid was likewise guaranteed 0.00. It now requires the
same player_only=True opt-in. Its ball_valid_min gate is left where it is and
keeps failing, because that failure is true.

Run: python -m scripts.platformkit.adapter_run <sport> <video> <game_id>
"""
from __future__ import annotations

import os
import sys
import traceback
import json
import argparse
from pathlib import Path

ADAPTERS = {
    "tennis": ("domains.tennis.tracking.adapter", "TennisAdapter"),
    "soccer": ("domains.soccer.tracking.adapter", "SoccerAdapter"),
    "baseball": ("domains.baseball.tracking.adapter", "BaseballAdapter"),
    "football": ("domains.football.tracking.adapter", "FootballAdapter"),
}
# Sports whose adapter must be asked for player-only tracking rather than
# raising, because it cannot honestly produce ball positions.
PLAYER_ONLY = {"baseball", "soccer"}
# Sports asked for IMAGE-SPACE rows because their court calibration is measured
# never to succeed on broadcast footage, so the court path emits nothing and the
# detector's work is simply discarded. Image rows declare coordinate_space and
# are REJECTED by the harness with coordinate_contract -- they are a preserved
# corpus for training, never a passing game.
#   soccer: 0 accepted homographies over 200 reference frames; the 131-of-132
#           "accepted" frames it used to report were a stale cached homography.
# Add a sport here only once its adapter supports image_space=True AND its
# calibration failure is MEASURED, not assumed.
IMAGE_SPACE = {"baseball", "football", "soccer"}
TEACHER_META = {"baseball"}
# Persisted declaration consumed by tracking_schema at the sole normalized-table
# decision point. Tennis runs MotionDiffDetector; every other current adapter
# writes player-only rows or has no evidenced ball detector. The basketball
# family is produced through run_clip by other callers and declares false too.
BALL_TELEMETRY_AVAILABLE = {
    "tennis": True,
    "soccer": False,
    "baseball": False,
    "football": False,
    "basketball": False,
    "wnba": False,
    "ncaa_basketball": False,
    "nba": False,
}


def _source_metadata(video: str) -> dict:
    """Read source metadata before adapters consume the clip."""
    from scripts.platformkit.tracking_media_inventory import probe_media
    from pathlib import Path
    metadata = probe_media(Path(video))
    width, height = metadata.get("width"), metadata.get("height")
    if width is not None and height is not None:
        metadata["resolution"] = "{}x{}".format(width, height)
    return metadata


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description="Track one video with a sport adapter.")
    parser.add_argument("sport")
    parser.add_argument("video")
    parser.add_argument("game_id")
    parser.add_argument("--max-frames", type=int, default=30000)
    args = parser.parse_args(argv[1:])
    sport, video, game_id = args.sport, args.video, args.game_id
    if sport not in ADAPTERS:
        print("unknown sport: %s (known: %s)" % (sport, ", ".join(sorted(ADAPTERS))))
        return 2

    sys.path.insert(0, ".")
    try:
        import importlib

        import pandas as pd

        module_name, class_name = ADAPTERS[sport]
        module = importlib.import_module(module_name)
        adapter = getattr(module, class_name)()
        from scripts.platformkit.tracking_timebase import sampling_plan, timebase_metrics

        metadata = _source_metadata(video)
        plan = sampling_plan(metadata.get("frame_rate"))
        options = {"max_frames": args.max_frames, "stride": plan.stride}
        if sport in PLAYER_ONLY:
            options["player_only"] = True
        if sport in IMAGE_SPACE:
            options["image_space"] = True
        if sport in TEACHER_META:
            options["compute_command"] = True
            frame, teacher_metadata = adapter.process_video(video, **options)
        else:
            frame = adapter.process_video(video, **options)

        output_dir = os.path.join("data", "tracking", game_id)
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "tracking_data.csv")
        module.write_csv(frame, output_path)
        from scripts.platformkit.tracking_schema import write_ball_telemetry_declaration
        write_ball_telemetry_declaration(output_path, sport, BALL_TELEMETRY_AVAILABLE[sport])
        if sport in TEACHER_META:
            from scripts.platformkit.tracking.teacher_emit import write_teacher_meta
            write_teacher_meta(teacher_metadata, game_id, sport, output_dir)

        from scripts.platformkit.tracking_harness import evaluate

        report = evaluate(pd.read_csv(output_path), sport, source_metadata=metadata)
        report_dir = os.path.join("data", "tracking_reports", sport)
        os.makedirs(report_dir, exist_ok=True)
        with open(os.path.join(report_dir, "%s.json" % game_id), "w") as handle:
            payload = json.loads(report.to_json())
            payload["sampling"] = plan.to_dict()
            payload["timebase_metrics"] = timebase_metrics(payload, plan)
            from scripts.platformkit.tracking.run_environment import with_run_environment
            from scripts.platformkit import tracking_harness, tracking_schema
            payload = with_run_environment(
                payload, seed=None,
                seed_reason="adapter_run has no explicit seed configuration",
                module_paths=(Path(__file__), Path(module.__file__),
                              Path(tracking_harness.__file__), Path(tracking_schema.__file__)),
            )
            handle.write(json.dumps(payload, indent=2) + "\n")
        print("%s rows=%d passed=%s failures=%s"
              % (game_id, len(frame), report.passed, report.failures))
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
