"""Bridge short, physically feasible gaps in canonical tracking tables.

Only linear rows between two observed endpoints are created.  The generated
rows are marked ``provenance=inferred`` and are never treated as observations.
This module is offline-only and does not download or alter the input CSV.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from scripts.platformkit.tracking_harness import evaluate

DEFAULT_FPS = 30.0
GAP_CAP_SECONDS = {
    "basketball": 1.0,
    "nba": 1.0,
    "wnba": 1.0,
    "soccer": 2.0,
    "football": 2.0,
    "tennis": 0.0,
    "baseball": 0.0,
    "npb": 0.0,
    "kbo": 0.0,
}


@dataclass(frozen=True)
class BridgeReport:
    """Counts and harness coverage for one bridge-only transformation."""

    gaps_seen: int
    gaps_bridged: int
    gaps_rejected_gap_too_long: int
    gaps_rejected_infeasible: int
    rows_bridged: int
    coverage_observed: float | None
    coverage_with_bridge: float | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report."""
        return asdict(self)


def _sport_key(sport: str) -> str:
    key = str(sport).strip().lower()
    if key == "nba":
        key = "basketball"
    if key not in GAP_CAP_SECONDS:
        raise ValueError("unsupported sport: {}".format(sport))
    return key


def _required(table: pd.DataFrame) -> None:
    required = {"frame", "track_id", "x", "y", "cls"}
    missing = sorted(required.difference(table.columns))
    if missing:
        raise ValueError("tracking rows missing columns: {}".format(", ".join(missing)))


def _player_rows(table: pd.DataFrame) -> pd.DataFrame:
    return table.loc[table["cls"].astype(str).str.lower().eq("player")].copy()


def _p99_from_bounds(bounds: Mapping[str, Any] | str | Path | float, sport: str) -> float:
    """Read the sport's p99 jump from an N2 mapping or JSON artifact."""
    value: Any = bounds
    if isinstance(bounds, (str, Path)):
        with Path(bounds).open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        p99 = float(value)
    elif isinstance(value, Mapping):
        key = _sport_key(sport)
        selected = value.get(key)
        if selected is None and key in {"nba", "wnba"}:
            selected = value.get("basketball")
        if selected is None:
            selected = value
        if isinstance(selected, Mapping):
            for name in ("p99", "p99_bound", "jump_p99"):
                if selected.get(name) is not None:
                    selected = selected[name]
                    break
        p99 = float(selected)
    else:
        raise TypeError("motion bounds must be a number, mapping, or JSON path")
    if p99 < 0.0:
        raise ValueError("p99 motion bound must be non-negative")
    return p99


def _coverage(
    table: pd.DataFrame,
    sport: str,
    *,
    allow_legacy_undeclared: bool = False,
) -> float | None:
    """Return measured coverage, preserving an insufficient-data null."""
    report = evaluate(table, sport, allow_legacy_undeclared=allow_legacy_undeclared)
    if report.verdict == "INSUFFICIENT_DATA" or report.coverage_pct is None:
        return None
    return float(report.coverage_pct)


def _group_columns(table: pd.DataFrame) -> list[str]:
    return ["game_id", "track_id"] if "game_id" in table.columns else ["track_id"]


def bridge_dataframe(
    tracks: pd.DataFrame,
    sport: str,
    motion_bounds: Mapping[str, Any] | str | Path | float,
    *,
    fps: float = DEFAULT_FPS,
) -> tuple[pd.DataFrame, BridgeReport]:
    """Return a copy with only short, feasible two-sided gaps linearly filled."""
    _required(tracks)
    key = _sport_key(sport)
    if fps <= 0.0:
        raise ValueError("fps must be positive")
    p99 = _p99_from_bounds(motion_bounds, key)
    result = tracks.copy()
    result["provenance"] = "observed"
    players = _player_rows(result).dropna(subset=["frame", "track_id", "x", "y"])
    additions: list[dict[str, Any]] = []
    gaps_seen = gaps_bridged = rejected_long = rejected_motion = 0
    for _, group in players.groupby(_group_columns(result), sort=False, dropna=False):
        ordered = group.sort_values("frame", kind="stable")
        for index in range(len(ordered) - 1):
            left = ordered.iloc[index]
            right = ordered.iloc[index + 1]
            start, end = int(left["frame"]), int(right["frame"])
            elapsed = end - start
            if elapsed <= 1:
                continue
            gaps_seen += 1
            if elapsed / fps > GAP_CAP_SECONDS[key]:
                rejected_long += 1
                continue
            dx = float(right["x"]) - float(left["x"])
            dy = float(right["y"]) - float(left["y"])
            distance = (dx * dx + dy * dy) ** 0.5
            if distance > p99 * elapsed:
                rejected_motion += 1
                continue
            gaps_bridged += 1
            for frame in range(start + 1, end):
                fraction = (frame - start) / elapsed
                row = left.to_dict()
                row.update({
                    "frame": frame,
                    "x": float(left["x"]) + fraction * dx,
                    "y": float(left["y"]) + fraction * dy,
                    "provenance": "inferred",
                })
                additions.append(row)
    if additions:
        result = pd.concat([result, pd.DataFrame(additions)], ignore_index=True)
        result = result.sort_values(["frame", "track_id"], kind="stable").reset_index(drop=True)
    report = BridgeReport(
        gaps_seen=gaps_seen,
        gaps_bridged=gaps_bridged,
        gaps_rejected_gap_too_long=rejected_long,
        gaps_rejected_infeasible=rejected_motion,
        rows_bridged=len(additions),
        coverage_observed=_coverage(tracks, key),
        coverage_with_bridge=_coverage(result, key),
    )
    return result, report


def bridge_csv(
    input_csv: str | Path,
    output_csv: str | Path,
    sport: str,
    motion_bounds: Mapping[str, Any] | str | Path | float,
    *,
    fps: float = DEFAULT_FPS,
) -> BridgeReport:
    """Read one CSV, write a transformed copy, and return its report."""
    table, report = bridge_dataframe(pd.read_csv(input_csv), sport, motion_bounds, fps=fps)
    table.to_csv(output_csv, index=False)
    return report


bridge_infill = bridge_dataframe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("sport")
    parser.add_argument("motion_bounds", type=Path)
    parser.add_argument("--fps", type=float, default=DEFAULT_FPS)
    args = parser.parse_args(argv)
    report = bridge_csv(args.input_csv, args.output_csv, args.sport, args.motion_bounds,
                        fps=args.fps)
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
