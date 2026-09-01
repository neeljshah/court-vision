"""Offline, explicitly marked recovery of short basketball tracking gaps.

This module never creates a new identity: it only aliases detected track
fragments and, for a linked identity, adds clearly marked interpolated rows.
The WNBA interpolation limit is 24 ft/s (about 16.4 mph), a conservative
upper bound for sustained player court motion rather than a claim of truth.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd


WNBA_MAX_INTERPOLATION_SPEED_FTPS = 24.0
DEFAULT_FPS = 30.0


def _player_rows(table: pd.DataFrame) -> pd.DataFrame:
    if "cls" not in table.columns:
        return table.copy()
    return table.loc[table["cls"].astype(str).str.lower().eq("player")].copy()


def _position_columns(table: pd.DataFrame) -> tuple[str, str]:
    for pair in (("court_x", "court_y"), ("x", "y")):
        if set(pair).issubset(table.columns):
            return pair
    raise ValueError("tracking rows need court_x/court_y or x/y columns")


def _identity_agrees(left: pd.Series, right: pd.Series) -> bool:
    """Return false only when populated team or jersey labels conflict."""
    for column in ("team", "team_id", "jersey_number", "jersey"):
        if column not in left.index:
            continue
        left_value, right_value = left[column], right[column]
        if pd.notna(left_value) and pd.notna(right_value) and left_value != right_value:
            return False
    return True


def track_bridging(
    tracks: pd.DataFrame,
    *,
    fps: float = DEFAULT_FPS,
    max_gap_frames: int = 45,
    max_speed_ft_per_sec: float = 30.0,
) -> dict[Any, Any]:
    """Link compatible detected player fragments and return raw-to-bridged IDs.

    A candidate starts one to ``max_gap_frames`` missing frames after another
    fragment ends. Its endpoint displacement must be physically reachable at
    ``max_speed_ft_per_sec``; populated team and jersey labels must agree.
    Greedy nearest matching makes every fragment have at most one predecessor
    and successor, avoiding identity fan-out.
    """
    required = {"frame", "track_id"}
    if missing := required.difference(tracks.columns):
        raise ValueError("missing columns: " + ", ".join(sorted(missing)))
    if fps <= 0 or max_gap_frames < 1 or max_speed_ft_per_sec <= 0:
        raise ValueError("fps, max_gap_frames, and max_speed_ft_per_sec must be positive")
    x_col, y_col = _position_columns(tracks)
    players = _player_rows(tracks).dropna(subset=["frame", "track_id", x_col, y_col])
    ids = tracks["track_id"].dropna().unique().tolist()
    mapping: dict[Any, Any] = {track_id: track_id for track_id in ids}
    if players.empty:
        return mapping

    fragments = []
    for track_id, group in players.groupby("track_id", sort=False):
        ordered = group.sort_values("frame")
        fragments.append((track_id, ordered.iloc[0], ordered.iloc[-1]))
    candidates: list[tuple[float, Any, Any]] = []
    for left_id, _, left_end in fragments:
        for right_id, right_start, _ in fragments:
            if left_id == right_id:
                continue
            elapsed = float(right_start["frame"] - left_end["frame"])
            missing_frames = elapsed - 1
            if missing_frames < 1 or missing_frames > max_gap_frames:
                continue
            if not _identity_agrees(left_end, right_start):
                continue
            distance = ((float(right_start[x_col]) - float(left_end[x_col])) ** 2 +
                        (float(right_start[y_col]) - float(left_end[y_col])) ** 2) ** 0.5
            if distance / elapsed * fps <= max_speed_ft_per_sec:
                candidates.append((distance, left_id, right_id))
    used_ends: set[Any] = set()
    used_starts: set[Any] = set()
    for _, left_id, right_id in sorted(candidates, key=lambda item: item[0]):
        if left_id in used_ends or right_id in used_starts:
            continue
        canonical = mapping[left_id]
        for raw_id, bridged_id in list(mapping.items()):
            if bridged_id == right_id:
                mapping[raw_id] = canonical
        mapping[right_id] = canonical
        used_ends.add(left_id)
        used_starts.add(right_id)
    return mapping


def occlusion_infill(
    tracks: pd.DataFrame,
    bridged_track_id_map: dict[Any, Any],
    *,
    fps: float = DEFAULT_FPS,
    max_gap_frames: int = 15,
    max_speed_ft_per_sec: float = WNBA_MAX_INTERPOLATION_SPEED_FTPS,
) -> pd.DataFrame:
    """Apply an ID map and linearly fill only short, plausible bridged gaps.

    Original detections have ``inferred=0``. Generated rows have
    ``inferred=1`` and use an existing bridged identity; they are not a new
    player detection and can be excluded downstream.
    """
    if fps <= 0 or max_gap_frames < 1 or max_speed_ft_per_sec <= 0:
        raise ValueError("fps, max_gap_frames, and max_speed_ft_per_sec must be positive")
    x_col, y_col = _position_columns(tracks)
    result = tracks.copy()
    result["source_track_id"] = result["track_id"]
    result["track_id"] = result["track_id"].map(bridged_track_id_map).fillna(result["track_id"])
    result["inferred"] = 0
    players = _player_rows(result).dropna(subset=["frame", "track_id", x_col, y_col])
    additions: list[dict[str, Any]] = []
    for bridged_id, group in players.groupby("track_id", sort=False):
        if group["source_track_id"].nunique() < 2:
            continue
        ordered = group.sort_values("frame")
        for index in range(len(ordered) - 1):
            left, right = ordered.iloc[index], ordered.iloc[index + 1]
            elapsed = float(right["frame"] - left["frame"])
            missing_frames = int(elapsed - 1)
            if missing_frames < 1 or missing_frames > max_gap_frames:
                continue
            distance = ((float(right[x_col]) - float(left[x_col])) ** 2 +
                        (float(right[y_col]) - float(left[y_col])) ** 2) ** 0.5
            if distance / elapsed * fps > max_speed_ft_per_sec:
                continue
            for frame in range(int(left["frame"]) + 1, int(right["frame"])):
                fraction = (frame - float(left["frame"])) / elapsed
                row = {column: pd.NA for column in result.columns}
                row.update({"frame": frame, "track_id": bridged_id,
                            "source_track_id": pd.NA, "inferred": 1,
                            x_col: float(left[x_col]) + fraction * (float(right[x_col]) - float(left[x_col])),
                            y_col: float(left[y_col]) + fraction * (float(right[y_col]) - float(left[y_col]))})
                if "cls" in result.columns:
                    row["cls"] = "player"
                additions.append(row)
    if additions:
        result = pd.concat([result, pd.DataFrame(additions)], ignore_index=True)
    return result.sort_values(["frame", "track_id", "inferred"], kind="stable").reset_index(drop=True)


def frame_completeness_report(
    before: pd.DataFrame, after: pd.DataFrame, minimum_players: int = 8,
) -> dict[str, float | int]:
    """Compare player coverage across the inclusive input frame timeline."""
    if minimum_players < 1:
        raise ValueError("minimum_players must be positive")
    if before.empty and after.empty:
        return {"pct_frames_with_at_least_n_before": 0.0,
                "pct_frames_with_at_least_n_after": 0.0,
                "id_fragment_count_before": 0, "id_fragment_count_after": 0,
                "inferred_row_share": 0.0}
    all_frames = pd.concat([before.get("frame", pd.Series(dtype=float)),
                            after.get("frame", pd.Series(dtype=float))]).dropna()
    timeline = range(int(all_frames.min()), int(all_frames.max()) + 1)

    def pct(table: pd.DataFrame) -> float:
        players = _player_rows(table)
        counts = players.groupby("frame")["track_id"].nunique()
        return round(100.0 * sum(int(counts.get(frame, 0)) >= minimum_players for frame in timeline) / len(timeline), 6)

    before_players, after_players = _player_rows(before), _player_rows(after)
    inferred = pd.to_numeric(after.get("inferred", pd.Series(0, index=after.index)), errors="coerce").fillna(0)
    return {"pct_frames_with_at_least_n_before": pct(before),
            "pct_frames_with_at_least_n_after": pct(after),
            "id_fragment_count_before": int(before_players["track_id"].nunique()),
            "id_fragment_count_after": int(after_players["track_id"].nunique()),
            "inferred_row_share": round(100.0 * float(inferred.eq(1).sum()) / len(after) if len(after) else 0.0, 6)}


def recover_csv(input_csv: str | Path, output_csv: str | Path) -> tuple[dict[Any, Any], dict[str, float | int]]:
    """Recover one offline CSV and return its bridge map and coverage report."""
    before = pd.read_csv(input_csv)
    bridge_map = track_bridging(before)
    after = occlusion_infill(before, bridge_map)
    after.to_csv(output_csv, index=False)
    return bridge_map, frame_completeness_report(before, after)


def main(argv: list[str] | None = None) -> int:
    """Recover an existing tracking CSV without modifying the input file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--minimum-players", type=int, default=8)
    args = parser.parse_args(argv)
    bridge_map, report = recover_csv(args.input_csv, args.output_csv)
    report["bridged_track_id_map"] = {str(key): str(value) for key, value in bridge_map.items()}
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
