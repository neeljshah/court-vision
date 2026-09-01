"""Fit empirical per-sport displacement bounds from canonical tracking CSVs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import pandas as pd

from scripts.platformkit.tracking_harness import SPORTS


def _columns(frame: pd.DataFrame) -> tuple[str, str, str]:
    track = next((name for name in ("track_id", "player_id") if name in frame), None)
    x_value = next((name for name in ("x", "x_position", "ft_x") if name in frame), None)
    y_value = next((name for name in ("y", "y_position", "ft_y") if name in frame), None)
    if not track or not x_value or not y_value or "frame" not in frame:
        raise ValueError("tracking rows require frame, track id, x position, and y position")
    return track, x_value, y_value


def _units(sport: str) -> str:
    bounds = SPORTS[sport]["bounds"]
    if bounds == SPORTS["basketball"]["bounds"]:
        return "ft"
    if bounds == SPORTS["soccer"]["bounds"] or bounds == SPORTS["football"]["bounds"]:
        return "m"
    return "ft"


def displacements(frame: pd.DataFrame) -> pd.Series:
    """Return harness-defined per-track Euclidean frame-to-frame jumps."""
    track, x_value, y_value = _columns(frame)
    rows = frame.copy()
    if "cls" in rows:
        rows = rows.loc[rows["cls"].astype("string").str.lower().eq("player")]
    rows[x_value] = pd.to_numeric(rows[x_value], errors="coerce")
    rows[y_value] = pd.to_numeric(rows[y_value], errors="coerce")
    rows = rows.dropna(subset=[track, "frame", x_value, y_value])
    grouped = rows.sort_values([track, "frame"]).groupby(track)
    return ((grouped[x_value].diff() ** 2 + grouped[y_value].diff() ** 2) ** 0.5).dropna()


def fit_motion_bounds(paths: Sequence[str | Path], sport: str,
                      fps_assumed: float = 30.0) -> dict[str, object]:
    """Fit percentile bounds from a list of independent tracking CSVs."""
    if sport not in SPORTS:
        raise ValueError("unknown sport {}".format(sport))
    if fps_assumed <= 0:
        raise ValueError("fps_assumed must be positive")
    source_paths = [Path(path) for path in paths]
    jumps = pd.concat([displacements(pd.read_csv(path)) for path in source_paths], ignore_index=True)
    if jumps.empty:
        raise ValueError("no valid player displacements in supplied CSVs")
    return {
        "units": _units(sport), "n_games": len(source_paths), "n_jumps": int(len(jumps)),
        "p50": float(jumps.quantile(0.50)), "p95": float(jumps.quantile(0.95)),
        "p99": float(jumps.quantile(0.99)), "p999": float(jumps.quantile(0.999)),
        "fps_assumed": float(fps_assumed),
    }


def write_motion_bounds(paths: Sequence[str | Path], sport: str,
                        output_path: str | Path = ".planning/tracking/motion_bounds.json",
                        fps_assumed: float = 30.0) -> dict[str, object]:
    """Fit one sport and preserve existing sport entries in the JSON output."""
    destination = Path(output_path)
    reports = json.loads(destination.read_text(encoding="ascii")) if destination.exists() else {}
    reports[sport] = fit_motion_bounds(paths, sport, fps_assumed)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(reports, indent=2, allow_nan=False), encoding="ascii")
    return reports[sport]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fit tracking motion bounds.")
    parser.add_argument("sport", choices=sorted(SPORTS))
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--output-path", default=".planning/tracking/motion_bounds.json")
    parser.add_argument("--fps", type=float, default=30.0)
    args = parser.parse_args()
    report = write_motion_bounds(args.paths, args.sport, args.output_path, args.fps)
    print(json.dumps(report, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
