"""G388 scoring: control qualification, real pairing, and pair-specific audit rows.

Reads sealed rater responses only. It never renders, never re-dispatches, and never
substitutes a missing response with anything but a recorded failure.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from scripts.platformkit.tracking import g387_tiles as tiles
from scripts.platformkit.tracking import g388_protocol as protocol

RATERS = ("terra", "sol")


def _point(raw) -> protocol.Point | None:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    try:
        return float(raw[0]), float(raw[1])
    except (TypeError, ValueError):
        return None


def read_control_response(path: Path, tile_index: int) -> tuple[protocol.Point, ...] | None:
    """Return one rater's three native control points, or None for any fault."""
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    if str(payload.get("state", "")).upper() != "VISIBLE":
        return None
    points = payload.get("points") or {}
    ordered = [_point(points.get(key)) for key in ("p1", "p2", "p3")]
    if any(value is None for value in ordered):
        return None
    offset = tiles.TILE_OFFSETS[tile_index - 1]
    return tuple(protocol.tile_to_native(value, offset) for value in ordered)


def score_controls(known: Path, out_dirs: dict[str, Path]) -> tuple[list[dict[str, str]], dict[str, object]]:
    """Apply the sealed two-rater 3 px band-membership bar to all 30 controls."""
    rows, table = tiles.read_csv(known), []
    payload = []
    for row in rows:
        tile_index = int(row["tile_index"])
        truth = protocol.Band((float(row["x1"]), float(row["y1"])), (float(row["x2"]), float(row["y2"])))
        record = {"control_id": row["control_id"], "tile_index": row["tile_index"],
                  "angle_degrees": row["angle_degrees"]}
        answers = {}
        for rater in RATERS:
            answers[rater] = read_control_response(
                out_dirs[rater] / (row["control_id"] + ".json"), tile_index)
            record[rater + "_state"] = "ANSWERED" if answers[rater] else "FAULT_OR_UNKNOWN"
            record[rater + "_pass"] = "YES" if protocol.control_passes(truth, answers[rater]) else "NO"
            record[rater + "_max_perp_px"] = ""
            if answers[rater]:
                deviations = [protocol._projection(point, truth)[1] for point in answers[rater]]
                record[rater + "_max_perp_px"] = "%.2f" % max(deviations)
                record[rater + "_span_px"] = "%.1f" % math.dist(answers[rater][0], answers[rater][1])
            record.setdefault(rater + "_span_px", "")
        record["pass"] = "YES" if all(record[r + "_pass"] == "YES" for r in RATERS) else "NO"
        table.append(record)
        payload.append({"context_key": row["control_id"], "truth": truth,
                        "rater_a": answers["terra"], "rater_b": answers["sol"]})
    return table, protocol.controls_qualify(payload)


def read_real_response(path: Path) -> tuple[str, list[protocol.Fragment]]:
    """Return one context's declared state and its validly shaped fragments."""
    if not path.is_file():
        return "MISSING", []
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return "MALFORMED", []
    state = str(payload.get("state", "UNKNOWN")).upper()
    fragments = []
    for order, raw in enumerate(payload.get("fragments") or [], start=1):
        tile_index = raw.get("tile")
        points = raw.get("points") or {}
        ordered = [_point(points.get(key)) for key in ("p1", "p2", "p3")]
        if not isinstance(tile_index, int) or not 1 <= tile_index <= 6 or any(v is None for v in ordered):
            continue
        offset = tiles.TILE_OFFSETS[tile_index - 1]
        native = [protocol.tile_to_native(value, offset) for value in ordered]
        fragments.append(protocol.Fragment(tile_index, str(raw.get("family", "UNKNOWN")).upper(),
                                           native[0], native[1], native[2], "f%d" % order))
    return state, fragments[:2]


def pair_contexts(context_ids: list[str], out_dirs: dict[str, Path]) -> list[dict[str, object]]:
    """Pair both raters' fragments once per context under the sealed rules."""
    results = []
    for context in context_ids:
        state_a, left = read_real_response(out_dirs["terra"] / (context + ".json"))
        state_b, right = read_real_response(out_dirs["sol"] / (context + ".json"))
        pairs = protocol.pair_fragments(left, right) if left and right else []
        families = {fragment.family for fragment in left} ^ {fragment.family for fragment in right}
        results.append({"context_id": context, "terra_state": state_a, "sol_state": state_b,
                        "terra_fragments": left, "sol_fragments": right, "pairs": pairs,
                        "family_disagreement": bool(families)})
    return results


def real_tables(results: list[dict[str, object]], visibility: dict[str, str]
                ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return the pair table and the per-context accounting over all 30 contexts."""
    pairs, frames = [], []
    for record in results:
        context = str(record["context_id"])
        for order, (left, right) in enumerate(record["pairs"], start=1):
            pairs.append({"context_id": context, "pair_id": "%s_pair%d" % (context, order),
                          "tile": str(left.tile), "family": left.family,
                          "symmetric_line_px": "%.2f" % protocol.symmetric_line_distance(left, right),
                          "terra_span_px": "%.1f" % left.line().length(),
                          "sol_span_px": "%.1f" % right.line().length(),
                          "audited_same_band": "PENDING", "audit_note": ""})
        frames.append({"context_id": context, "claude_visibility": visibility.get(context, ""),
                       "terra_state": str(record["terra_state"]), "sol_state": str(record["sol_state"]),
                       "terra_fragments": str(len(record["terra_fragments"])),
                       "sol_fragments": str(len(record["sol_fragments"])),
                       "pairs": str(len(record["pairs"])),
                       "family_disagreement": "YES" if record["family_disagreement"] else "NO"})
    return pairs, frames


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    tiles.write_csv(path, rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--known", type=Path, required=True)
    parser.add_argument("--out-terra", type=Path, required=True)
    parser.add_argument("--out-sol", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    dirs = {"terra": args.out_terra, "sol": args.out_sol}
    table, verdict = score_controls(args.known, dirs)
    args.evidence.joinpath("controls").mkdir(parents=True, exist_ok=True)
    write_csv(args.evidence / "controls" / "control_results.csv", table)
    verdict.pop("per_context", None)
    args.evidence.joinpath("controls", "control_verdict.json").write_text(
        json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
