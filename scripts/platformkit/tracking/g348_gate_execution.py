"""G348 valid-fixture gate accounting using the unchanged tracking harness."""
from __future__ import annotations

import argparse
import csv
import hashlib
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit.coordinate_provenance import stamp_court_space_rows
from scripts.platformkit.court_transform import load_court_calibration, to_court_feet
from scripts.platformkit.tracking.g343_attack_test import GATES, gate_statuses
from scripts.platformkit.tracking_harness import evaluate

ARMS = ("A0", "A1_FROZEN", "A2_ID_MERGE", "A3_SCALE_TRANSLATE", "A4_MIRROR",
        "A5_BALL_SHIFT", "C0_CONTRACT_INVALID")
_REQUIRED = {"fixture_id", "game_id", "league", "tracking_path", "sidecar_path",
             "window_start", "window_end", "tracking_sha256", "sidecar_sha256"}


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reason_class(reason: str) -> str:
    if reason.startswith("accepted"):
        return "ACCEPTED"
    if "coordinate" in reason:
        return "COORDINATE_CONTRACT"
    if "ball" in reason:
        return "BALL_BLIND"
    if "construction" in reason:
        return "CONSTRUCTION"
    if "insufficient" in reason:
        return "INSUFFICIENT_DATA"
    return reason.split(" ", 1)[0].upper().replace("-", "_")


def _record(fixture: str, arm: str, gate: str, status: str, reason: str) -> dict[str, object]:
    refused = status == "REFUSED"
    evaluated = status in {"PASS", "REJECT"}
    return {"fixture_id": fixture, "arm": arm, "gate": gate, "status": status,
            "reason_class": _reason_class(reason), "reached": int(evaluated),
            "evaluated": int(evaluated), "rejected": int(status == "REJECT"),
            "refused": int(refused)}


def _court_arm(court: pd.DataFrame, arm: str) -> pd.DataFrame | None:
    """Return one declared coordinate corruption, or None when not constructible."""
    out = court.copy(deep=True)
    players = out["cls"].eq("player")
    if arm == "A0":
        return out
    if arm == "A1_FROZEN":
        out.loc[players, ["x", "y"]] = out.loc[players].groupby("track_id")[["x", "y"]].transform("first")
        return out
    if arm == "A2_ID_MERGE":
        groups = out.loc[players].groupby(["team", "track_id"]).size().reset_index(name="n")
        choices = [group.sort_values(["n", "track_id"], ascending=[False, True]).head(2)
                   for _, group in groups.groupby("team")]
        choices = [choice for choice in choices if len(choice) == 2]
        if not choices:
            return None
        choice = sorted(choices, key=lambda item: (-int(item.iloc[0].n), str(item.iloc[0].team)))[0]
        out.loc[(out["team"] == choice.iloc[1].team) & (out["track_id"] == choice.iloc[1].track_id),
                "track_id"] = choice.iloc[0].track_id
        return out
    if arm == "A3_SCALE_TRANSLATE":
        out.loc[players, "x"] = 0.9 * (out.loc[players, "x"] - 47.0) + 47.0 + 4.7
        out.loc[players, "y"] = 0.9 * (out.loc[players, "y"] - 25.0) + 25.0 + 2.5
        return out
    if arm == "A4_MIRROR":
        out.loc[players, "x"] = 94.0 - out.loc[players, "x"]
        return out
    return None


def _to_production(court: pd.DataFrame, raw: pd.DataFrame, calibration: dict) -> pd.DataFrame:
    """Map court-coordinate twins back through the authentic transform only."""
    matrix = np.linalg.inv(np.asarray(calibration["map2d_to_feet"], dtype=float))
    points = np.column_stack((court["x"].to_numpy(float), court["y"].to_numpy(float), np.ones(len(court))))
    mapped = points @ matrix.T
    if np.any(np.isclose(mapped[:, 2], 0.0)):
        raise ValueError("inverse transform reaches infinity")
    out = raw.copy(deep=True)
    out["x_position"] = mapped[:, 0] / mapped[:, 2]
    out["y_position"] = mapped[:, 1] / mapped[:, 2]
    out["player_id"] = court["track_id"].to_numpy()
    return out


def status_map(frame: pd.DataFrame, arm: str, attempted_frames: int,
               source: str | None = None) -> dict[str, tuple[str, str]]:
    """Return imported-harness statuses; invalid-contract control is REFUSED."""
    if arm == "A5_BALL_SHIFT":
        return {gate: ("UNIDENTIFIABLE", "harness has no ball-table input")
                for gate in (*GATES, "any_gate")}
    candidate = frame.copy(deep=True)
    if arm == "C0_CONTRACT_INVALID":
        candidate["coordinate_space"] = "image_px"
        statuses = gate_statuses(evaluate(candidate, "basketball", source=source,
                                          attempted_frames=attempted_frames))
        return {gate: (("REFUSED", reason) if gate == "coordinate_contract" else
                       ("UNIDENTIFIABLE", "contract refusal stopped metric gates"))
                for gate, (_, reason) in statuses.items()}
    report = evaluate(candidate, "basketball", source=source, attempted_frames=attempted_frames)
    return gate_statuses(report)


def _fixture_records(row: pd.Series) -> list[dict[str, object]]:
    tracking, sidecar = str(row.tracking_path), str(row.sidecar_path)
    if _sha256(tracking) != row.tracking_sha256 or _sha256(sidecar) != row.sidecar_sha256:
        raise ValueError("fixture digest mismatch {}".format(row.fixture_id))
    raw = pd.read_csv(tracking)
    raw = raw.loc[raw["frame"].between(int(row.window_start), int(row.window_end))].copy()
    calibration = load_court_calibration(sidecar)
    court = to_court_feet(raw, calibration)
    court["track_id"] = court["player_id"]
    court["cls"] = "player"
    court = stamp_court_space_rows(court, "basketball")
    attempted = int(court["frame"].nunique())
    records: list[dict[str, object]] = []
    for arm in ARMS:
        candidate = court if arm == "C0_CONTRACT_INVALID" else _court_arm(court, arm)
        if arm == "A5_BALL_SHIFT":
            ball_path = str(row.get("ball_path", ""))
            if ball_path and Path(ball_path).is_file():
                if row.get("ball_sha256") and _sha256(ball_path) != row.ball_sha256:
                    raise ValueError("ball fixture digest mismatch {}".format(row.fixture_id))
                ball = pd.read_csv(ball_path)
                ball["frame"] = ball["frame"] + 30
            statuses = status_map(court, arm, attempted)
        elif candidate is None:
            statuses = {gate: ("UNIDENTIFIABLE", "arm construction unavailable")
                        for gate in (*GATES, "any_gate")}
        elif arm in {"C0_CONTRACT_INVALID"}:
            statuses = status_map(candidate, arm, attempted)
        else:
            production = _to_production(candidate, raw, calibration)
            statuses = status_map(production, arm, attempted, sidecar)
        records.extend(_record(str(row.fixture_id), arm, gate, status, reason)
                       for gate, (status, reason) in statuses.items())
    return records


def aggregate_gates(records: list[dict[str, object]]) -> list[dict[str, str]]:
    """Aggregate additive per-gate denominators without re-scoring fixtures."""
    groups: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for record in records:
        groups[(str(record["arm"]), str(record["gate"]), str(record["status"]),
                str(record["reason_class"]))].append(record)
    rows = []
    for key, values in sorted(groups.items()):
        n = len(values)
        rejected = sum(int(value["rejected"]) for value in values)
        rows.append({"arm": key[0], "gate": key[1], "status": key[2], "reason_class": key[3],
                     "n": f"{n:06d}", "reached_n": f"{sum(int(v['reached']) for v in values):06d}",
                     "evaluated_n": f"{sum(int(v['evaluated']) for v in values):06d}",
                     "rejected_n": f"{rejected:06d}", "refused_n": f"{sum(int(v['refused']) for v in values):06d}",
                     "rejection_share": f"{rejected / n:.6f}",
                     "rejection_permille": f"{round(1000 * rejected / n):04d}"})
    return rows


def detection_rows(records: list[dict[str, object]]) -> list[dict[str, str]]:
    """Summarize any-gate detection; REFUSED and UNIDENTIFIABLE stay out of n."""
    rows = []
    for arm in ARMS:
        cells = [row for row in records if row["arm"] == arm and row["gate"] == "any_gate"]
        applicable = [row for row in cells if row["status"] in {"PASS", "REJECT"}]
        rejected = sum(int(row["rejected"]) for row in applicable)
        share = rejected / len(applicable) if applicable else 0.0
        rows.append({"arm": arm, "fixture_n": f"{len(cells):06d}",
                     "applicable_n": f"{len(applicable):06d}", "detected_n": f"{rejected:06d}",
                     "detection_share": f"{share:.6f}", "detection_permille": f"{round(1000 * share):04d}",
                     "false_rejection_share": f"{share if arm == 'A0' else 0.0:.6f}",
                     "false_rejection_permille": f"{round(1000 * share) if arm == 'A0' else 0:04d}"})
    return rows


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(fixtures_path: Path, gates_path: Path, detection_path: Path) -> None:
    """Run one authentic fixture table at a time after sealed-input checks."""
    fixtures = pd.read_csv(fixtures_path, dtype=str)
    if _REQUIRED - set(fixtures) or len(fixtures) < 30 or fixtures.fixture_id.duplicated().any():
        raise ValueError("fixtures require unique ids, >=30 rows, and sealed required columns")
    if fixtures.game_id.nunique() < 3 or fixtures.loc[fixtures.league.str.lower().eq("wnba")].game_id.nunique() < 2:
        raise ValueError("fixtures require >=3 games including two WNBA tables")
    records = [record for _, row in fixtures.iterrows() for record in _fixture_records(row)]
    _write(gates_path, aggregate_gates(records))
    _write(detection_path, detection_rows(records))


def main() -> None:
    parser = argparse.ArgumentParser(description="G348 authentic-sidecar gate execution")
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument("--gates", required=True, type=Path)
    parser.add_argument("--detection", required=True, type=Path)
    args = parser.parse_args()
    run(args.fixtures, args.gates, args.detection)


if __name__ == "__main__":
    main()
