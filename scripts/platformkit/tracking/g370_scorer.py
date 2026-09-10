"""G370 M1 admission rows, v0 image gates, and evaluator-state construction."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import pandas as pd

from scripts.platformkit.eval_gate.walkforward import walk_forward
from scripts.platformkit.tracking.g358_gate_execution import (construct_arm, evaluate_section_arm_duration,
                                                                load_merged)
from scripts.platformkit.tracking.g359_held_position import collapse_held
from scripts.platformkit.tracking.g370_controls import measured_bars
from scripts.platformkit.tracking.g361_source_identity import sha256_file
from scripts.platformkit.tracking.production_schema_adapter import adapt_production_section
from scripts.platformkit.tracking.g370_export import write_export_hashes
from scripts.platformkit.tracking.g370_schema import (admission_status_for, new_admission_row,
                                                        position_observed, task_mask_for)
from scripts.platformkit.tracking.g370_ticks import tick_verification, verification_sha256

V0_GATES = ("zero_step_share", "distinct_position_ratio")
DETECTION_ARMS = ("A1_FROZEN", "A2_ID_MERGE")
PASSING = frozenset(("PASS",))


def _task_status(cells: Mapping[str, str]) -> str:
    if not cells:
        return "ABSENT"
    if any(status == "REJECT" for status in cells.values()):
        return "FAIL"
    if all(status in PASSING for status in cells.values()):
        return "PASS"
    return "ABSENT" if any(status in ("REFUSED", "UNIDENTIFIABLE") for status in cells.values()) else "NOT_APPLICABLE"


def _source(value: Any) -> str:
    value = str(value or "").upper()
    return value if value in ("DETECTION", "PREDICTION", "HELD", "UNKNOWN") else "UNKNOWN"


def _box(item: Mapping[str, Any]) -> list[Any] | None:
    keys = ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2")
    return [item.get(key) for key in keys] if all(key in item for key in keys) else None


def _observation(item: Mapping[str, Any], ball: bool = False) -> dict[str, Any]:
    source = _source(item.get("position_source"))
    observation = {"track_id": item.get("track_id"), "track_generation": item.get("track_generation"),
                   "bbox_px": _box(item), "xy_px": [item.get("x"), item.get("y")],
                   "position_source": source, "producer_branch_file_line": item.get("producer_branch_file_line"),
                   "attribution_evidence_sha256": item.get("attribution_evidence_sha256"),
                   "last_observed_pts": item.get("last_observed_pts"), "age_s": item.get("age_s"),
                   "observed": position_observed(source)}
    if ball:
        observation["observed_box_px"] = item.get("observed_box_px") or _box(item)
    return observation


def _gate_scores(section: str, pool: str, table: pd.DataFrame, adapted, mode: str) -> dict[str, dict[str, Any]]:
    cells = evaluate_section_arm_duration(section, pool, "A0", "FULL", table, adapted.frame_width,
                                          adapted.frame_height, adapted.frame_size_source)
    return {cell["gate"]: {"status": cell["status"], "measurement": cell["measurement"],
                            "threshold": cell["threshold"], "mode": mode} for cell in cells}


def _control_scores(section: str, pool: str, table: pd.DataFrame, adapted) -> dict[str, dict[str, Any]]:
    """Keep frozen and id-merge detection controls beside, not inside, M1 admission."""
    scores = {}
    for arm in DETECTION_ARMS:
        corrupted = construct_arm(table, arm)
        collapsed, _ = collapse_held(corrupted)
        cells = evaluate_section_arm_duration(section, pool, arm, "FULL", collapsed,
                                               adapted.frame_width, adapted.frame_height,
                                               adapted.frame_size_source)
        v0 = [value for value in cells if value["gate"] in V0_GATES]
        status = "REJECT" if any(value["status"] == "REJECT" for value in v0) else "UNIDENTIFIABLE"
        scores[arm] = {"status": status, "measurement": None, "threshold": None, "mode": "M1"}
    return scores


def _task_statuses(m1: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    position = _task_status({gate: str(m1.get(gate, {}).get("status", "ABSENT")) for gate in V0_GATES})
    return {"position": position, "geometry": "NOT_APPLICABLE"}


def _state_key(row: Mapping[str, Any]) -> str:
    """Return the preregistered evaluator identity for one verified tick."""
    return "{}:{}:{}:{}".format(row["game_id"], row["section_id"], row["frame_index"],
                                  row["evaluated_tick_id"])


def admission_rows(section: Mapping[str, Any], control_bars: Mapping[str, bool] | None = None,
                   plant_bars: Mapping[str, bool] | None = None) -> list[dict[str, Any]]:
    """Create one row per declared scheduled frame; require a non-circular schedule."""
    scheduled = section.get("scheduled_frames")
    if not isinstance(scheduled, list) or not scheduled:
        raise ValueError("section {} lacks declared scheduled_frames".format(section.get("section_id")))
    tracking, ball = Path(section["tracking_path"]), Path(section["ball_path"])
    merged = load_merged(tracking, ball)
    adapted = adapt_production_section(merged)
    m0 = construct_arm(adapted.table, "A0")
    m1, _ = collapse_held(m0)
    m0_scores = _gate_scores(section["section_id"], section.get("pool", "G370"), m0, adapted, "M0")
    m1_scores = _gate_scores(section["section_id"], section.get("pool", "G370"), m1, adapted, "M1")
    m1_scores["detection_controls"] = _control_scores(section["section_id"], section.get("pool", "G370"),
                                                         adapted.table, adapted)
    control_bars, plant_bars = control_bars or {}, plant_bars or {}
    statuses = _task_statuses(m1_scores)
    masks = task_mask_for(statuses, control_bars, plant_bars)
    table_sha, ball_sha = sha256_file(tracking), sha256_file(ball)
    rows = []
    for frame in sorted({int(value) for value in scheduled}):
        current = m1.loc[m1["frame"].eq(frame)]
        players = [_observation(row) for row in current.loc[current["cls"].eq("player")].to_dict("records")]
        balls = [_observation(row, ball=True) for row in current.loc[current["cls"].eq("ball")].to_dict("records")]
        tick_id, verified, tick_input = tick_verification(current, section, frame)
        row = new_admission_row(
            source_id=section.get("source_id"), source_uri=section.get("source_uri"),
            requested_start_s=section.get("requested_start_s"), requested_end_s=section.get("requested_end_s"),
            source_sha256=section.get("source_sha256"), byte_size=section.get("byte_size"),
            frame_sha256=None, table_sha256=table_sha, source_identity_status=section.get("source_identity_status", "UNKNOWN"),
            alignment_error_native_frames=section.get("alignment_error_native_frames"),
            deploy_manifest_sha256=section.get("deploy_manifest_sha256"), route_sha256=section.get("route_sha256"),
            weights_sha256=section.get("weights_sha256"), game_id=section.get("game_id"),
            competition=section.get("competition"), section_id=section["section_id"], frame_index=frame,
            pts=next(iter(current.get("timestamp", [])), None), timebase="source_pts",
            decoded_frame_count=section.get("decoded_frame_count"),
            evaluated_tick_id=tick_id,
            evaluated_tick_verified=verified, width=adapted.frame_width, height=adapted.frame_height,
            crop_xywh=section.get("crop_xywh"), pixel_transform_sha256=section.get("pixel_transform_sha256"),
            split=section.get("split"), inclusion_probability=section.get("inclusion_probability"),
            ball_x2d_px=None, ball_y2d_px=None, track_observations=players, ball_observations=balls,
            geometry_status="IMAGE_ONLY", gate_scores_m0=m0_scores, gate_scores_m1=m1_scores,
            gate_status_by_task=statuses, task_mask=masks, reason_codes=[],
            evidence_sha256s={"tracking_data.csv": table_sha, "ball_tracking.csv": ball_sha,
                              "tick_verification": verification_sha256(tick_input)},
            admission_spec_sha256=section.get("admission_spec_sha256"),
            admission_status=admission_status_for(statuses, control_bars, plant_bars), scorable=False)
        rows.append(row)
    return rows


def evaluator_states(rows: Iterable[Mapping[str, Any]], contexts: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Construct one stable evaluator state per verified M1 tick, never per section."""
    states = []
    for row in rows:
        if not row["evaluated_tick_verified"]:
            continue
        key = _state_key(row)
        if key not in contexts:
            raise ValueError("missing evaluator context for {}".format(key))
        state = dict(contexts[key])
        state["state_key"] = key
        states.append(state)
    if len({state["state_key"] for state in states}) != len(states):
        raise ValueError("duplicate evaluated tick state key")
    return states


def evaluate_comparison(states: list[dict[str, Any]], predictor: Callable) -> list[dict[str, Any]]:
    """Run a future outcome comparison only through the shared purged evaluator."""
    return walk_forward(states, predictor, strict_redaction=True, guard_state_keys=True).records


def _artifact_path(value: Any, base: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    return path if path.is_absolute() else base / path


def _manifest_sections(manifest: Path) -> tuple[list[Mapping[str, Any]], Path | None, Path | None]:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        sections, metadata = payload, payload[0] if payload else {}
    elif isinstance(payload, dict) and isinstance(payload.get("sections"), list):
        sections, metadata = payload["sections"], payload
    else:
        raise ValueError("manifest must be a section list or an object with sections")
    return sections, _artifact_path(metadata.get("controls_path"), manifest.parent), _artifact_path(
        metadata.get("plants_path"), manifest.parent)


def run_manifest(manifest: Path, out: Path, decisions: Path, census: Path) -> None:
    """Materialize declared sections and export twice; no hidden section selection occurs."""
    sections, controls_path, plants_path = _manifest_sections(manifest)
    control_bars, plant_bars = measured_bars(controls_path, plants_path)
    rows = []
    for section in sections:
        section_rows = admission_rows(section, control_bars, plant_bars)
        rows.extend(section_rows)
        _, _, ledger = tick_verification(pd.DataFrame(), section, 0)
        stride = ledger.get("implied_stride")
        if stride is None and any(row["evaluated_tick_verified"] for row in section_rows):
            stride = "MARKER"
        line = "TICKS section={} verified={} unverified={} stride={}".format(
            section.get("section_id"), sum(row["evaluated_tick_verified"] for row in section_rows),
            sum(not row["evaluated_tick_verified"] for row in section_rows),
            stride if stride is not None else "ABSENT")
        if ledger.get("reason"):
            line += " reason={}".format(ledger["reason"])
        print(line)
    hashes = write_export_hashes(rows, out, control_bars, plant_bars)
    decisions.parent.mkdir(parents=True, exist_ok=True)
    with decisions.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("game_id", "section_id", "frame_index", "evaluated_tick_id", "admission_status", "task_mask"))
        writer.writeheader()
        writer.writerows([{key: json.dumps(row[key], sort_keys=True) if key == "task_mask" else row[key]
                           for key in writer.fieldnames} for row in rows])
    with census.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("section_id", "scheduled_frames", "represented_frames", "missing_frames"))
        writer.writeheader()
        for section in sections:
            expected = {int(frame) for frame in section["scheduled_frames"]}
            actual = {int(row["frame_index"]) for row in rows if row["section_id"] == section["section_id"]}
            writer.writerow({"section_id": section["section_id"], "scheduled_frames": len(expected),
                             "represented_frames": len(actual), "missing_frames": len(expected - actual)})
    print("rows={} exports={}".format(len(rows), len(hashes)))


def main() -> None:
    parser = argparse.ArgumentParser(description="G370 admission scorer")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--denominator-census", required=True, type=Path)
    args = parser.parse_args()
    run_manifest(args.manifest, args.out, args.decisions, args.denominator_census)


if __name__ == "__main__":
    main()
