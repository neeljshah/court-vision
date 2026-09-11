"""G400: seal the ten paired rating rounds before any rater is dispatched."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g400_prepare as rails

FIELDS = ("round", "position", "frame_key", "canonical_game", "video_id",
          "width", "height", "state_status")


def run(args) -> int:
    out = Path(args.out_dir)
    with (out / "native_manifest.csv").open(encoding="ascii", newline="") as handle:
        manifest = list(csv.DictReader(handle))
    lookup = {row["frame_key"]: row for row in manifest}
    plan = rails.make_batch_plan(manifest)
    rows = [{**entry, "video_id": lookup[entry["frame_key"]]["video_id"],
             "width": lookup[entry["frame_key"]]["width"],
             "height": lookup[entry["frame_key"]]["height"],
             "state_status": lookup[entry["frame_key"]]["status"]} for entry in plan]
    with (out / "batch_plan.csv").open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    seal = hashlib.sha256((out / "batch_plan.csv").read_bytes()).hexdigest()
    (out / "batch_plan_seal.json").write_text(json.dumps(
        {"batch_plan_sha256": seal, "rounds": rails.RATER_BATCHES,
         "per_round": rails.RATER_BATCH_SIZE, "planned_states": len(rows),
         "sealed_utc": args.sealed_utc}, indent=1, sort_keys=True) + "\n",
        encoding="ascii")
    print("PLAN rows", len(rows), "seal", seal)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g400_plan")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--sealed-utc", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
