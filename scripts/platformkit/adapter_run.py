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

ADAPTERS = {
    "tennis": ("domains.tennis.tracking.adapter", "TennisAdapter"),
    "soccer": ("domains.soccer.tracking.adapter", "SoccerAdapter"),
    "baseball": ("domains.baseball.tracking.adapter", "BaseballAdapter"),
    "football": ("domains.football.tracking.adapter", "FootballAdapter"),
}
# Sports whose adapter must be asked for player-only tracking rather than
# raising, because it cannot honestly produce ball positions.
PLAYER_ONLY = {"baseball", "soccer"}


def main(argv: list) -> int:
    if len(argv) < 4:
        print("usage: adapter_run.py <sport> <video> <game_id>")
        return 2
    sport, video, game_id = argv[1], argv[2], argv[3]
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
        options = {"max_frames": 30000, "stride": 3}
        if sport in PLAYER_ONLY:
            options["player_only"] = True
        frame = adapter.process_video(video, **options)

        output_dir = os.path.join("data", "tracking", game_id)
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "tracking_data.csv")
        module.write_csv(frame, output_path)

        from scripts.platformkit.tracking_harness import evaluate

        report = evaluate(pd.read_csv(output_path), sport)
        report_dir = os.path.join("data", "tracking_reports", sport)
        os.makedirs(report_dir, exist_ok=True)
        with open(os.path.join(report_dir, "%s.json" % game_id), "w") as handle:
            handle.write(report.to_json())
        print("%s rows=%d passed=%s failures=%s"
              % (game_id, len(frame), report.passed, report.failures))
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
