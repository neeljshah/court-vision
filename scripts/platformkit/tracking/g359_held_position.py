"""G359 held-position artifact vs threshold miscalibration (prepared, unscored).

Decides, per image-space gate that rejects the UNCHANGED arm in G358, between a
PRODUCTION_SCHEMA_ARTIFACT (rows written every frame, positions advanced only on
evaluated ticks) and a THRESHOLD_MISCALIBRATED reading of live motion. Sealed
definitions: `docs/evidence/tracking/g359_held_position_vs_threshold_2026-09-09/
g359_prereg_2026-09-09.md`. Gates, thresholds, the adapter and the arm
constructors are IMPORTED from the landed G358 / G353 modules, never copied.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from scripts.platformkit.liveness_metrics import thresholds_for
from scripts.platformkit.tracking.g358_gate_execution import (
    CONSTRUCTIBLE, _sha256, aggregate_gates, construct_arm, load_merged,
    evaluate_section_arm_duration)
from scripts.platformkit.tracking.production_schema_adapter import adapt_production_section

SPORT = "basketball"
DURATION = "FULL"
MODES = ("M0", "M1")
PREMISE_HELD_MIN = 0.20
CLEAR_BAR = 0.90
REJECT_BAR = 0.10
DEFAULT_GATES = ("zero_step_share", "distinct_position_ratio",
                 "stationary_track_share", "median_step_distance")
LEDGER_FIELDS = ("rows", "seconds", "source_fps", "decoded_frames", "evaluated_frames", "stride")
COUNT_KEYS = ("rows", "unique_frames", "tracks", "pairs_n", "held_n", "modal_frame_step")
_i = "{:06d}".format        # zero-padded integer cell
_f = "{:.6f}".format        # six-decimal share cell
_p = "{:04d}".format        # additive per-mille cell


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def latest_ledger_records(ledger_path: Path) -> dict[str, dict]:
    """Last record per ledger `game_id` by `finished_at` (the section id is that key)."""
    latest: dict[str, dict] = {}
    for line in ledger_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not (line.startswith("{") and line.endswith("}")):
            continue          # a partially written trailing line of the live ledger
        record = json.loads(line)
        key = str(record.get("game_id", ""))
        if key not in latest or (record.get("finished_at") or 0) >= (latest[key].get("finished_at") or 0):
            latest[key] = record
    return latest


def held_share(tracking_path: Path) -> dict[str, object]:
    """Byte-identical consecutive-position repeats within a track (sealed rule)."""
    table = pd.read_csv(tracking_path, dtype=str, keep_default_na=False,
                        usecols=["frame", "player_id", "x_position", "y_position"])
    numeric = pd.to_numeric(table["frame"], errors="coerce")
    ordered = table.assign(_sort=numeric).sort_values(["player_id", "_sort"], kind="stable")
    prev_x = ordered.groupby("player_id")["x_position"].shift(1)
    prev_y = ordered.groupby("player_id")["y_position"].shift(1)
    held_n = int((ordered["x_position"].eq(prev_x) & ordered["y_position"].eq(prev_y)).sum())
    tracks = int(table["player_id"].nunique())
    pairs_n = max(len(table) - tracks, 0)
    distinct = sorted(set(numeric.dropna().tolist()))
    steps = Counter(int(b - a) for a, b in zip(distinct, distinct[1:]) if b > a)
    return {"rows": len(table), "unique_frames": int(table["frame"].nunique()), "tracks": tracks,
            "pairs_n": pairs_n, "held_n": held_n,
            "modal_frame_step": steps.most_common(1)[0][0] if steps else 0,
            "held_share": held_n / pairs_n if pairs_n else 0.0}


def premise(sealed: Path, sections_dir: Path, ledger: Path, out: Path) -> list[dict[str, str]]:
    """Per sealed section: held share, the ledger stride fields, the modal frame step."""
    records = latest_ledger_records(ledger) if ledger.exists() else {}
    rows: list[dict[str, str]] = []
    for _, sealed_row in pd.read_csv(sealed, dtype=str).iterrows():
        name = sealed_row["section_name"]
        path = sections_dir / name / "tracking_data.csv"
        if not path.exists():
            print("ABSENT-SECTION {}".format(name))
            continue
        measured = held_share(path)
        record = records.get(name, {})
        row = {"section_name": name, "game_id": sealed_row["game_id"], "pool": sealed_row["pool"]}
        row.update({key: _i(measured[key]) for key in COUNT_KEYS})
        row["held_share"] = _f(measured["held_share"])
        row["held_permille"] = _p(round(1000 * measured["held_share"]))
        row.update({"ledger_" + field: ("" if record.get(field) is None else str(record[field]))
                    for field in LEDGER_FIELDS})
        decoded, evaluated = record.get("decoded_frames"), record.get("evaluated_frames")
        row["implied_stride"] = _f(decoded / evaluated) if decoded and evaluated else ""
        rows.append(row)
    if rows:
        _write(out, rows)
    top = max([float(row["held_share"]) for row in rows], default=0.0)
    verdict = "PREMISE FALSE" if rows and top < PREMISE_HELD_MIN else "PREMISE HOLDS"
    print("{} n={} max_held_share={}".format(verdict, len(rows), _f(top)))
    return rows


def collapse_held(table: pd.DataFrame | None) -> tuple[pd.DataFrame | None, int]:
    """Drop every PLAYER row whose (x, y) repeats the previous row of its track."""
    if table is None:
        return None, 0
    out = table.reset_index(drop=True)
    players = out.loc[out["cls"].eq("player")].sort_values(["track_id", "frame"], kind="stable")
    same_x = players["x"].eq(players.groupby("track_id")["x"].shift(1))
    same_y = players["y"].eq(players.groupby("track_id")["y"].shift(1))
    held = players.index[same_x & same_y]
    if len(held) == 0:
        return out, 0
    return out.drop(index=held).reset_index(drop=True), int(len(held))


def denominators(table: pd.DataFrame | None, dropped: int) -> dict[str, str]:
    """Raw and collapsed denominators of every per-frame statistic (sealed section 4)."""
    counts = dict.fromkeys(("rows_total", "player_rows", "ball_rows", "tracks",
                            "unique_frames", "steps_n"), 0)
    if table is not None:  # an arm that could not be constructed reports zeros
        players = table.loc[table["cls"].eq("player")]
        counts.update({"rows_total": len(table), "player_rows": len(players),
                       "ball_rows": len(table) - len(players),
                       "tracks": int(players["track_id"].nunique()),
                       "unique_frames": int(table["frame"].nunique())})
        counts["steps_n"] = max(counts["player_rows"] - counts["tracks"], 0)
    counts["held_rows_dropped"] = dropped
    return {key: _i(value) for key, value in counts.items()}


def section_records(name: str, pool: str, tracking_path: Path, ball_path: Path,
                    tracking_sha256: str, ball_sha256: str) -> list[dict[str, object]]:
    """Both modes x every constructible arm on one sealed section, gates unchanged."""
    for path, digest in ((tracking_path, tracking_sha256), (ball_path, ball_sha256)):
        if _sha256(path) != digest:
            raise ValueError("digest mismatch {} {}".format(name, path.name))
    adapted = adapt_production_section(load_merged(tracking_path, ball_path))
    records: list[dict[str, object]] = []
    for arm in CONSTRUCTIBLE:
        constructed = construct_arm(adapted.table, arm)
        for mode in MODES:
            # The plant is constructed BEFORE the collapse so the mode cannot hide one.
            table, dropped = (constructed, 0) if mode == "M0" else collapse_held(constructed)
            shape = denominators(table, dropped)
            for record in evaluate_section_arm_duration(
                    name, pool, arm, DURATION, table, adapted.frame_width,
                    adapted.frame_height, adapted.frame_size_source):
                record["mode"] = mode
                record.update(shape)
                records.append(record)
    return records


ARM_COLUMNS = ("section_name", "pool", "arm", "mode", "duration", "gate", "status", "reason",
               "measurement", "threshold", "rows_total", "player_rows", "ball_rows", "tracks",
               "unique_frames", "steps_n", "held_rows_dropped")


def arms(sealed: Path, sections_dir: Path, out: Path) -> None:
    """Run M0 and M1 over the sealed list; one row per section x arm x mode x gate."""
    rows: list[dict[str, str]] = []
    for _, sealed_row in pd.read_csv(sealed, dtype=str).iterrows():
        name = sealed_row["section_name"]
        section_dir = sections_dir / name
        if not (section_dir / "tracking_data.csv").exists():
            print("ABSENT-SECTION {}".format(name))
            continue
        for record in section_records(name, sealed_row["pool"],
                                      section_dir / "tracking_data.csv",
                                      section_dir / "ball_tracking.csv",
                                      sealed_row["tracking_sha256"], sealed_row["ball_sha256"]):
            record["section_name"] = record.pop("section")
            rows.append({key: ("" if record.get(key) is None else str(record.get(key, "")))
                         for key in ARM_COLUMNS})
    if rows:
        _write(out, rows)
    print("arms rows={} sections={}".format(len(rows), len({r["section_name"] for r in rows})))


def _direction(gate: str) -> str:
    """Read the sealed direction off the landed threshold key; never hand-copied."""
    keys = thresholds_for(SPORT)
    if gate + "_max" in keys:
        return "max"
    return "min" if gate + "_min" in keys else ""


def classify(clear_m0: float, clear_m1: float) -> str:
    """Sealed order: the exact M1 boundary at 0.90 belongs to the artifact class."""
    if clear_m1 >= CLEAR_BAR and clear_m0 < CLEAR_BAR:
        return "PRODUCTION_SCHEMA_ARTIFACT"
    if clear_m1 <= 1.0 - REJECT_BAR:  # float-safe form of reject_share_M1 >= REJECT_BAR
        return "THRESHOLD_MISCALIBRATED"
    return "UNDECIDED"


def decide(arms_csv: Path, diagnosis: Path | None, out: Path) -> list[dict[str, str]]:
    """Per failing gate: the paired M0/M1 clear shares, the class, the v2 candidate."""
    table = pd.read_csv(arms_csv, dtype=str, keep_default_na=False)
    table = table.loc[table["arm"].eq("A0") & table["duration"].eq(DURATION)]
    gates = DEFAULT_GATES
    if diagnosis is not None and diagnosis.exists():
        gates = tuple(pd.read_csv(diagnosis, dtype=str)["gate"].tolist())
    rows: list[dict[str, str]] = []
    for gate in gates:
        cell = table.loc[table["gate"].eq(gate)]
        by_mode = {mode: cell.loc[cell["mode"].eq(mode) & cell["status"].isin(("PASS", "REJECT"))]
                   .set_index("section_name") for mode in MODES}
        paired = sorted(set(by_mode["M0"].index) & set(by_mode["M1"].index))
        if not paired:
            continue
        clear = {mode: sum(1 for s in paired if by_mode[mode].loc[s, "status"] == "PASS")
                 / len(paired) for mode in MODES}
        values = {mode: [float(v) for v in by_mode[mode].loc[paired, "measurement"] if v != ""]
                  for mode in MODES}
        limits = [t for t in by_mode["M0"].loc[paired, "threshold"] if t != ""]
        classification = classify(clear["M0"], clear["M1"])
        quantile = {"max": 0.95, "min": 0.05}.get(_direction(gate))
        candidate = ""
        if classification == "THRESHOLD_MISCALIBRATED" and quantile and values["M1"]:
            candidate = _f(pd.Series(values["M1"]).quantile(quantile))
        rows.append({"gate": gate, "duration": DURATION, "n_paired": _i(len(paired)),
                     "clear_share_M0": _f(clear["M0"]), "clear_share_M1": _f(clear["M1"]),
                     "reject_share_M1": _f(1.0 - clear["M1"]),
                     "clear_permille_M0": _p(round(1000 * clear["M0"])),
                     "clear_permille_M1": _p(round(1000 * clear["M1"])),
                     "sealed_threshold": limits[0] if limits else "",
                     "statistic_median_M0": _f(pd.Series(values["M0"]).median()) if values["M0"] else "",
                     "statistic_median_M1": _f(pd.Series(values["M1"]).median()) if values["M1"] else "",
                     "candidate_v2_gate_name": gate + "_v2" if candidate else "",
                     "candidate_v2_quantile": "{:.2f}".format(quantile) if candidate else "",
                     "candidate_v2_threshold": candidate, "classification": classification})
        print("{} n_paired={} clear_M0={} clear_M1={} {}".format(gate, len(paired),
              _f(clear["M0"]), _f(clear["M1"]), classification))
    if rows:
        _write(out, rows)
    return rows


def check_default(arms_csv: Path, gates_csv: Path) -> int:
    """M0 must reproduce the landed G358 FULL cells, cell string by cell string."""
    table = pd.read_csv(arms_csv, dtype=str, keep_default_na=False)
    m0 = table.loc[table["mode"].eq("M0")]
    records = m0[["arm", "duration", "gate", "status"]].to_dict("records")
    landed = pd.read_csv(gates_csv, dtype=str, keep_default_na=False)
    landed = landed.loc[landed["duration"].eq(DURATION) & landed["arm"].isin(CONSTRUCTIBLE)]
    expected = {(r["arm"], r["duration"], r["gate"]): dict(r) for _, r in landed.iterrows()}
    mismatches = compared = 0
    for row in aggregate_gates(records):
        key = (row["arm"], row["duration"], row["gate"])
        landed_row = expected.get(key)
        if landed_row is None:
            print("MISSING-IN-LANDED {}".format(key))
            mismatches += 1
            continue
        for column, value in row.items():
            compared += 1
            if landed_row.get(column) != value:
                print("MISMATCH {} {} landed={} recomputed={}".format(
                    key, column, landed_row.get(column), value))
                mismatches += 1
    print("check-default compared_cells={} mismatches={}".format(compared, mismatches))
    return 1 if mismatches else 0


SUBCOMMANDS = (("premise", ("--sealed", "--sections-dir", "--ledger", "--out")),
               ("arms", ("--sealed", "--sections-dir", "--out")),
               ("decide", ("--arms", "--out", "--diagnosis")),
               ("check-default", ("--arms", "--gates")))


def main() -> None:
    parser = argparse.ArgumentParser(description="G359 held-position vs threshold")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, options in SUBCOMMANDS:
        child = sub.add_parser(name)
        for option in options:
            child.add_argument(option, type=Path, required=option != "--diagnosis")
    args = parser.parse_args()
    if args.command == "premise":
        premise(args.sealed, args.sections_dir, args.ledger, args.out)
    elif args.command == "arms":
        arms(args.sealed, args.sections_dir, args.out)
    elif args.command == "decide":
        decide(args.arms, args.diagnosis, args.out)
    else:
        raise SystemExit(check_default(args.arms, args.gates))


if __name__ == "__main__":
    main()
