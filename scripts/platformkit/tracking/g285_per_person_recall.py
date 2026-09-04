"""Render frozen G267 footpoints and summarize pre-committed G285 verdicts."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import cv2


COURT_X_MAX = 50.0
COURT_Y_MAX = 94.0
MARKER_RADIUS_PX = 7
MARKER_FILL_BGR = (255, 0, 255)
MARKER_OUTLINE_BGR = (0, 0, 0)


def on_court(detection: dict[str, Any]) -> bool:
    """Apply G270's unchanged inclusive court rectangle."""
    return (bool(detection["finite"]) and 0 <= float(detection["court_x_ft"]) <= COURT_X_MAX
            and 0 <= float(detection["court_y_ft"]) <= COURT_Y_MAX)


def read_counted_frames(path: Path) -> list[dict[str, str]]:
    """Load G284's sealed judgeable frames in its committed blind order."""
    with path.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    counted = [row for row in rows if row["count_status"] == "COUNTED"]
    if len(rows) != 61 or len(counted) != 54:
        raise ValueError("G284 must contain 61 rows with 54 COUNTED frames")
    if [int(row["blind_id"]) for row in rows] != list(range(61)):
        raise ValueError("G284 blind order changed")
    return counted


def marker_rows(g267_path: Path, frames: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Return G270-on-court footpoints for only G284's judgeable frames."""
    source = json.loads(g267_path.read_text(encoding="ascii"))
    records = {int(row["source_frame"]): row for row in source["frame_records"]}
    if len(records) != len(source["frame_records"]):
        raise ValueError("duplicate G267 frame record")
    output: list[dict[str, Any]] = []
    for frame in frames:
        blind_id, source_frame = int(frame["blind_id"]), int(frame["source_frame"])
        detections = records[source_frame]["detections"]
        for marker_index, detection in enumerate(row for row in detections if on_court(row)):
            output.append({
                "blind_id": blind_id, "source_frame": source_frame,
                "marker_index": marker_index, "track_id": int(detection["track_id"]),
                "foot_x_px": float(detection["foot_x_px"]), "foot_y_px": float(detection["foot_y_px"]),
            })
    return output


def write_markers(rows: list[dict[str, Any]], path: Path) -> None:
    """Write stable marker identities beside the marker-only renders."""
    fields = ["blind_id", "source_frame", "marker_index", "track_id", "foot_x_px", "foot_y_px"]
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def render(args: argparse.Namespace) -> None:
    """Render all and only G284 judgeable frames with frozen marker locations."""
    frames = read_counted_frames(args.per_frame_join)
    markers = marker_rows(args.g267, frames)
    by_frame: dict[int, list[dict[str, Any]]] = {}
    for marker in markers:
        by_frame.setdefault(marker["blind_id"], []).append(marker)
    args.render_dir.mkdir(parents=True, exist_ok=True)
    for frame in frames:
        source = args.frames_dir / frame["frame_file"]
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None or image.shape[:2] != (1080, 1920):
            raise ValueError("unexpected source image: %s" % source)
        for marker in by_frame.get(int(frame["blind_id"]), []):
            point = (round(marker["foot_x_px"]), round(marker["foot_y_px"]))
            cv2.circle(image, point, MARKER_RADIUS_PX + 1, MARKER_OUTLINE_BGR, -1, cv2.LINE_AA)
            cv2.circle(image, point, MARKER_RADIUS_PX, MARKER_FILL_BGR, -1, cv2.LINE_AA)
        output = args.render_dir / ("blind_%03d_frame_%05d.jpg" % (int(frame["blind_id"]), int(frame["source_frame"])))
        if not cv2.imwrite(str(output), image):
            raise OSError("failed to write %s" % output)
    write_markers(markers, args.marker_manifest)
    print("Rendered 54 G284 judgeable frames and wrote marker manifest")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def wilson(successes: int, total: int) -> dict[str, float]:
    """Return the two-sided 95 percent Wilson interval."""
    if not 0 <= successes <= total or total == 0:
        raise ValueError("invalid Wilson numerator or denominator")
    z = 1.959963984540054
    proportion, z2 = successes / total, z * z
    centre = (proportion + z2 / (2 * total)) / (1 + z2 / total)
    half = z * math.sqrt(proportion * (1 - proportion) / total + z2 / (4 * total * total)) / (1 + z2 / total)
    return {"estimate": proportion, "lower": centre - half, "upper": centre + half}


def validate_verdicts(frames: list[dict[str, str]], markers: list[dict[str, Any]], people: list[dict[str, str]], marker_verdicts: list[dict[str, str]]) -> None:
    """Enforce exhaustive, one-to-one, per-person and per-marker judgements."""
    expected_people = {(int(frame["blind_id"]), slot)
                       for frame in frames for slot in range(1, int(frame["players_visible_on_court"]) + 1)}
    actual_people = {(int(row["blind_id"]), int(row["player_slot"])) for row in people}
    if actual_people != expected_people or len(people) != len(expected_people):
        raise ValueError("per-person verdicts do not exactly cover sealed player slots")
    expected_markers = {(int(row["blind_id"]), int(row["marker_index"])) for row in markers}
    actual_markers = {(int(row["blind_id"]), int(row["marker_index"])) for row in marker_verdicts}
    if actual_markers != expected_markers or len(marker_verdicts) != len(expected_markers):
        raise ValueError("per-marker verdicts do not exactly cover rendered markers")
    person_links: dict[tuple[int, int], tuple[int, int]] = {}
    for row in people:
        verdict = row["verdict"]
        key = (int(row["blind_id"]), int(row["player_slot"]))
        if verdict not in {"MATCHED", "UNMATCHED"} or row["near_boundary"] not in {"YES", "NO"}:
            raise ValueError("invalid person verdict")
        if verdict == "MATCHED":
            person_links[key] = (key[0], int(row["marker_index"]))
        elif row["marker_index"]:
            raise ValueError("unmatched person has a marker assignment")
    marker_links: dict[tuple[int, int], tuple[int, int]] = {}
    for row in marker_verdicts:
        verdict = row["verdict"]
        key = (int(row["blind_id"]), int(row["marker_index"]))
        if verdict not in {"MATCHED", "UNMATCHED"}:
            raise ValueError("invalid marker verdict")
        if verdict == "MATCHED":
            marker_links[key] = (key[0], int(row["player_slot"]))
        elif row["player_slot"]:
            raise ValueError("unmatched marker has a player assignment")
    if set(marker_links.values()) != set(person_links):
        raise ValueError("per-person and per-marker assignments disagree")


def summarize(args: argparse.Namespace) -> None:
    """Compute summary only from the committed exhaustive human verdict tables."""
    frames, markers = read_counted_frames(args.per_frame_join), read_csv(args.marker_manifest)
    people, marker_verdicts = read_csv(args.person_verdicts), read_csv(args.marker_verdicts)
    validate_verdicts(frames, markers, people, marker_verdicts)
    matched = sum(row["verdict"] == "MATCHED" for row in people)
    unmatched_markers = sum(row["verdict"] == "UNMATCHED" for row in marker_verdicts)
    output = {
        "sealed_visible_player_slots": len(people), "judgeable_frames": len(frames),
        "g270_on_court_marker_observations": len(markers), "matched_visible_players": matched,
        "unmatched_visible_players": len(people) - matched,
        "recall_wilson_95": wilson(matched, len(people)),
        "near_boundary_player_verdicts": sum(row["near_boundary"] == "YES" for row in people),
        "unmatched_markers": unmatched_markers,
        "unmatched_marker_rate": unmatched_markers / len(markers),
        "unmatched_marker_wilson_95": wilson(unmatched_markers, len(markers)),
    }
    args.summary_output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print("Wrote per-person recall summary")


def materialize(args: argparse.Namespace) -> None:
    """Expand the reviewed manual assignments into exhaustive verdict tables."""
    frames, markers = read_counted_frames(args.per_frame_join), read_csv(args.marker_manifest)
    assignments = json.loads(args.assignments.read_text(encoding="ascii"))
    primary = {(row["blind_id"], row["player_slot"]): row for row in assignments["person_matches"]}
    marker_links = {(row["blind_id"], row["marker_index"]): row["player_slot"] for row in assignments["marker_matches"]}
    people = []
    for frame in frames:
        blind_id, source_frame = int(frame["blind_id"]), int(frame["source_frame"])
        for slot in range(1, int(frame["players_visible_on_court"]) + 1):
            match = primary.get((blind_id, slot))
            people.append({"blind_id": blind_id, "source_frame": source_frame, "player_slot": slot,
                           "verdict": "MATCHED" if match else "UNMATCHED",
                           "marker_index": "" if match is None else match["primary_marker_index"],
                           "near_boundary": "NO" if match is None else match["near_boundary"]})
    marker_verdicts = []
    for marker in markers:
        key = (int(marker["blind_id"]), int(marker["marker_index"]))
        slot = marker_links.get(key)
        marker_verdicts.append({"blind_id": key[0], "source_frame": int(marker["source_frame"]),
                                "marker_index": key[1], "verdict": "MATCHED" if slot else "UNMATCHED",
                                "player_slot": "" if slot is None else slot})
    validate_verdicts(frames, markers, people, marker_verdicts)
    for rows, fields, path in (
        (people, ["blind_id", "source_frame", "player_slot", "verdict", "marker_index", "near_boundary"], args.person_output),
        (marker_verdicts, ["blind_id", "source_frame", "marker_index", "verdict", "player_slot"], args.marker_output),
    ):
        with path.open("w", newline="", encoding="ascii") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    print("Wrote exhaustive manual per-person and per-marker verdict tables")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True)
    render_parser = commands.add_parser("render")
    render_parser.add_argument("--per-frame-join", type=Path, required=True)
    render_parser.add_argument("--g267", type=Path, required=True)
    render_parser.add_argument("--frames-dir", type=Path, required=True)
    render_parser.add_argument("--render-dir", type=Path, required=True)
    render_parser.add_argument("--marker-manifest", type=Path, required=True)
    render_parser.set_defaults(func=render)
    summary_parser = commands.add_parser("summarize")
    summary_parser.add_argument("--per-frame-join", type=Path, required=True)
    summary_parser.add_argument("--marker-manifest", type=Path, required=True)
    summary_parser.add_argument("--person-verdicts", type=Path, required=True)
    summary_parser.add_argument("--marker-verdicts", type=Path, required=True)
    summary_parser.add_argument("--summary-output", type=Path, required=True)
    summary_parser.set_defaults(func=summarize)
    materialize_parser = commands.add_parser("materialize")
    materialize_parser.add_argument("--per-frame-join", type=Path, required=True)
    materialize_parser.add_argument("--marker-manifest", type=Path, required=True)
    materialize_parser.add_argument("--assignments", type=Path, required=True)
    materialize_parser.add_argument("--person-output", type=Path, required=True)
    materialize_parser.add_argument("--marker-output", type=Path, required=True)
    materialize_parser.set_defaults(func=materialize)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
