"""Run one adapter into an explicitly supplied scratch CSV."""
from __future__ import annotations

import argparse
import importlib
import sys
import traceback
from pathlib import Path
from typing import Any

from scripts.platformkit.adapter_run import ADAPTERS, IMAGE_SPACE, PLAYER_ONLY


def track(sport: str, clip: Path, output: Path, max_frames: int, stride: int) -> int:
    """Run the normal adapter path without touching production tracking directories."""
    if sport not in ADAPTERS:
        print("unknown adapter sport={}".format(sport))
        return 2
    module_name, class_name = ADAPTERS[sport]
    module = importlib.import_module(module_name)
    adapter = getattr(module, class_name)()
    options: dict[str, Any] = {"max_frames": max_frames, "stride": stride}
    if sport in PLAYER_ONLY:
        options["player_only"] = True
    if sport in IMAGE_SPACE:
        options["image_space"] = True
    frame = adapter.process_video(str(clip), **options)
    output.parent.mkdir(parents=True, exist_ok=True)
    module.write_csv(frame, str(output))
    print("worker rows={} output={}".format(len(frame), output))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one tracking adapter in scratch space.")
    parser.add_argument("sport")
    parser.add_argument("clip", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-frames", type=int, required=True)
    parser.add_argument("--stride", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        return track(args.sport, args.clip, args.output, args.max_frames, args.stride)
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
