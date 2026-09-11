"""Blind-answer ingestion, frozen pairing and recovery accounting for G399."""
from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

from scripts.platformkit.tracking import g399_protocol as protocol
from scripts.platformkit.tracking.g399_measure import OFFSETS

STATES = ("VISIBLE", "ABSENT", "UNKNOWN")


def to_native(tile: int, point: list[float]) -> protocol.Point:
    """Convert one tile-local rater point to the native 1920x1080 frame."""
    offset_x, offset_y = OFFSETS[tile - 1]
    return (float(point[0]) + offset_x, float(point[1]) + offset_y)


def load_rater(out_dir: Path, rater: str, context_ids: list[str]) -> dict[str, dict]:
    """Read one rater's immutable answers; a missing file stays a named failure."""
    answers = {}
    for context_id in context_ids:
        path = out_dir / ("%s.json" % context_id)
        if not path.is_file():
            answers[context_id] = {"state": "NO_ANSWER", "fragments": [], "reason": "",
                                   "raw_path": ""}
            continue
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        state = str(data.get("state", "")).upper()
        fragments = []
        for index, item in enumerate(data.get("fragments") or [], start=1):
            points = item.get("points") or {}
            if not all(key in points for key in ("p1", "p2", "p3")):
                continue
            tile = int(item.get("tile", 0))
            if not 1 <= tile <= 6:
                continue
            fragments.append(protocol.Fragment(
                rater=rater, tile=tile, family=str(item.get("family", "UNKNOWN")).upper(),
                first=to_native(tile, points["p1"]), second=to_native(tile, points["p2"]),
                third=to_native(tile, points["p3"]),
                fragment_id="%s_%s_f%d" % (context_id, rater, index)))
        answers[context_id] = {"state": state if state in STATES else "NO_ANSWER",
                               "fragments": fragments, "reason": str(data.get("reason", ""))[:160],
                               "raw_path": path.as_posix()}
    return answers


def symmetric_line_px(left: protocol.Fragment, right: protocol.Fragment) -> float:
    """Largest of the six cross perpendicular distances; the 6 px rule binds it."""
    values = [protocol._projection(point, right.first, right.second)[1]
              for point in (left.first, left.second, left.third)]
    values += [protocol._projection(point, left.first, left.second)[1]
               for point in (right.first, right.second, right.third)]
    return max(values)


def freeze_pairs(context_id: str, left: list[protocol.Fragment],
                 right: list[protocol.Fragment]) -> tuple[list[dict], list[protocol.Fragment]]:
    """Pair by smallest symmetric line distance with stable deterministic ties."""
    candidates = []
    for one, two in product(left, right):
        if not protocol.pair_compatible(one, two):
            continue
        candidates.append((symmetric_line_px(one, two), one.fragment_id, two.fragment_id, one, two))
    candidates.sort(key=lambda item: (round(item[0], 6), item[1], item[2]))
    used: set[str] = set()
    pairs = []
    for distance, left_id, right_id, one, two in candidates:
        if left_id in used or right_id in used:
            continue
        used.update((left_id, right_id))
        pairs.append({"pair_id": "%s_pair%d" % (context_id, len(pairs) + 1),
                      "context_id": context_id, "tile": one.tile, "family": one.family,
                      "symmetric_line_px": round(distance, 3),
                      "astra_fragment": left_id, "sol_fragment": right_id,
                      "astra_span_px": round(protocol.math.dist(one.first, one.second), 1),
                      "sol_span_px": round(protocol.math.dist(two.first, two.second), 1),
                      "passes_sealed_6px_rule": "YES"})
    unmatched = [fragment for fragment in left + right if fragment.fragment_id not in used]
    return pairs, unmatched


def audit_points(fragment: protocol.Fragment) -> list[protocol.Point]:
    """Nine evenly spaced native points along one fragment, for the pixel audit."""
    return [(fragment.first[0] + index * (fragment.second[0] - fragment.first[0]) / 8.0,
             fragment.first[1] + index * (fragment.second[1] - fragment.first[1]) / 8.0)
            for index in range(protocol.AUDIT_POINTS)]


def recovery(pairs: list[dict], audits: dict[str, dict]) -> dict[str, object]:
    """Count a state once when at least one pair passes both fragment audits."""
    recovered = set()
    passed_pairs = []
    for pair in pairs:
        verdict = audits.get(pair["pair_id"])
        if not verdict:
            continue
        if verdict["same_band"] == "YES" and verdict["astra_points"] >= protocol.AUDIT_REQUIRED \
                and verdict["sol_points"] >= protocol.AUDIT_REQUIRED:
            recovered.add(pair["context_id"])
            passed_pairs.append(pair["pair_id"])
    return {"recovered_states": sorted(recovered), "passed_pairs": sorted(passed_pairs)}


def score(states: list[dict], answers: dict[str, dict[str, dict]], audits: dict[str, dict]) -> dict:
    """Produce the full descriptive accounting from immutable inputs only."""
    per_frame, all_pairs, unmatched = [], [], []
    for state in states:
        context_id = state["context_id"]
        astra = answers["astra"].get(context_id, {"state": "NO_IMAGE", "fragments": []})
        sol = answers["sol"].get(context_id, {"state": "NO_IMAGE", "fragments": []})
        pairs, loose = freeze_pairs(context_id, astra["fragments"], sol["fragments"])
        all_pairs.extend(pairs)
        unmatched.extend({"context_id": context_id, "fragment_id": f.fragment_id, "rater": f.rater,
                          "tile": f.tile, "family": f.family} for f in loose)
        families = {f.family for f in astra["fragments"]} , {f.family for f in sol["fragments"]}
        per_frame.append({
            "context_id": context_id, "object_name": state["object_name"],
            "competition": state["competition"], "ytid": state["ytid"], "section": state["section"],
            "export_status": state["export_status"], "claude_visibility": state.get("visibility", ""),
            "astra_state": astra["state"], "sol_state": sol["state"],
            "astra_fragments": len(astra["fragments"]), "sol_fragments": len(sol["fragments"]),
            "candidate_pairs": len(pairs),
            "family_disagreement": "YES" if families[0] and families[1] and families[0] != families[1] else "NO"})
    result = recovery(all_pairs, audits)
    decoded = [row for row in per_frame if row["export_status"] == "EXPORTED"]
    visible = [row for row in decoded if row["claude_visibility"] == "YES"]
    recovered = set(result["recovered_states"])
    return {"per_frame": per_frame, "pairs": all_pairs, "unmatched": unmatched,
            "recovered_states": result["recovered_states"], "passed_pairs": result["passed_pairs"],
            "planned": len(per_frame), "decoded": len(decoded), "visible": len(visible),
            "recovered": len(recovered),
            "recovered_of_decoded": sum(row["context_id"] in recovered for row in decoded),
            "recovered_of_visible": sum(row["context_id"] in recovered for row in visible),
            "candidate_pairs": len(all_pairs), "unmatched_fragments": len(unmatched),
            "family_disagreement": sum(row["family_disagreement"] == "YES" for row in per_frame)}


def render_pair_card(frame_path: Path, pair: dict, fragments: dict, out_path: Path) -> dict:
    """Draw the nine audit points of both fragments on a 2x native zoom card."""
    import cv2
    import numpy as np

    frame = cv2.imdecode(np.fromfile(str(frame_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    left, right = fragments[pair["astra_fragment"]], fragments[pair["sol_fragment"]]
    points = audit_points(left) + audit_points(right)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0 = max(0, int(min(xs)) - 40)
    y0 = max(0, int(min(ys)) - 40)
    x1 = min(1920, int(max(xs)) + 40)
    y1 = min(1080, int(max(ys)) + 40)
    crop = frame[y0:y1, x0:x1]
    scale = 2
    card = cv2.resize(crop, (crop.shape[1] * scale, crop.shape[0] * scale),
                      interpolation=cv2.INTER_NEAREST)
    for fragment, color in ((left, (0, 255, 255)), (right, (255, 0, 255))):
        for index, point in enumerate(audit_points(fragment)):
            centre = (int(round((point[0] - x0) * scale)), int(round((point[1] - y0) * scale)))
            cv2.circle(card, centre, 6, color, 1)
            cv2.putText(card, str(index + 1), (centre[0] + 7, centre[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".jpg", card, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(str(out_path))
    return {"pair_id": pair["pair_id"], "card": out_path.as_posix(),
            "crop": [x0, y0, x1, y1], "zoom": scale}


def render_point_grid(frame_path: Path, fragment: protocol.Fragment, out_path: Path,
                      half: int = 24, zoom: int = 8) -> dict:
    """Render the nine audit points as native zoom cells so 3 px is judgeable."""
    import cv2
    import numpy as np

    frame = cv2.imdecode(np.fromfile(str(frame_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    cell = half * 2 * zoom
    grid = np.zeros((cell * 3, cell * 3, 3), dtype=np.uint8)
    for index, point in enumerate(audit_points(fragment)):
        cx, cy = int(round(point[0])), int(round(point[1]))
        patch = np.zeros((half * 2, half * 2, 3), dtype=np.uint8)
        x0, y0 = max(0, cx - half), max(0, cy - half)
        x1, y1 = min(1920, cx + half), min(1080, cy + half)
        patch[y0 - (cy - half):y1 - (cy - half), x0 - (cx - half):x1 - (cx - half)] = frame[y0:y1, x0:x1]
        view = cv2.resize(patch, (cell, cell), interpolation=cv2.INTER_NEAREST)
        centre = half * zoom
        radius = int(protocol.POINT_TOLERANCE * zoom)
        cv2.circle(view, (centre, centre), radius, (0, 0, 255), 1)
        cv2.drawMarker(view, (centre, centre), (0, 0, 255), cv2.MARKER_CROSS, zoom * 2, 1)
        cv2.putText(view, str(index + 1), (6, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        row, column = divmod(index, 3)
        grid[row * cell:(row + 1) * cell, column * cell:(column + 1) * cell] = view
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(".jpg", grid, [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tofile(str(out_path))
    return {"fragment_id": fragment.fragment_id, "grid": out_path.as_posix(),
            "half_px": half, "zoom": zoom, "circle_px": protocol.POINT_TOLERANCE}


def main(argv: list[str]) -> int:
    if len(argv) != 6:
        print("usage: g399_score <states.json> <audits.json> <out_astra> <out_sol> <result.json>")
        return 2
    states = json.loads(Path(argv[1]).read_text(encoding="ascii"))
    audits = json.loads(Path(argv[2]).read_text(encoding="ascii")) if Path(argv[2]).is_file() else {}
    ids = [state["context_id"] for state in states]
    answers = {"astra": load_rater(Path(argv[3]), "astra", ids),
               "sol": load_rater(Path(argv[4]), "sol", ids)}
    result = score(states, answers, audits)
    result["raw_paths"] = {rater: {cid: answers[rater][cid]["raw_path"] for cid in ids}
                           for rater in ("astra", "sol")}
    result["reasons"] = {rater: {cid: answers[rater][cid]["reason"] for cid in ids}
                         for rater in ("astra", "sol")}
    Path(argv[5]).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n",
                             encoding="ascii", newline="\n")
    print("SCORE planned=%d decoded=%d visible=%d pairs=%d recovered=%d"
          % (result["planned"], result["decoded"], result["visible"],
             result["candidate_pairs"], result["recovered"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
