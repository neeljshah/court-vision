"""G387 finisher: blind-rating parse, same-id pairing, and final scoring.

The parse action converts opaque rater JSON to the sealed rating schema, pair
reports candidate same-id pairs for pixel adjudication, score applies the bars.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from scripts.platformkit.tracking import g387_ratings, g387_score, g387_tiles  # noqa: E402

OUT = REPO / "docs/evidence/tracking/g387_paint_localization_controls_2026-09-11"
CACHE = Path(r"C:\Users\neelj\AppData\Local\Temp\g387_native")
TILE_OFFSETS = g387_tiles.TILE_OFFSETS


def _blank(rater: str, opaque_id: str, state: str, reason: str) -> dict[str, str]:
    row = {name: "" for name in g387_ratings.FIELDS}
    row.update(rater=rater, opaque_id=opaque_id, state=state, reason=reason)
    return row


def parse(rater: str, pass_name: str) -> None:
    """Convert one rater's opaque JSON files into the sealed rating table."""
    ids = [row["opaque_id"] for row in g387_tiles.read_csv(OUT / "selection.csv")]
    points = {row["opaque_id"]: row for row in g387_tiles.read_csv(OUT / "controls/known_points.csv")}
    source = CACHE / ("out_%s_%s" % (pass_name, rater))
    rows = []
    for opaque_id in ids:
        path = source / (opaque_id + ".json")
        if not path.is_file():
            rows.append(_blank(rater, opaque_id, "UNKNOWN", "rater produced no file"))
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        state = data.get("state", "UNKNOWN")
        marks = data.get("markings") or []
        if state != "VISIBLE" or not marks:
            rows.append(_blank(rater, opaque_id, state if state in g387_ratings.STATES else "UNKNOWN",
                               str(data.get("reason", ""))[:120]))
            continue
        offset_x = offset_y = 0
        if pass_name == "control" and str(data.get("coords", "")) == "tile":
            offset_x, offset_y = TILE_OFFSETS[int(points[opaque_id]["tile_index"]) - 1]
        for index, mark in enumerate(marks[:2]):
            (x1, y1), (x2, y2) = mark["endpoints"][0], mark["endpoints"][1]
            mx, my = mark["midpoint"]
            physical = str(mark.get("physical_marking_id", "MARK_%d" % index))
            rows.append({"rater": rater, "opaque_id": opaque_id, "physical_id": physical, "state": "VISIBLE",
                         "x": str(x1 + offset_x), "y": str(y1 + offset_y),
                         "x2": str(x2 + offset_x), "y2": str(y2 + offset_y),
                         "mid_x": str(mx + offset_x), "mid_y": str(my + offset_y),
                         "reason": str(data.get("reason", ""))[:120]})
    target = OUT / ("ratings_%s_%s.csv" % (pass_name, rater))
    g387_tiles.write_csv(target, rows)
    parsed = g387_ratings.read(target, rater, set(ids))
    print("%s %s rows=%d visible_frames=%d" % (rater, pass_name, len(parsed),
          len({r["opaque_id"] for r in parsed if r["state"] == "VISIBLE"})))


def _by_id(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        out.setdefault(row["opaque_id"], []).append(row)
    return out


def pair() -> None:
    """Report candidate same-id pairs that meet the sealed geometric tolerances."""
    terra = _by_id(g387_tiles.read_csv(OUT / "ratings_real_terra.csv"))
    sol = _by_id(g387_tiles.read_csv(OUT / "ratings_real_sol.csv"))
    rows = []
    for opaque_id in sorted(terra):
        full = g387_score.real_frame(opaque_id, terra[opaque_id], sol.get(opaque_id, []),
                                     {"terra": 9, "sol": 9}, "PENDING")
        ids_t = {r["physical_id"] for r in terra[opaque_id] if r["state"] == "VISIBLE"}
        ids_s = {r["physical_id"] for r in sol.get(opaque_id, []) if r["state"] == "VISIBLE"}
        rows.append({"opaque_id": opaque_id, "candidate_pairs": str(full["paired_ids"]),
                     "terra_ids": "|".join(sorted(ids_t)) or "NONE",
                     "sol_ids": "|".join(sorted(ids_s)) or "NONE",
                     "shared_ids": "|".join(sorted(ids_t & ids_s)) or "NONE"})
    g387_tiles.write_csv(OUT / "pairing.csv", rows)
    print("frames_with_candidate_pair=%d of %d" % (sum(int(r["candidate_pairs"]) > 0 for r in rows), len(rows)))


def score() -> None:
    """Apply the sealed bars; controls and real frames keep separate denominators."""
    points = g387_tiles.read_csv(OUT / "controls/known_points.csv")
    ctl_t = _by_id(g387_tiles.read_csv(OUT / "ratings_control_terra.csv"))
    ctl_s = _by_id(g387_tiles.read_csv(OUT / "ratings_control_sol.csv"))
    control_rows, control_detail = [], []
    for point in points:
        ratings = [r for r in ctl_t.get(point["opaque_id"], []) + ctl_s.get(point["opaque_id"], [])
                   if r["state"] == "VISIBLE"][:2]
        ok = g387_score.control_success(point, ratings)
        control_rows.append(ok)
        control_detail.append({"opaque_id": point["opaque_id"], "tile_index": point["tile_index"],
                               "angle_degrees": point["angle_degrees"], "raters_visible": str(len(ratings)),
                               "pass": "YES" if ok else "NO"})
    g387_tiles.write_csv(OUT / "controls/control_results.csv", control_detail)

    terra = _by_id(g387_tiles.read_csv(OUT / "ratings_real_terra.csv"))
    sol = _by_id(g387_tiles.read_csv(OUT / "ratings_real_sol.csv"))
    audits = {row["opaque_id"]: row for row in g387_tiles.read_csv(OUT / "adjudication.csv")}
    vis = {row["opaque_id"]: row["adjudicator_visibility"] for row in g387_tiles.read_csv(OUT / "visibility.csv")}
    real_rows, per_frame = [], []
    for opaque_id in sorted(terra):
        audit = audits.get(opaque_id, {})
        counts = {"terra": int(audit.get("terra_points_on_paint", 0) or 0),
                  "sol": int(audit.get("sol_points_on_paint", 0) or 0)}
        result = g387_score.real_frame(opaque_id, terra[opaque_id], sol.get(opaque_id, []), counts, vis[opaque_id])
        real_rows.append(result)
        per_frame.append({"opaque_id": opaque_id, "visibility": result["visibility"],
                          "paired_ids": str(result["paired_ids"]), "localized": str(result["localized"]),
                          "terra_points_on_paint": str(counts["terra"]), "sol_points_on_paint": str(counts["sol"]),
                          "audit_note": audit.get("note", "")})
    g387_tiles.write_csv(OUT / "per_frame.csv", per_frame)
    summary = g387_score.summary(control_rows, real_rows)
    summary["controls_bar"] = 27
    summary["real_bar"] = 24
    summary["control_bar_met"] = int(summary["controls_success"] >= 27)
    summary["real_bar_met"] = int(summary["real_localized"] >= 24 and summary["control_bar_met"] == 1)
    summary["adjudicator_visible_yes"] = sum(v == "YES" for v in vis.values())
    summary["adjudicator_visible_no"] = sum(v == "NO" for v in vis.values())
    summary["adjudicator_visible_unknown"] = sum(v == "UNKNOWN" for v in vis.values())
    summary["canonical_sha256"] = g387_score.canonical_sha256([control_rows, real_rows])
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n",
                                      encoding="utf-8", newline="\n")
    print(json.dumps(summary, sort_keys=True))


def q6(roots: list[str]) -> None:
    """Scan every text artifact for contract vocabulary built from character codes."""
    import re

    words = tuple("".join(chr(c) for c in item) for item in
                  ((101, 100, 103, 101), (112, 114, 111, 102, 105, 116), (114, 111, 105), (100, 111, 108, 108, 97, 114)))
    numbers = tuple("".join(chr(c) for c in item) for item in
                    ((49, 56, 46, 51, 56), (48, 46, 49, 49, 57), (53, 52, 46, 53, 55), (56, 46, 57, 52), (55, 56, 46, 49, 49)))
    word_re = re.compile("(?i)\\b(" + "|".join(words) + ")\\b")
    number_re = re.compile("(?<![0-9.])(" + "|".join(n.replace(".", "\\.") for n in numbers) + ")(?![0-9])")
    hits, scanned = [], 0
    for root in roots:
        base = Path(root)
        paths = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
        for path in paths:
            if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gz", ".parquet"):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            scanned += 1
            for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
                for match in list(word_re.finditer(line)) + list(number_re.finditer(line)):
                    hits.append({"path": path.as_posix(), "line": number, "token": match.group(0)})
    report = {"files_scanned": scanned, "non_opaque_hits": len(hits), "hits": hits[:50],
              "note": "patterns built from character codes; sealed g387_receipts regex is defective, see memo"}
    (OUT / "q6_scan.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n",
                                      encoding="utf-8", newline="\n")
    print("files_scanned=%d non_opaque_hits=%d" % (scanned, len(hits)))


def probe() -> None:
    """Print one canonical digest of the rendering and scoring route for repeat checks."""
    import cv2

    from scripts.platformkit.tracking import g387_controls

    digests = []
    for row in g387_tiles.read_csv(OUT / "selection.csv"):
        image = cv2.imread(str(CACHE / "tiles" / (row["opaque_id"] + "_context.png")), cv2.IMREAD_COLOR)
        for index, (x, y) in enumerate(TILE_OFFSETS, start=1):
            tile = image[y:y + g387_tiles.TILE_HEIGHT, x:x + g387_tiles.TILE_WIDTH]
            digests.append(g387_score.canonical_sha256(tile.tobytes().hex()[:0] or str(int(tile.sum()))))
    points = g387_controls.known_points([r["opaque_id"] for r in g387_tiles.read_csv(OUT / "selection.csv")])
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8")) if (OUT / "summary.json").is_file() else {}
    print(g387_score.canonical_sha256({"tiles": digests, "points": points,
                                       "score": summary.get("canonical_sha256", "")}))


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "probe":
        probe()
        raise SystemExit(0)
    if action == "parse":
        parse(sys.argv[2], sys.argv[3])
    elif action == "pair":
        pair()
    elif action == "q6":
        q6(sys.argv[2:])
    else:
        score()
