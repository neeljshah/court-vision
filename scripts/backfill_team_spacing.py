"""
backfill_team_spacing.py — Recompute team_spacing and spacing_hull_area for existing
tracking_data.csv files, normalising px² convex hull area to ft² equivalent.

ISSUE-026: ConvexHull.volume returns pixel-unit area (e.g. 146,000 px²) which is
meaningless for ML.  Fix: divide by (map_w * map_h) / 4700.0 to convert to ft²
equivalent.  map_w and map_h are inferred from max(x_position) and max(y_position)
in each tracking file.

Usage:
    python scripts/backfill_team_spacing.py [--game GAME_ID ...]

If no --game flag is given, all games under data/tracking/ are processed.
"""

import argparse
import csv
import os
import shutil
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data", "tracking")
NORM_REF   = 4700.0   # ft² reference — matches _SPACING_NORM in unified_pipeline.py


# ── Convex hull (pure Python fallback if scipy unavailable) ───────────────────

try:
    from scipy.spatial import ConvexHull as _SciConvexHull
    _SCIPY = True
except ImportError:
    _SCIPY = False


def _convex_hull_area(pts: List[Tuple[float, float]]) -> float:
    """Return 2-D convex hull area for a list of (x, y) points."""
    if len(pts) < 3:
        return 0.0
    if _SCIPY:
        import numpy as np
        try:
            return float(_SciConvexHull(np.array(pts, dtype=float)).volume)
        except Exception:
            return 0.0
    # Fallback: shoelace formula on convex hull approximation via Graham scan
    # Good enough for backfill; scipy is preferred.
    try:
        from functools import cmp_to_key
        import math

        def _cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        pts_sorted = sorted(set(pts))
        if len(pts_sorted) < 3:
            return 0.0
        lower: List = []
        for p in pts_sorted:
            while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
                lower.pop()
            lower.append(p)
        upper: List = []
        for p in reversed(pts_sorted):
            while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
                upper.pop()
            upper.append(p)
        hull = lower[:-1] + upper[:-1]
        n = len(hull)
        area = abs(sum(hull[i][0] * hull[(i+1) % n][1] - hull[(i+1) % n][0] * hull[i][1]
                       for i in range(n))) / 2.0
        return area
    except Exception:
        return 0.0


def _infer_map_size(rows: List[dict]) -> Tuple[float, float]:
    """Infer map_w and map_h from max x_position / y_position in tracking rows."""
    xs = [float(r["x_position"]) for r in rows if r.get("x_position") not in ("", None)]
    ys = [float(r["y_position"]) for r in rows if r.get("y_position") not in ("", None)]
    map_w = max(xs) if xs else 1180.0   # typical 2D court width in px
    map_h = max(ys) if ys else 680.0
    return map_w, map_h


def _recompute_spacing(rows: List[dict], map_w: float, map_h: float) -> None:
    """Mutate rows in-place: recompute team_spacing and spacing_hull_area columns."""
    norm_factor = (map_w * map_h) / NORM_REF

    # Group by (frame, team) to get the set of player positions per team per frame
    by_frame_team: Dict[Tuple[int, str], List[Tuple[float, float]]] = defaultdict(list)
    for r in rows:
        try:
            frame = int(r["frame"])
            team  = r.get("team", "")
            if not team or team == "referee":
                continue
            x = float(r["x_position"])
            y = float(r["y_position"])
            by_frame_team[(frame, team)].append((x, y))
        except (ValueError, KeyError):
            continue

    # Build lookup: (frame, team) -> normalised spacing
    spacing_lut: Dict[Tuple[int, str], float] = {}
    for (frame, team), pts in by_frame_team.items():
        px_area = _convex_hull_area(pts)
        spacing_lut[(frame, team)] = px_area / norm_factor if norm_factor else 0.0

    # Patch rows
    for r in rows:
        try:
            frame = int(r["frame"])
            team  = r.get("team", "")
            key   = (frame, team)
            if key in spacing_lut:
                val = round(spacing_lut[key], 4)
                r["team_spacing"]       = val
                r["spacing_hull_area"]  = val
        except (ValueError, KeyError):
            continue


def _process_game(game_dir: str) -> Optional[str]:
    """Recompute spacing columns for one game's tracking_data.csv. Returns game_id or None."""
    tracking_csv = os.path.join(game_dir, "tracking_data.csv")
    if not os.path.exists(tracking_csv):
        return None

    game_id = os.path.basename(game_dir)

    with open(tracking_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if not rows:
        print(f"  {game_id}: empty — skipped")
        return None

    # Ensure output columns exist in fieldnames (in case of old schema)
    for col in ("team_spacing", "spacing_hull_area"):
        if col not in fieldnames:
            fieldnames = list(fieldnames) + [col]

    # Snapshot before
    sample_before = rows[0].get("team_spacing", "")

    map_w, map_h = _infer_map_size(rows)
    _recompute_spacing(rows, map_w, map_h)

    sample_after = rows[0].get("team_spacing", "")

    # Write back (atomic via temp file)
    tmp = tracking_csv + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    shutil.move(tmp, tracking_csv)

    print(f"  {game_id}: map={int(map_w)}×{int(map_h)}px  "
          f"team_spacing  {sample_before} → {sample_after}  ({len(rows)} rows)")
    return game_id


def main():
    ap = argparse.ArgumentParser(description="Backfill team_spacing ft² normalisation")
    ap.add_argument("--game", dest="games", nargs="*",
                    help="Game IDs to process (default: all under data/tracking/)")
    args = ap.parse_args()

    if args.games:
        dirs = [os.path.join(DATA_DIR, g) for g in args.games]
    else:
        dirs = sorted(
            os.path.join(DATA_DIR, d)
            for d in os.listdir(DATA_DIR)
            if os.path.isdir(os.path.join(DATA_DIR, d))
        )

    if not dirs:
        print("No game directories found under", DATA_DIR)
        return

    print(f"Backfilling team_spacing for {len(dirs)} game(s)…")
    done, skipped = 0, 0
    for d in dirs:
        result = _process_game(d)
        if result:
            done += 1
        else:
            skipped += 1

    print(f"\nDone: {done} updated, {skipped} skipped.")


if __name__ == "__main__":
    main()
