"""G378 reference join, per-class scoring, the orbit-choice diagnostic and the verdict.

The join, the adjudication rule, the Wilson interval and Cohen kappa are IMPORTED from the landed
G367 cue module and are not copied. The orbit diagnostic reads the landed G371 artifacts read only
and writes nothing back: G371's refusal, statuses and margin semantics are untouched.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking.g367_cues import _kappa, _ratings, _reference, _wilson
from scripts.platformkit.tracking.g367_symmetry import GROUP, compose
from scripts.platformkit.tracking.g334_court_template import project
from scripts.platformkit.tracking.g378_sheets import _rows

P_ANCHOR = np.array([[0.0, 0.0]], dtype=float)
GEOMETRIES = ("G1_SYNTH_QUAD", "G2_WIDE", "G3_TIGHT", "G4_OFF_AXIS")
CLASSES = ("left", "right")
FRAME_BAR, SECTION_BAR, GAME_BAR, CLASS_BAR, WILSON_BAR = 120, 20, 8, 30, 0.90
SCORED_COLUMNS = ("frame_key,section,game,cache,call,reference,terra,sol,adjudicator,"
                  "left_mass,right_mass,outcome").split(",")
ORBIT_COLUMNS = ("geometry,element,probe_x,probe_half,cue_call,retained,n_retained,"
                 "unique_after_cue,g371_n_classes,g371_geometry_status,"
                 "would_pick_where_g371_refused").split(",")
UNKNOWN_COLUMNS = ("frame_key,section,game,call,reference,unknown_reason,kind").split(",")


def _outcome(callv: str, reference: str) -> str:
    if reference not in CLASSES:
        return "reference_" + (reference or "missing")
    if callv == "UNKNOWN":
        return "cue_unknown"
    return "correct" if callv.lower() == reference else "wrong"


def build(ratings: Path, cue_csv: Path, frames: Path, scored_out: Path, reference_out: Path,
          unknowns_out: Path) -> tuple:
    """Reference by agreement then blind adjudication; every frame stays in the denominator."""
    labels = _ratings(ratings)
    cache = {row["frame_key"]: row for row in _rows(frames)}
    rows = []
    for item in sorted(_rows(cue_csv), key=lambda row: row["frame_key"]):
        key = item["frame_key"]
        per_rater = labels.get(key, {})
        reference = _reference(per_rater)
        rows.append({"frame_key": key, "section": item["section"], "game": item["game"],
                     "cache": cache[key]["cache"], "call": item["call"],
                     "reference": reference, "terra": per_rater.get("terra", ""),
                     "sol": per_rater.get("sol", ""),
                     "adjudicator": per_rater.get("ADJUDICATOR", ""),
                     "left_mass": item["left_mass"], "right_mass": item["right_mass"],
                     "outcome": _outcome(item["call"], reference),
                     "unknown_reason": item["unknown_reason"]})
    scored_out.parent.mkdir(parents=True, exist_ok=True)
    with scored_out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=SCORED_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    with reference_out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.writer(handle)
        writer.writerow(("frame_key", "terra", "sol", "adjudicator", "reference"))
        for row in rows:
            writer.writerow((row["frame_key"], row["terra"], row["sol"], row["adjudicator"],
                             row["reference"] or "UNADJUDICATED"))
    unresolved = [row for row in rows if row["outcome"] != "correct" and row["outcome"] != "wrong"]
    with unknowns_out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=UNKNOWN_COLUMNS)
        writer.writeheader()
        for row in unresolved:
            writer.writerow({"frame_key": row["frame_key"], "section": row["section"],
                             "game": row["game"], "call": row["call"],
                             "reference": row["reference"] or "UNADJUDICATED",
                             "unknown_reason": row["unknown_reason"], "kind": row["outcome"]})
    return rows, labels


def orbit(g371_dir: Path, out: Path) -> list:
    """Which sealed group elements a LEFT or a RIGHT call would retain. Diagnostic only."""
    matrices = json.loads((g371_dir / "matrices_clean.json").read_text(encoding="utf-8"))
    fixtures = json.loads((g371_dir / "fixtures.json").read_text(encoding="utf-8"))
    height, width = fixtures["shape"]
    with (g371_dir / "selected.csv").open(newline="", encoding="utf-8") as handle:
        landed = {row["geometry"]: row for row in csv.DictReader(handle)
                  if row["geometry"] in GEOMETRIES}
    rows = []
    for geometry in GEOMETRIES:
        winner = np.asarray(matrices["%s|0.00|000" % geometry]["winner"], dtype=float)
        halves = {}
        for element in GROUP:
            try:
                point = project(compose(winner, element), P_ANCHOR)[0]
            except Exception:
                halves[element.name] = ("", "OFF_FRAME")
                continue
            if not np.isfinite(point).all():
                halves[element.name] = ("", "OFF_FRAME")
                continue
            halves[element.name] = (round(float(point[0]), 4),
                                    "LEFT" if float(point[0]) < width / 2.0 else "RIGHT")
        cell = landed.get(geometry, {})
        n_classes = int(cell.get("n_classes", "1") or 1)
        for call_value in ("LEFT", "RIGHT"):
            retained = [name for name, (_x, half) in halves.items() if half == call_value]
            unique = len(retained) == 1
            for element in GROUP:
                probe_x, half = halves[element.name]
                rows.append({"geometry": geometry, "element": element.name, "probe_x": probe_x,
                             "probe_half": half, "cue_call": call_value,
                             "retained": "|".join(retained), "n_retained": len(retained),
                             "unique_after_cue": int(unique), "g371_n_classes": n_classes,
                             "g371_geometry_status": cell.get("geometry_status", ""),
                             "would_pick_where_g371_refused": int(unique and n_classes > 1)})
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=ORBIT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    picks = sum(row["would_pick_where_g371_refused"] for row in rows)
    print("ORBIT geometries=%d rows=%d would_pick_where_g371_refused=%d" % (len(GEOMETRIES), len(rows), picks))
    return rows


def verdict(summary: dict) -> str:
    """DONE only when every bar of the sealed ACCEPTANCE RULE is met; never a lowered bar."""
    short = []
    coverage = summary["coverage"]
    if coverage["n_frames"] < FRAME_BAR or coverage["n_sections"] < SECTION_BAR \
            or coverage["n_games"] < GAME_BAR:
        short.append("coverage")
    for name in CLASSES:
        stat = summary["classes"][name]
        if stat["resolved"] < CLASS_BAR:
            short.append("class_%s_quota" % name)
        elif stat["wilson_lower"] is None or stat["wilson_lower"] < WILSON_BAR:
            short.append("class_%s_wilson" % name)
    for name in ("mirror", "masked"):
        if not summary["controls"][name]["meets"]:
            short.append("control_" + name)
    summary["bars_short"] = short
    return "DONE" if not short else "PARTIAL: " + ", ".join(short)


def score(ratings: Path, cue_csv: Path, frames: Path, manifest: Path, g371_dir: Path,
          evidence: Path, summary_path: Path) -> int:
    rows, labels = build(ratings, cue_csv, frames, evidence / "scored.csv",
                         evidence / "reference.csv", evidence / "unknowns.csv")
    orbit(g371_dir, evidence / "orbit_choices.csv")
    payload = json.loads(summary_path.read_text(encoding="ascii")) if summary_path.exists() else {"row": "G378"}
    manifest_payload = json.loads(manifest.read_text(encoding="ascii"))
    classes = {}
    for name in CLASSES:
        subset = [row for row in rows if row["reference"] == name]
        resolved = [row for row in subset if row["call"] != "UNKNOWN"]
        correct = sum(row["outcome"] == "correct" for row in resolved)
        low, high = _wilson(correct, len(resolved))
        classes[name] = {"reference_frames": len(subset), "resolved": len(resolved),
                         "correct": correct,
                         "correct_share": round(correct / len(resolved), 6) if resolved else None,
                         "wilson_lower": None if low is None else round(low, 6),
                         "wilson_upper": None if high is None else round(high, 6)}
    payload["coverage"] = {"n_frames": len(rows), "n_unique_frames": len({r["frame_key"] for r in rows}),
                           "n_sections": len({r["section"] for r in rows}),
                           "n_games": len({r["game"] for r in rows}),
                           "development_games": manifest_payload["development_games"]}
    payload["reference_counts"] = {name: sum(row["reference"] == name for row in rows)
                                   for name in ("left", "right", "unknown")}
    payload["reference_counts"]["unadjudicated"] = sum(not row["reference"] for row in rows)
    payload["classes"] = classes
    payload["kappa"] = _kappa(labels)
    payload["outcomes"] = {name: sum(row["outcome"] == name for row in rows)
                           for name in sorted({row["outcome"] for row in rows})}
    payload["verdict"] = verdict(payload)
    summary_path.write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("SCORE verdict=%s left=%s right=%s kappa=%s"
          % (payload["verdict"], classes["left"], classes["right"], payload["kappa"]))
    return 0


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("ratings", "cue", "frames", "manifest", "g371-dir", "evidence", "summary"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv[1:])
    return score(Path(args.ratings), Path(args.cue), Path(args.frames), Path(args.manifest),
                 Path(args.g371_dir), Path(args.evidence), Path(args.summary))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
