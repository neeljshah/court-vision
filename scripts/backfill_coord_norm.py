"""
backfill_coord_norm.py — Add x_norm, y_norm, defender_dist_norm to existing shot_log.csv
and x_norm, y_norm to existing tracking_data.csv for all processed games.

Each game's pano dimensions differ, so we derive map_w / map_h from the run.log if
possible, otherwise estimate from the max coordinate range observed in that game's CSV.

Usage:
    conda activate basketball_ai
    python scripts/backfill_coord_norm.py
"""

import csv
import os
import re
from pathlib import Path

PROJECT_DIR  = Path(__file__).resolve().parent.parent
TRACKING_DIR = PROJECT_DIR / "data" / "tracking"


def _parse_map_dims_from_log(run_log: Path):
    """Parse 'map_2d shape: WxH' line from run.log if present. Returns (w, h) or None."""
    if not run_log.exists():
        return None
    try:
        text = run_log.read_text(errors="ignore")
        m = re.search(r"map_2d\s+(?:shape[:\s]+)?(\d+)[x×](\d+)", text, re.IGNORECASE)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None


def _estimate_map_dims_from_csv(rows, x_col="x_position", y_col="y_position"):
    """Estimate map dimensions as 110% of the max coordinate seen (safe upper bound)."""
    xs = [float(r[x_col]) for r in rows
          if r.get(x_col, "").replace(".", "").lstrip("-").isdigit()]
    ys = [float(r[y_col]) for r in rows
          if r.get(y_col, "").replace(".", "").lstrip("-").isdigit()]
    if not xs or not ys:
        return None
    map_w = max(int(max(xs) * 1.1), 1)
    map_h = max(int(max(ys) * 1.1), 1)
    return map_w, map_h


def backfill_shot_log(game_dir: Path, map_w: int, map_h: int) -> int:
    path = game_dir / "shot_log.csv"
    if not path.exists():
        return 0

    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    if not rows:
        return 0

    # Skip if already normalized
    if "x_norm" in rows[0]:
        return 0

    # Rebuild fieldnames inserting new cols after y_position / defender_distance
    old_fields = list(rows[0].keys())
    new_fields = []
    for f in old_fields:
        new_fields.append(f)
        if f == "y_position":
            new_fields += ["x_norm", "y_norm"]
        if f == "defender_distance":
            new_fields.append("defender_dist_norm")

    for r in rows:
        try:
            x = float(r.get("x_position", 0) or 0)
            y = float(r.get("y_position", 0) or 0)
            d = float(r.get("defender_distance", 0) or 0)
        except ValueError:
            x, y, d = 0.0, 0.0, 0.0
        r["x_norm"] = round(x / map_w, 4)
        r["y_norm"] = round(y / map_h, 4)
        r["defender_dist_norm"] = round(d / map_w, 4)

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=new_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def backfill_tracking(game_dir: Path, map_w: int, map_h: int) -> int:
    path = game_dir / "tracking_data.csv"
    if not path.exists():
        return 0

    # Large file — stream it
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        old_fields = reader.fieldnames or []
        if "x_norm" in old_fields:
            return 0
        rows = list(reader)

    if not rows:
        return 0

    new_fields = []
    for f in old_fields:
        new_fields.append(f)
        if f == "y_position":
            new_fields += ["x_norm", "y_norm"]

    for r in rows:
        try:
            x = float(r.get("x_position", 0) or 0)
            y = float(r.get("y_position", 0) or 0)
        except ValueError:
            x, y = 0.0, 0.0
        r["x_norm"] = round(x / map_w, 4)
        r["y_norm"] = round(y / map_h, 4)

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=new_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def process_game(game_dir: Path):
    name = game_dir.name
    run_log = game_dir / "run.log"

    dims = _parse_map_dims_from_log(run_log)
    if dims is None:
        # Estimate from shot_log coordinates
        shot_path = game_dir / "shot_log.csv"
        if shot_path.exists():
            rows = list(csv.DictReader(shot_path.open(newline="")))
            dims = _estimate_map_dims_from_csv(rows)
    if dims is None:
        # Estimate from tracking_data
        td_path = game_dir / "tracking_data.csv"
        if td_path.exists():
            with open(td_path, newline="") as f:
                reader = csv.DictReader(f)
                rows = [next(reader) for _ in range(500) if True]
            dims = _estimate_map_dims_from_csv(rows)
    if dims is None:
        print(f"  {name}: SKIP — cannot estimate map dims")
        return

    map_w, map_h = dims
    shots  = backfill_shot_log(game_dir, map_w, map_h)
    tracks = backfill_tracking(game_dir, map_w, map_h)

    if shots == 0 and tracks == 0:
        print(f"  {name}: already normalized or no data")
    else:
        print(f"  {name}: map={map_w}x{map_h}  shots={shots}  tracking_rows={tracks}")


def main():
    game_dirs = [d for d in TRACKING_DIR.iterdir()
                 if d.is_dir() and (d / "shot_log.csv").exists()]
    game_dirs.sort()
    print(f"Found {len(game_dirs)} game dirs with shot_log.csv\n")
    for gd in game_dirs:
        process_game(gd)
    print("\nDone.")


if __name__ == "__main__":
    main()
