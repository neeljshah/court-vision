"""Merge tracking fragments using geometry, timing, and team agreement only."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from scripts.platformkit.tracking.bridge_infill import _coverage, _p99_from_bounds, _sport_key


@dataclass(frozen=True)
class MergeReport:
    """Identity and coverage measurements before and after a merge."""

    n_tracks_before: int
    n_tracks_after: int
    median_track_length_before: float
    median_track_length_after: float
    concurrent_duplicates_culled: int
    coverage_before: float | None
    coverage_after: float | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable report."""
        return asdict(self)


def _required(table: pd.DataFrame) -> None:
    required = {"frame", "track_id", "x", "y", "cls"}
    missing = sorted(required.difference(table.columns))
    if missing:
        raise ValueError("tracking rows missing columns: {}".format(", ".join(missing)))


def _players(table: pd.DataFrame) -> pd.DataFrame:
    return table.loc[table["cls"].astype(str).str.lower().eq("player")].copy()


def _ids(table: pd.DataFrame) -> list[Any]:
    return table["track_id"].dropna().drop_duplicates().tolist()


class _UnionFind:
    def __init__(self, values: list[Any]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: Any) -> Any:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: Any, right: Any, preferred: Any | None = None) -> Any:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return left_root
        root = preferred if preferred in {left_root, right_root} else left_root
        other = right_root if root == left_root else left_root
        self.parent[other] = root
        return root


def _team_values(rows: pd.DataFrame) -> set[str]:
    if "team" not in rows.columns:
        return set()
    return {str(value) for value in rows["team"].dropna().tolist()}


def _teams_agree(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    left_values, right_values = _team_values(left), _team_values(right)
    return not left_values or not right_values or left_values == right_values


def _game_value(rows: pd.DataFrame) -> Any:
    if "game_id" not in rows.columns:
        return None
    values = rows["game_id"].dropna().drop_duplicates().tolist()
    return values[0] if values else None


def _common_run(left: pd.DataFrame, right: pd.DataFrame) -> int:
    left_by_frame = {int(row.frame): row for row in left.itertuples(index=False)}
    right_by_frame = {int(row.frame): row for row in right.itertuples(index=False)}
    common = sorted(set(left_by_frame).intersection(right_by_frame))
    longest = current = 0
    previous = None
    for frame in common:
        a, b = left_by_frame[frame], right_by_frame[frame]
        distance = ((float(a.x) - float(b.x)) ** 2 + (float(a.y) - float(b.y)) ** 2) ** 0.5
        if distance <= 1.5 and previous is not None and frame == previous + 1:
            current += 1
        elif distance <= 1.5:
            current = 1
        else:
            current = 0
        longest = max(longest, current)
        previous = frame
    return longest


def _confidence_mean(rows: pd.DataFrame) -> float:
    if "confidence" not in rows.columns:
        return 0.0
    values = pd.to_numeric(rows["confidence"], errors="coerce").dropna()
    return float(values.mean()) if len(values) else 0.0


def _deduplicate(players: pd.DataFrame, union: _UnionFind) -> set[Any]:
    ids = players["track_id"].dropna().drop_duplicates().tolist()
    losers: set[Any] = set()
    by_id = {track_id: players.loc[players["track_id"].eq(track_id)] for track_id in ids}
    for index, left_id in enumerate(ids):
        for right_id in ids[index + 1:]:
            left, right = by_id[left_id], by_id[right_id]
            if _game_value(left) != _game_value(right) or not _teams_agree(left, right):
                continue
            if _common_run(left, right) < 15:
                continue
            left_score, right_score = _confidence_mean(left), _confidence_mean(right)
            winner, loser = (left_id, right_id) if left_score >= right_score else (right_id, left_id)
            union.union(winner, loser, preferred=winner)
            losers.add(loser)
    return losers


def _component_rows(players: pd.DataFrame, members: set[Any]) -> pd.DataFrame:
    return players.loc[players["track_id"].isin(members)].copy()


def _component_compatible(
    players: pd.DataFrame, left_members: set[Any], right_members: set[Any], p99: float,
) -> tuple[bool, float]:
    left, right = _component_rows(players, left_members), _component_rows(players, right_members)
    if _game_value(left) != _game_value(right) or not _teams_agree(left, right):
        return False, 0.0
    left_min, left_max = int(left["frame"].min()), int(left["frame"].max())
    right_min, right_max = int(right["frame"].min()), int(right["frame"].max())
    if left_max < right_min:
        earlier, later = left, right
    elif right_max < left_min:
        earlier, later = right, left
    else:
        return False, 0.0
    end = earlier.loc[earlier["frame"].idxmax()]
    start = later.loc[later["frame"].idxmin()]
    elapsed = int(start["frame"]) - int(end["frame"])
    distance = ((float(start.x) - float(end.x)) ** 2 + (float(start.y) - float(end.y)) ** 2) ** 0.5
    return distance <= p99 * elapsed, distance


def apply_tracklet_map(tracks: pd.DataFrame, mapping: Mapping[Any, Any]) -> pd.DataFrame:
    """Apply an ID map and remove duplicate frame-track rows by confidence."""
    _required(tracks)
    result = tracks.copy()
    result["track_id"] = result["track_id"].map(lambda value: mapping.get(value, value))
    result["_merge_order"] = range(len(result))
    result["_merge_confidence"] = pd.to_numeric(
        result.get("confidence", pd.Series(0.0, index=result.index)), errors="coerce"
    ).fillna(0.0)
    keys = ["frame", "track_id"]
    if "game_id" in result.columns:
        keys.insert(0, "game_id")
    result = result.sort_values(keys + ["_merge_confidence", "_merge_order"],
                                ascending=[True] * len(keys) + [False, True], kind="stable")
    result = result.drop_duplicates(keys, keep="first")
    return result.sort_values("_merge_order", kind="stable").drop(
        columns=["_merge_order", "_merge_confidence"]
    ).reset_index(drop=True)


def merge_tracklets(
    tracks: pd.DataFrame,
    sport: str,
    motion_bounds: Mapping[str, Any] | str | Path | float,
) -> tuple[dict[Any, Any], MergeReport]:
    """Return a geometry-only raw-ID map and its before/after report."""
    _required(tracks)
    key = _sport_key(sport)
    p99 = _p99_from_bounds(motion_bounds, key)
    players = _players(tracks).dropna(subset=["frame", "track_id", "x", "y"])
    ids = _ids(players)
    union = _UnionFind(ids)
    duplicate_losers = _deduplicate(players, union)
    dedup_mapping = {track_id: union.find(track_id) for track_id in ids}
    deduped = apply_tracklet_map(tracks, dedup_mapping)
    working = _players(deduped).dropna(subset=["frame", "track_id", "x", "y"])
    working_ids = _ids(working)
    union = _UnionFind(working_ids)
    candidates: list[tuple[float, Any, Any]] = []
    for index, left_id in enumerate(working_ids):
        for right_id in working_ids[index + 1:]:
            feasible, distance = _component_compatible(
                working, {left_id}, {right_id}, p99
            )
            if feasible:
                candidates.append((distance, left_id, right_id))
    for _, left_id, right_id in sorted(candidates, key=lambda item: (item[0], str(item[1]), str(item[2]))):
        left_root, right_root = union.find(left_id), union.find(right_id)
        if left_root == right_root:
            continue
        left_members = {value for value in working_ids if union.find(value) == left_root}
        right_members = {value for value in working_ids if union.find(value) == right_root}
        feasible, _ = _component_compatible(working, left_members, right_members, p99)
        if not feasible:
            continue
        left_first = int(_component_rows(working, left_members)["frame"].min())
        right_first = int(_component_rows(working, right_members)["frame"].min())
        preferred = left_root if (left_first, str(left_root)) <= (right_first, str(right_root)) else right_root
        union.union(left_root, right_root, preferred=preferred)
    mapping = {
        track_id: (union.find(dedup_mapping.get(track_id, track_id))
                   if dedup_mapping.get(track_id, track_id) in union.parent else track_id)
        for track_id in _ids(tracks)
    }
    after = apply_tracklet_map(tracks, mapping)
    before_players, after_players = _players(tracks), _players(after)
    before_lengths = before_players.groupby("track_id").size()
    after_lengths = after_players.groupby("track_id").size()
    report = MergeReport(
        n_tracks_before=int(before_players["track_id"].nunique()),
        n_tracks_after=int(after_players["track_id"].nunique()),
        median_track_length_before=float(before_lengths.median()) if len(before_lengths) else 0.0,
        median_track_length_after=float(after_lengths.median()) if len(after_lengths) else 0.0,
        concurrent_duplicates_culled=len(duplicate_losers),
        # Merge input is already-produced tracking output, not a fresh
        # producer emission; it predates the coordinate_space contract, so
        # coverage measurement uses the explicit legacy-corpus switch rather
        # than tripping the fail-closed coordinate_contract gate.
        coverage_before=_coverage(tracks, key, allow_legacy_undeclared=True),
        coverage_after=_coverage(after, key, allow_legacy_undeclared=True),
    )
    return mapping, report


def merge_csv(
    input_csv: str | Path,
    output_csv: str | Path,
    sport: str,
    motion_bounds: Mapping[str, Any] | str | Path | float,
) -> MergeReport:
    """Apply the merge map to one CSV and write the offline transformed copy."""
    tracks = pd.read_csv(input_csv)
    mapping, report = merge_tracklets(tracks, sport, motion_bounds)
    apply_tracklet_map(tracks, mapping).to_csv(output_csv, index=False)
    return report


tracklet_merge = merge_tracklets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("sport")
    parser.add_argument("motion_bounds", type=Path)
    args = parser.parse_args(argv)
    report = merge_csv(args.input_csv, args.output_csv, args.sport, args.motion_bounds)
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
