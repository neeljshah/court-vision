"""G370 pre-adaptation frozen, coast, and id-merge control constructors."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from scripts.platformkit.tracking.g358_gate_execution import (REACHED_STATUSES, evaluate_section_arm_duration,
                                                                load_merged)
from scripts.platformkit.tracking.g359_held_position import collapse_held
from scripts.platformkit.tracking.production_schema_adapter import adapt_production_section

KINDS = ("FROZEN", "COAST", "ID_MERGE")
V0_GATES = ("zero_step_share", "distinct_position_ratio")


def _ordered_players(source: pd.DataFrame) -> pd.DataFrame:
    return source.sort_values(["player_id", "frame"], kind="stable")


def corrupt_before_adaptation(source: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Return a copy with one sealed corruption applied before adapter translation."""
    if kind not in KINDS:
        raise ValueError("unknown control kind {}".format(kind))
    out = source.copy(deep=True)
    if kind == "FROZEN":
        ordered = _ordered_players(out)
        first = ordered.groupby("player_id")[["x_position", "y_position"]].transform("first")
        out.loc[ordered.index, ["x_position", "y_position"]] = first
    elif kind == "ID_MERGE":
        counts = out.groupby("player_id").size().sort_values(ascending=False)
        if len(counts) < 2:
            raise ValueError("id-merge control requires two player tracks")
        out.loc[out["player_id"].eq(counts.index[1]), "player_id"] = counts.index[0]
    else:
        ordered = _ordered_players(out)
        numeric_frame = pd.to_numeric(ordered["frame"], errors="coerce")
        tracks = ordered.assign(_frame=numeric_frame).groupby("player_id", sort=False)
        velocity = pd.concat([_coast_track(track) for _, track in tracks])
        out.loc[velocity.index, ["x_position", "y_position"]] = velocity[["x_position", "y_position"]]
    return out


def _coast_track(track: pd.DataFrame) -> pd.DataFrame:
    """Extrapolate every row from the last observation using a moving step."""
    result = track[["x_position", "y_position"]].copy()
    if len(track) < 2:
        raise ValueError("coast plant unconstructible: fewer than two rows")
    first = second = None
    for index in range(1, len(track)):
        candidate, previous = track.iloc[index], track.iloc[index - 1]
        if (float(candidate["_frame"]) != float(previous["_frame"])
                and (float(candidate["x_position"]) != float(previous["x_position"])
                     or float(candidate["y_position"]) != float(previous["y_position"]))):
            first, second = previous, candidate
            break
    if first is None or second is None:
        raise ValueError("coast plant unconstructible: no nonzero position step")
    last = track.iloc[-1]
    try:
        step_frames = float(second["_frame"]) - float(first["_frame"])
        vx = (float(second["x_position"]) - float(first["x_position"])) / step_frames
        vy = (float(second["y_position"]) - float(first["y_position"])) / step_frames
        dt = track["_frame"].astype(float) - float(last["_frame"])
        result["x_position"] = float(last["x_position"]) + vx * dt
        result["y_position"] = float(last["y_position"]) + vy * dt
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise ValueError("coast plant unconstructible: invalid step") from exc
    return result


def control_result(section: Mapping[str, Any], kind: str) -> dict[str, Any]:
    """Score one declared plant without writing source tables or hiding unidentifiable cases."""
    source = load_merged(Path(section["tracking_path"]), Path(section["ball_path"]))
    try:
        adapted = adapt_production_section(corrupt_before_adaptation(source, kind))
    except ValueError as exc:
        if kind == "COAST" and str(exc).startswith("coast plant unconstructible"):
            print("PLANT-UNCONSTRUCTIBLE section={} kind=COAST".format(section["section_id"]))
            return {"section_id": section["section_id"], "kind": kind, "identifiable": 0,
                    "detected": 0, "status": "UNIDENTIFIABLE"}
        raise
    collapsed, _ = collapse_held(adapted.table)
    cells = evaluate_section_arm_duration(section["section_id"], section.get("pool", "G370"), "A0", "FULL",
                                          collapsed, adapted.frame_width, adapted.frame_height,
                                          adapted.frame_size_source)
    v0 = [item for item in cells if item["gate"] in V0_GATES]
    detected = any(item["status"] == "REJECT" for item in v0)
    reached = any(item["status"] in REACHED_STATUSES for item in v0)
    status = "REJECT" if detected else "UNIDENTIFIABLE"
    return {"section_id": section["section_id"], "kind": kind, "identifiable": int(reached),
            "detected": int(detected), "status": status if reached else "UNIDENTIFIABLE"}


def _as_bool(value: Any) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "pass", "reject")


def _usable(row: Mapping[str, str]) -> bool:
    return "usable" not in row or _as_bool(row.get("usable", ""))


def _rejected(row: Mapping[str, str]) -> bool | None:
    status = row.get("status", "").strip().upper()
    if status in ("PASS", "REJECT"):
        return status == "REJECT"
    if "rejected" in row:
        return _as_bool(row["rejected"])
    return None


def _control_bars(path: Path | None) -> dict[str, bool]:
    if path is None or not path.exists():
        return {}
    values: dict[str, list[tuple[bool, str]]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rejected = _rejected(row)
            if rejected is None or not _usable(row):
                continue
            task = row.get("task", "position").strip() or "position"
            values.setdefault(task, []).append((rejected, row.get("game_id", "").strip()))
    return {task: len(rows) >= 30 and len({game for _, game in rows if game}) >= 10
            and sum(rejected for rejected, _ in rows) / len(rows) <= 0.05
            for task, rows in values.items()}


def _plant_measurements(path: Path | None) -> dict[str, dict[str, list[bool]]]:
    if path is None or not path.exists():
        return {}
    values: dict[str, dict[str, list[bool]]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            task = row.get("task", "position").strip() or "position"
            values.setdefault(task, {})
            if not _as_bool(row.get("identifiable", "")):
                continue
            kind = row.get("kind", "").strip()
            if kind in KINDS:
                values[task].setdefault(kind, []).append(_as_bool(row.get("detected", "")))
    return values


def _plant_bars(path: Path | None) -> dict[str, bool]:
    values = _plant_measurements(path)
    return {task: all(len(kinds.get(kind, [])) >= 30
                      and sum(kinds.get(kind, [])) / len(kinds.get(kind, [])) >= 0.80
                      for kind in KINDS)
            for task, kinds in values.items()}


def plant_bar_report(path: Path | None) -> dict[str, dict[str, tuple[int, float | None]]]:
    """Return every required kind's identifiable count and detection rate by task."""
    values = _plant_measurements(path)
    return {task: {kind: (len(kinds.get(kind, [])),
                         sum(kinds.get(kind, [])) / len(kinds[kind]) if kinds.get(kind) else None)
                   for kind in KINDS}
            for task, kinds in values.items()}


def measured_bars(controls_path: Path | None, plants_path: Path | None) -> tuple[dict[str, bool], dict[str, bool]]:
    """Derive sealed task bars from measured control and plant artifacts only."""
    return _control_bars(controls_path), _plant_bars(plants_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="G370 plant controls")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    rows = [control_result(section, section["kind"]) for section in
            json.loads(args.manifest.read_text(encoding="utf-8"))]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("section_id", "kind", "identifiable", "detected", "status"))
        writer.writeheader()
        writer.writerows(rows)
    for task, kinds in plant_bar_report(args.out).items():
        for kind, (count, rate) in kinds.items():
            rate_text = "ABSENT" if rate is None else "{:.4f}".format(rate)
            print("PLANT-BAR task={} kind={} identifiable={} detection_rate={}".format(
                task, kind, count, rate_text))
        missing = [kind for kind, (count, _) in kinds.items() if count == 0]
        if missing:
            print("PARTIAL task={} zero_identifiable={}".format(task, ",".join(missing)))
    print("plants={}".format(len(rows)))


if __name__ == "__main__":
    main()
