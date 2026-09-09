"""G366 gate confirmation on fresh sections: arms, stationary plant, reach, summary.

Sealed definitions: `docs/evidence/tracking/g366_gate_confirmation_2026-09-09/
g366_prereg_2026-09-09.md`. The gates, the thresholds, the adapter, the arm
constructors and the M1 collapse are IMPORTED from the landed G358 / G359 modules
and never copied; the v2 candidate is an ADDITIVE column and moves nothing.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import Counter
from pathlib import Path

for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "2")

import pandas as pd  # noqa: E402

from scripts.platformkit.tracking.g358_gate_execution import (  # noqa: E402
    _sha256, evaluate_section_arm_duration)
from scripts.platformkit.tracking.g359_held_position import (  # noqa: E402
    _f, _i, _write, ARM_COLUMNS, DURATION, MODES, collapse_held, section_records)
from scripts.platformkit.tracking.image_space_gates import GATE_ORDER  # noqa: E402
from scripts.platformkit.tracking.g366_fresh import (  # noqa: E402
    STRIP_MAX_BYTES, adapted_section, even_pick, selected_rows)

V2_GATE = "median_step_distance"
V2_THRESHOLD = 76.995468          # G359 decision.csv candidate_v2_threshold, unscored there
V2_DIRECTION = "max"              # REJECT when the measurement exceeds the threshold
PLANT_GATE = "stationary_track_share"
PLANT_TARGET = 10
PLANT_FRACTION = 0.30
PLANT_MIN = 3
BAR_A0 = 0.05
BAR_DETECTION = 0.80
TICK_BAND = (0.90, 1.10)
BAR_SECTIONS, BAR_GAMES = 30, 10
CONFIRM_GATES = ("zero_step_share", "distinct_position_ratio",
                 "stationary_track_share", V2_GATE)
DETECTION_ARMS = ("A1_FROZEN", "A2_ID_MERGE", "A5_BALL_SHIFT")
V2_COLUMNS = ("section_name", "arm", "mode", "gate", "measurement", "threshold_v1",
              "status_v1", "threshold_v2", "status_v2", "direction")
PLANT_COLUMNS = ("section_name", "mode", "tracks_unplanted", "plant_n", "plant_share_expected",
                 "threshold", "measurement_unplanted", "status_unplanted",
                 "measurement_planted", "status_planted", "detected")


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def v2_status(status: str, measurement: str) -> str:
    """Additive: v1's own status passes through unless the gate reached a bar."""
    if status not in ("PASS", "REJECT") or measurement == "":
        return status
    return "REJECT" if float(measurement) > V2_THRESHOLD else "PASS"


def v2_row(cell: dict[str, str]) -> dict[str, str]:
    return {"section_name": cell["section_name"], "arm": cell["arm"], "mode": cell["mode"],
            "gate": cell["gate"], "measurement": cell["measurement"],
            "threshold_v1": cell["threshold"], "status_v1": cell["status"],
            "threshold_v2": _f(V2_THRESHOLD),
            "status_v2": v2_status(cell["status"], cell["measurement"]),
            "direction": V2_DIRECTION}


def arms(sections: Path, sections_dir: Path, out: Path, v2_out: Path) -> None:
    """M0 and M1 over the selected fresh set through the landed G359 section runner."""
    rows: list[dict[str, str]] = []
    v2_rows: list[dict[str, str]] = []
    for row in selected_rows(sections):
        name = row["section_name"]
        for record in section_records(name, row["pool"],
                                      sections_dir / name / "tracking_data.csv",
                                      sections_dir / name / "ball_tracking.csv",
                                      row["tracking_sha256"], row["ball_sha256"]):
            record["section_name"] = record.pop("section")
            cell = {key: ("" if record.get(key) is None else str(record.get(key, "")))
                    for key in ARM_COLUMNS}
            rows.append(cell)
            if cell["gate"] == V2_GATE:
                v2_rows.append(v2_row(cell))
    _write(out, rows)
    _write(v2_out, v2_rows)
    print("arms rows={} sections={} v2_rows={}".format(
        len(rows), len({row["section_name"] for row in rows}), len(v2_rows)))


def plant_count(tracks: int) -> int:
    return max(PLANT_MIN, math.ceil(PLANT_FRACTION * tracks))


def plant_tracks(table: pd.DataFrame, count: int) -> pd.DataFrame:
    """Append `count` exactly frozen player tracks to a COPY; no row is modified."""
    players = table.loc[table["cls"].eq("player")]
    ids = pd.to_numeric(players["track_id"], errors="coerce")
    if ids.isna().any():
        raise ValueError("the sealed plant requires numeric player track ids")
    frames = sorted(players["frame"].unique())
    x0 = float(pd.to_numeric(players["x"], errors="coerce").median())
    y0 = float(pd.to_numeric(players["y"], errors="coerce").median())
    template, base = players.iloc[0].to_dict(), int(ids.max()) + 1
    planted = [dict(template, frame=frame, track_id=base + i, x=x0 + i, y=y0,
                    cls="player", scorable=False)
               for i in range(count) for frame in frames]
    return pd.concat((table, pd.DataFrame(planted)), ignore_index=True, sort=False)


def _gate_cell(name: str, pool: str, table: pd.DataFrame, adapted) -> dict[str, object]:
    records = evaluate_section_arm_duration(name, pool, "A0", DURATION, table,
                                            adapted.frame_width, adapted.frame_height,
                                            adapted.frame_size_source)
    return next(record for record in records if record["gate"] == PLANT_GATE)


def plant(sections: Path, sections_dir: Path, out: Path) -> list[dict[str, str]]:
    """The stationary control: a genuinely frozen track must still reject under M1."""
    rows: list[dict[str, str]] = []
    for row in even_pick(selected_rows(sections), PLANT_TARGET):
        name = row["section_name"]
        adapted = adapted_section(sections_dir, name)
        base = adapted.table
        tracks = int(base.loc[base["cls"].eq("player"), "track_id"].nunique())
        count = plant_count(tracks)
        spiked = plant_tracks(base, count)
        for mode in MODES:
            plain = base if mode == "M0" else collapse_held(base)[0]
            marked = spiked if mode == "M0" else collapse_held(spiked)[0]
            clean_cell, planted_cell = (_gate_cell(name, row["pool"], plain, adapted),
                                        _gate_cell(name, row["pool"], marked, adapted))
            rows.append({"section_name": name, "mode": mode, "tracks_unplanted": _i(tracks),
                         "plant_n": _i(count),
                         "plant_share_expected": _f(count / (tracks + count)),
                         "threshold": str(planted_cell["threshold"]),
                         "measurement_unplanted": str(clean_cell["measurement"]),
                         "status_unplanted": clean_cell["status"],
                         "measurement_planted": str(planted_cell["measurement"]),
                         "status_planted": planted_cell["status"],
                         "detected": "1" if planted_cell["status"] == "REJECT" else "0"})
    _write(out, [{key: row[key] for key in PLANT_COLUMNS} for row in rows])
    for mode in MODES:
        cell = [row for row in rows if row["mode"] == mode]
        hits = sum(1 for row in cell if row["detected"] == "1")
        print("plant mode={} n={} detected={} share={}".format(
            mode, len(cell), hits, _f(hits / len(cell)) if cell else _f(0.0)))
    return rows


def reach_table(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Per gate per mode on arm A0; NOT_APPLICABLE never enters a share numerator."""
    a0 = [row for row in rows if row["arm"] == "A0"]
    out: list[dict[str, str]] = []
    for mode in MODES:
        for gate in GATE_ORDER:
            cell = [row for row in a0 if row["mode"] == mode and row["gate"] == gate]
            if not cell:
                continue
            counts = Counter(row["status"] for row in cell)
            reached = counts["PASS"] + counts["REJECT"]
            causes = sorted({row["reason"] for row in cell
                             if row["status"] not in ("PASS", "REJECT")})
            out.append({"gate": gate, "mode": mode, "n": _i(len(cell)),
                        "pass_n": _i(counts["PASS"]), "reject_n": _i(counts["REJECT"]),
                        "not_applicable_n": _i(counts["NOT_APPLICABLE"]),
                        "other_n": _i(len(cell) - reached - counts["NOT_APPLICABLE"]),
                        "share_reachable": _f(reached / len(cell)),
                        "causes": "|".join(causes)})
    return out


def reach(gates: Path, out: Path) -> list[dict[str, str]]:
    rows = reach_table(_read(gates))
    _write(out, rows)
    blocked = [row["gate"] for row in rows if row["mode"] == "M1" and row["not_applicable_n"] != _i(0)]
    print("reach rows={} not_applicable_gates_M1={}".format(len(rows), ",".join(sorted(set(blocked)))))
    return rows


def rejection(rows: list[dict[str, str]], arm: str, gate: str, mode: str,
              field: str = "status") -> dict[str, object]:
    """rejected_n / evaluated_n with PASS and REJECT the only denominator members."""
    cell = [row for row in rows if row["arm"] == arm and row["mode"] == mode
            and row.get("gate") == gate and row[field] in ("PASS", "REJECT")]
    rejected = sum(1 for row in cell if row[field] == "REJECT")
    return {"n": len(cell), "rejected_n": rejected,
            "share": round(rejected / len(cell), 6) if cell else None}


def _v2_summary(rows: list[dict[str, str]]) -> dict[str, object]:
    def share(arm: str, field: str) -> dict[str, object]:
        return rejection(rows, arm, V2_GATE, "M1", field)
    return {"gate": V2_GATE, "threshold_v1": rows[0]["threshold_v1"] if rows else "",
            "threshold_v2": V2_THRESHOLD, "direction": V2_DIRECTION,
            "a0_M1_v1": share("A0", "status_v1"), "a0_M1_v2": share("A0", "status_v2"),
            "detection_v2": {arm: share(arm, "status_v2") for arm in DETECTION_ARMS}}


def _plant_summary(rows: list[dict[str, str]], mode: str) -> dict[str, object]:
    cell = [row for row in rows if row["mode"] == mode]
    hits = sum(1 for row in cell if row["detected"] == "1")
    return {"n": len(cell), "detected_n": hits,
            "share": round(hits / len(cell), 6) if cell else None}


def _tick_summary(rows: list[dict[str, str]]) -> dict[str, object]:
    ratios = [float(row["ratio_vs_evaluated"]) for row in rows if row["ratio_vs_evaluated"]]
    median = round(float(pd.Series(ratios).median()), 6) if ratios else None
    return {"n": len(rows), "with_ratio_n": len(ratios), "median_ratio": median,
            "in_band": bool(median is not None and TICK_BAND[0] <= median <= TICK_BAND[1])}


def summary(evidence: Path, out: Path) -> dict[str, object]:
    """Every bar of the prereg beside its measured value, plus the artifact digests."""
    sections = _read(evidence / "fresh_sections.csv")
    selected = [row for row in sections if row.get("selected") == "1"]
    games = {row["game_id"] for row in selected}
    gates = _read(evidence / "gates_fresh.csv")
    payload = {
        "fresh_set": {"census_n": len(sections),
                      "eligible_n": sum(1 for row in sections if row["eligible"] == "1"),
                      "selected_n": len(selected), "games_n": len(games),
                      "meets_bar": len(selected) >= BAR_SECTIONS and len(games) >= BAR_GAMES},
        "a0_rejection": {gate: {mode: rejection(gates, "A0", gate, mode) for mode in MODES}
                         for gate in CONFIRM_GATES},
        "detection_any_gate": {arm: {mode: rejection(gates, arm, "any_gate", mode)
                                     for mode in MODES} for arm in DETECTION_ARMS},
        "v2": _v2_summary(_read(evidence / "v2.csv")),
        "plants": {mode: _plant_summary(_read(evidence / "plants.csv"), mode) for mode in MODES},
        "ticks": _tick_summary(_read(evidence / "ticks.csv")),
        "reach": {row["gate"] + "/" + row["mode"]: row["share_reachable"]
                  for row in _read(evidence / "reach.csv")},
        "strips_n": len(sorted((evidence / "strips").glob("*.svg"))),
        "bars": {"a0_rejection_max": BAR_A0, "detection_min": BAR_DETECTION,
                 "tick_ratio_band": list(TICK_BAND), "sections_min": BAR_SECTIONS,
                 "games_min": BAR_GAMES, "strip_max_bytes": STRIP_MAX_BYTES},
        "sha256": {path.name: _sha256(path) for path in sorted(evidence.glob("*.csv"))},
    }
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("summary sections={} games={} strips={}".format(
        len(selected), len(games), payload["strips_n"]))
    return payload


SUBCOMMANDS = (("arms", ("--sections", "--sections-dir", "--out", "--v2-out")),
               ("plant", ("--sections", "--sections-dir", "--out")),
               ("reach", ("--gates", "--out")),
               ("summary", ("--evidence", "--out")))


def main() -> None:
    parser = argparse.ArgumentParser(description="G366 gate confirmation on fresh sections")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, options in SUBCOMMANDS:
        child = sub.add_parser(name)
        for option in options:
            child.add_argument(option, type=Path, required=True)
    args = parser.parse_args()
    if args.command == "arms":
        arms(args.sections, args.sections_dir, args.out, args.v2_out)
    elif args.command == "plant":
        plant(args.sections, args.sections_dir, args.out)
    elif args.command == "reach":
        reach(args.gates, args.out)
    else:
        summary(args.evidence, args.out)


if __name__ == "__main__":
    main()
