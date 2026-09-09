"""G358 full-section image-space gate execution (fix 1c, complete eligible set).

Arms A1_FROZEN / A2_ID_MERGE / A5_BALL_SHIFT reuse the landed G348 constructor logic,
applied directly to the additive image-space table `production_schema_adapter` emits
(no court-feet conversion: production tables carry no calibration sidecar).
A3_SCALE_TRANSLATE / A4_MIRROR are UNIDENTIFIABLE by construction, reported not counted.
Durations are cut from ONE full-section construction (same start rule every duration).
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import pandas as pd

from scripts.platformkit.tracking.image_space_gates import GATE_ORDER, evaluate_image_space
from scripts.platformkit.tracking.production_schema_adapter import adapt_production_section

ARMS = ("A0", "A1_FROZEN", "A2_ID_MERGE", "A3_SCALE_TRANSLATE", "A4_MIRROR", "A5_BALL_SHIFT")
CONSTRUCTIBLE = ("A0", "A1_FROZEN", "A2_ID_MERGE", "A5_BALL_SHIFT")
UNIDENTIFIABLE_ARMS = ("A3_SCALE_TRANSLATE", "A4_MIRROR")
DURATIONS = (("FULL", None), ("30s", 30.0), ("10s", 10.0), ("2s", 2.0))
BALL_SHIFT_FRAMES = 30  # G348 convention: g348_gate_execution._fixture_records
SPORT = "basketball"


def _sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_merged(tracking_path: Path, ball_path: Path) -> pd.DataFrame:
    """Additive left-join: attach ball_x2d_px/ball_y2d_px onto tracking rows by frame."""
    tracking = pd.read_csv(tracking_path)
    ball = pd.read_csv(ball_path)
    px_cols = [c for c in ("ball_x2d_px", "ball_y2d_px") if c in ball.columns]
    if not px_cols:
        return tracking
    return tracking.merge(ball[["frame", *px_cols]], on="frame", how="left")


def arm_frozen(table: pd.DataFrame) -> pd.DataFrame:
    """A1_FROZEN: hold each player track at its first observed position (G348 logic)."""
    out = table.copy(deep=True)
    players = out["cls"].eq("player")
    out.loc[players, ["x", "y"]] = out.loc[players].groupby("track_id")[["x", "y"]].transform("first")
    return out


def arm_id_merge(table: pd.DataFrame) -> pd.DataFrame | None:
    """A2_ID_MERGE: fold the 2nd-busiest track of one team into the busiest (G348 logic)."""
    if "team" not in table.columns:
        return None
    out = table.copy(deep=True)
    players = out["cls"].eq("player")
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


def arm_ball_shift(table: pd.DataFrame) -> pd.DataFrame | None:
    """A5_BALL_SHIFT: displace the ball row's frame index by +30 (G348 convention)."""
    ball = table["cls"].eq("ball")
    if not ball.any():
        return None
    out = table.copy(deep=True)
    out.loc[ball, "frame"] = out.loc[ball, "frame"] + BALL_SHIFT_FRAMES
    return out


def construct_arm(full_table: pd.DataFrame, arm: str) -> pd.DataFrame | None:
    if arm == "A0":
        return full_table
    if arm == "A1_FROZEN":
        return arm_frozen(full_table)
    if arm == "A2_ID_MERGE":
        return arm_id_merge(full_table)
    if arm == "A5_BALL_SHIFT":
        return arm_ball_shift(full_table)
    raise ValueError("arm {} is not constructible".format(arm))


def duration_window(table: pd.DataFrame, t0: float, seconds: float | None) -> pd.DataFrame:
    """Same start rule at every duration: begin at t0, no future rows past t0+seconds."""
    if seconds is None:
        return table
    return table.loc[table["timestamp"] <= t0 + seconds]


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    phat = successes / n
    denom = 1.0 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
    return max(0.0, (center - margin) / denom), min(1.0, (center + margin) / denom)


def evaluate_section_arm_duration(section: str, pool: str, arm: str, duration_name: str,
                                  windowed: pd.DataFrame | None, frame_width, frame_height,
                                  frame_size_source: str) -> list[dict[str, object]]:
    records = []
    if windowed is None:
        for gate in GATE_ORDER:
            records.append({"section": section, "pool": pool, "arm": arm, "duration": duration_name,
                            "gate": gate, "status": "UNIDENTIFIABLE",
                            "reason": "arm_construction_unavailable", "measurement": None,
                            "threshold": None})
        return records
    try:
        rows = evaluate_image_space(windowed, SPORT, frame_width, frame_height, frame_size_source)
    except ValueError as exc:
        for gate in GATE_ORDER:
            records.append({"section": section, "pool": pool, "arm": arm, "duration": duration_name,
                            "gate": gate, "status": "REFUSED", "reason": str(exc),
                            "measurement": None, "threshold": None})
        return records
    for row in rows:
        records.append({"section": section, "pool": pool, "arm": arm, "duration": duration_name,
                        "gate": row["gate"], "status": row["status"], "reason": row["reason"],
                        "measurement": row["measurement"], "threshold": row["threshold"]})
    return records


def run_section(name: str, pool: str, tracking_path: Path, ball_path: Path,
                tracking_sha256: str, ball_sha256: str) -> list[dict[str, object]]:
    if _sha256(tracking_path) != tracking_sha256:
        raise ValueError("tracking digest mismatch {}".format(name))
    if _sha256(ball_path) != ball_sha256:
        raise ValueError("ball digest mismatch {}".format(name))
    merged = load_merged(tracking_path, ball_path)
    adapted = adapt_production_section(merged)
    full_table = adapted.table
    t0 = float(full_table["timestamp"].min())

    records: list[dict[str, object]] = []
    for arm in UNIDENTIFIABLE_ARMS:
        for duration_name, _ in DURATIONS:
            for gate in GATE_ORDER:
                records.append({"section": name, "pool": pool, "arm": arm, "duration": duration_name,
                                "gate": gate, "status": "UNIDENTIFIABLE",
                                "reason": "not constructible for image-space (sealed prereg)",
                                "measurement": None, "threshold": None})
    for arm in CONSTRUCTIBLE:
        constructed = construct_arm(full_table, arm)
        for duration_name, seconds in DURATIONS:
            windowed = None if constructed is None else duration_window(constructed, t0, seconds)
            records.extend(evaluate_section_arm_duration(
                name, pool, arm, duration_name, windowed,
                adapted.frame_width, adapted.frame_height, adapted.frame_size_source))
    return records


# Reached = an actual evaluate_image_space() status, not UNIDENTIFIABLE/REFUSED;
# independent of evaluated_n's PASS/REJECT-only share denominator (fix 1c).
REACHED_STATUSES = ("PASS", "REJECT", "NOT_APPLICABLE", "MEASURED_NO_BAR")


def aggregate_gates(records: list[dict[str, object]]) -> list[dict[str, str]]:
    """Per arm x duration x gate: reached/evaluated/rejected with n and Wilson bounds."""
    groups: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for r in records:
        key = (r["arm"], r["duration"], r["gate"])
        groups.setdefault(key, []).append(r)
    out = []
    for (arm, duration, gate), values in sorted(groups.items()):
        n = len(values)
        reached = sum(1 for v in values if v["status"] in REACHED_STATUSES)
        applicable = [v for v in values if v["status"] in ("PASS", "REJECT")]
        rejected = sum(1 for v in applicable if v["status"] == "REJECT")
        evaluated = len(applicable)
        share = rejected / evaluated if evaluated else 0.0
        lo, hi = wilson_interval(rejected, evaluated)
        out.append({"arm": arm, "duration": duration, "gate": gate, "n": f"{n:06d}",
                    "reached_n": f"{reached:06d}", "evaluated_n": f"{evaluated:06d}",
                    "rejected_n": f"{rejected:06d}", "rejection_share": f"{share:.6f}",
                    "rejection_permille": f"{round(1000 * share):04d}",
                    "wilson_lo_permille": f"{round(1000 * lo):04d}",
                    "wilson_hi_permille": f"{round(1000 * hi):04d}"})
    return out


def duration_table(records: list[dict[str, object]]) -> list[dict[str, str]]:
    """False rejection (A0) and detection (A1/A2/A5, any_gate) drift across durations."""
    out = []
    order = {d[0]: i for i, d in enumerate(DURATIONS)}
    for metric_type, arm, gate in _duration_cells(records):
        rows_by_duration = {d: [r for r in records if r["arm"] == arm and r["duration"] == d
                                and r["gate"] == gate] for d, _ in DURATIONS}
        for duration_name, values in sorted(rows_by_duration.items(), key=lambda kv: order[kv[0]]):
            applicable = [v for v in values if v["status"] in ("PASS", "REJECT")]
            rejected = sum(1 for v in applicable if v["status"] == "REJECT")
            evaluated = len(applicable)
            share = rejected / evaluated if evaluated else 0.0
            lo, hi = wilson_interval(rejected, evaluated)
            out.append({"metric_type": metric_type, "arm": arm, "gate": gate, "duration": duration_name,
                        "n": f"{evaluated:06d}", "rejected_n": f"{rejected:06d}",
                        "share": f"{share:.6f}", "wilson_lo_permille": f"{round(1000 * lo):04d}",
                        "wilson_hi_permille": f"{round(1000 * hi):04d}"})
    return out


def _duration_cells(records: list[dict[str, object]]):
    cells = {("FALSE_REJECTION", "A0", g) for g in GATE_ORDER}
    cells |= {("DETECTION", arm, "any_gate") for arm in ("A1_FROZEN", "A2_ID_MERGE", "A5_BALL_SHIFT")}
    return sorted(cells)


def diagnosis_table(records: list[dict[str, object]]) -> list[dict[str, str]]:
    """For every A0/FULL gate whose false rejection exceeds 0.05: statistic + class."""
    out = []
    for gate in GATE_ORDER:
        if gate == "any_gate":
            continue  # derived OR-of-gates roll-up, not a leaf gate with its own sealed threshold
        cell = [r for r in records if r["arm"] == "A0" and r["duration"] == "FULL" and r["gate"] == gate]
        applicable = [r for r in cell if r["status"] in ("PASS", "REJECT")]
        if not applicable:
            continue
        rejected = sum(1 for r in applicable if r["status"] == "REJECT")
        share = rejected / len(applicable)
        if share <= 0.05:
            continue
        values = sorted(float(r["measurement"]) for r in applicable if r["measurement"] is not None)
        threshold = next((r["threshold"] for r in applicable if r["threshold"] is not None), None)
        # Standard median/p90 (fix 1c: numpy.median / numpy.quantile(v, 0.9) equivalent).
        series = pd.Series(values) if values else None
        median = float(series.median()) if series is not None else None
        p90 = float(series.quantile(0.9)) if series is not None else None
        classification = _classify(gate, share, threshold, median)
        out.append({"gate": gate, "duration": "FULL", "n": f"{len(applicable):06d}",
                    "rejection_share": f"{share:.6f}",
                    "statistic_median": "" if median is None else f"{median:.6f}",
                    "statistic_p90": "" if p90 is None else f"{p90:.6f}",
                    "threshold": "" if threshold is None else str(threshold),
                    "classification": classification})
    return out


def _classify(gate: str, share: float, threshold, median) -> str:
    """Memo-only reseal proposal class; no threshold is moved here."""
    if gate in ("liveness_frozen", "duplicate_frame_identity", "insufficient_data"):
        return "PRODUCTION_SCHEMA_ARTIFACT"
    if threshold is not None and median is not None:
        return "THRESHOLD_MISCALIBRATED"
    return "DURATION_ARTIFACT"


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(sealed_csv: Path, sections_dir: Path, gates_out: Path, duration_out: Path,
       diagnosis_out: Path) -> list[dict[str, object]]:
    sealed = pd.read_csv(sealed_csv, dtype=str)
    all_records: list[dict[str, object]] = []
    for _, row in sealed.iterrows():
        name = row["section_name"]
        section_dir = sections_dir / name
        all_records.extend(run_section(name, row["pool"], section_dir / "tracking_data.csv",
                                       section_dir / "ball_tracking.csv",
                                       row["tracking_sha256"], row["ball_sha256"]))
    _write(gates_out, aggregate_gates(all_records))
    _write(duration_out, duration_table(all_records))
    diagnosis = diagnosis_table(all_records)
    if diagnosis:
        _write(diagnosis_out, diagnosis)
    return all_records


def main() -> None:
    parser = argparse.ArgumentParser(description="G358 fix 1b full-section gate execution")
    parser.add_argument("--sealed", required=True, type=Path)
    parser.add_argument("--sections-dir", required=True, type=Path)
    parser.add_argument("--gates", required=True, type=Path)
    parser.add_argument("--duration", required=True, type=Path)
    parser.add_argument("--diagnosis", required=True, type=Path)
    args = parser.parse_args()
    run(args.sealed, args.sections_dir, args.gates, args.duration, args.diagnosis)


if __name__ == "__main__":
    main()
