"""G389: seal the blind judgments, then reconcile them against the primary pair.

Order matters and is sealed: each adjudicator judges from the native sheet with no
access to any earlier annotation, and only afterwards are the two G373 primary
annotations revealed here. Reconciliation is DESCRIPTIVE -- it never rewrites a
primary rating and never manufactures agreement. Keys whose adjudication contradicts
a unanimous primary pair, and audit keys where the two adjudicators differ, are
emitted for a human-equivalent pixel resolution; UNKNOWN survives every stage.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

from scripts.platformkit.tracking.g363_ball_coverage import read_csv, write_csv

ADJ_FIELDS = ("frame_key", "rater", "label", "box_x", "box_y", "box_w", "box_h",
              "cx", "cy", "pass", "reason")
RECON_FIELDS = ("frame_key", "split", "why", "adjudicator", "adjudicator_label",
                "adjudicator_cx", "adjudicator_cy", "terra_label", "sol_label",
                "primary_state", "agreement", "conflict_class")
AUDIT_FIELDS = ("frame_key", "split", "terra_label", "sol_label", "terra_cx", "terra_cy",
                "sol_cx", "sol_cy", "labels_agree", "centre_distance_px", "resolution")
PRIMARY = ("terra", "sol")


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def centre(row: dict) -> tuple[float, float] | None:
    """Native centre of one rating, from cx/cy or from the box it carries."""
    x, y = _float(row.get("cx")), _float(row.get("cy"))
    if x is not None and y is not None:
        return x, y
    box = [_float(row.get(name)) for name in ("box_x", "box_y", "box_w", "box_h")]
    if None in box:
        return None
    return box[0] + box[2] / 2.0, box[1] + box[3] / 2.0


def distance(first: dict, second: dict) -> float | None:
    """Native-pixel centre separation of two ratings, or None when either is boxless."""
    a, b = centre(first), centre(second)
    return None if a is None or b is None else math.hypot(a[0] - b[0], a[1] - b[1])


def primaries(ratings: list[dict]) -> dict[str, dict[str, dict]]:
    """The two revealed primary annotations per frame, revealed only after judging."""
    out: dict[str, dict[str, dict]] = {}
    for row in ratings:
        if row["rater"] in PRIMARY:
            out.setdefault(row["frame_key"], {})[row["rater"]] = row
    return out


def resolve_audit(pair: dict[str, dict], diameter: float) -> tuple[str, str]:
    """Audit repeats: agreement is reported, never imposed; a gap escalates."""
    labels = [pair[name]["label"] for name in PRIMARY if name in pair]
    if len(labels) != 2 or labels[0] != labels[1]:
        return "", "AUDIT-LABEL-CONFLICT"
    if labels[0] != "VISIBLE":
        return labels[0], "AUDIT-AGREED"
    gap = distance(pair[PRIMARY[0]], pair[PRIMARY[1]])
    if gap is None or gap > diameter:
        return "", "AUDIT-CENTRE-CONFLICT"
    return labels[0], "AUDIT-AGREED"


def _mean_row(key: str, pair: dict[str, dict], label: str) -> dict:
    rows = [pair[name] for name in PRIMARY if name in pair]
    points = [centre(row) for row in rows if centre(row) is not None]
    sizes = [max(_float(row.get("box_w")) or 0.0, _float(row.get("box_h")) or 0.0)
             for row in rows]
    sizes = [size for size in sizes if size > 0]
    if label == "VISIBLE" and points:
        cx = sum(point[0] for point in points) / len(points)
        cy = sum(point[1] for point in points) / len(points)
        size = sum(sizes) / len(sizes) if sizes else ""
        width = height = size if size else ""
        box = {"box_x": round(cx - (size or 0) / 2.0, 2) if size else "",
               "box_y": round(cy - (size or 0) / 2.0, 2) if size else "",
               "box_w": round(width, 2) if width else "",
               "box_h": round(height, 2) if height else ""}
    else:
        cx = cy = ""
        box = {name: "" for name in ("box_x", "box_y", "box_w", "box_h")}
    return {"frame_key": key, "rater": "ADJUDICATOR", "label": label,
            "cx": round(cx, 2) if cx != "" else "", "cy": round(cy, 2) if cy != "" else "",
            "pass": "full_frame", "reason": "audit repeat agreed", **box}


def run(args) -> int:
    out = Path(args.out_dir)
    sweep = read_csv(out / "sweep_permutation.csv")
    judged: dict[str, dict[str, dict]] = {}
    for name, path in (("terra", args.terra), ("sol", args.sol)):
        for row in (read_csv(Path(path)) if Path(path).exists() else []):
            judged.setdefault(row["frame_key"], {})[name] = row
    revealed = primaries(read_csv(Path(args.ratings)))
    queue_reason = {row["frame_key"]: row["why"] for row in read_csv(Path(args.queue))}
    resolved = {row["frame_key"]: row for row in
                (read_csv(Path(args.resolved))
                 if args.resolved and Path(args.resolved).is_file() else [])}
    diameter = float(args.median_diameter)

    decisions: list[dict] = []
    recon: list[dict] = []
    audits: list[dict] = []
    conflicts: list[dict] = []
    for item in sweep:
        key, owner = item["frame_key"], item["allocation"]
        pair = judged.get(key, {})
        if not pair:
            continue
        is_audit = item["audit_duplicate"] == "1"
        if is_audit and len(pair) == 2:
            label, verdict = resolve_audit(pair, diameter)
            gap = distance(pair["terra"], pair["sol"])
            audits.append({"frame_key": key, "split": item["split"],
                           "terra_label": pair["terra"]["label"],
                           "sol_label": pair["sol"]["label"],
                           **{f"{name}_{axis}": (centre(pair[name]) or ("", ""))[index]
                              for name in PRIMARY for index, axis in enumerate(("cx", "cy"))},
                           "labels_agree": int(pair["terra"]["label"] == pair["sol"]["label"]),
                           "centre_distance_px": "" if gap is None else round(gap, 2),
                           "resolution": verdict})
            chosen = _mean_row(key, pair, label) if label else None
        else:
            source = pair.get(owner) or next(iter(pair.values()))
            chosen = {field: source.get(field, "") for field in ADJ_FIELDS}
            chosen["rater"], chosen["pass"] = "ADJUDICATOR", "full_frame"
            label = source["label"]
        shown = revealed.get(key, {})
        labels = [shown.get(name, {}).get("label", "") for name in PRIMARY]
        state = ("UNANIMOUS" if labels[0] and labels[0] == labels[1]
                 else "SPLIT" if all(labels) else "INCOMPLETE")
        agreement = ("AGREES-BOTH" if label and label == labels[0] == labels[1]
                     else "AGREES-ONE" if label in labels
                     else "AGREES-NEITHER" if label else "UNRESOLVED")
        conflict = ("PRIMARY-UNANIMOUS-CONTRADICTED"
                    if state == "UNANIMOUS" and agreement == "AGREES-NEITHER" else "")
        if not label:
            conflict = next((row["resolution"] for row in audits
                             if row["frame_key"] == key), "AUDIT-CONFLICT")
        point = centre(chosen) if chosen else None
        recon.append({"frame_key": key, "split": item["split"],
                      "why": queue_reason.get(key, ""), "adjudicator": owner,
                      "adjudicator_label": label, "terra_label": labels[0],
                      "sol_label": labels[1], "primary_state": state,
                      "adjudicator_cx": "" if point is None else round(point[0], 2),
                      "adjudicator_cy": "" if point is None else round(point[1], 2),
                      "agreement": agreement, "conflict_class": conflict})
        if conflict and key in resolved:
            chosen = {field: resolved[key].get(field, "") for field in ADJ_FIELDS}
            chosen["rater"], chosen["pass"] = "ADJUDICATOR", "claude_pixel_resolution"
        elif conflict:
            conflicts.append({"frame_key": key, "split": item["split"],
                              "sheet": item["sheet"], "conflict_class": conflict,
                              "adjudicator_label": label, "terra_label": labels[0],
                              "sol_label": labels[1]})
        if chosen and chosen.get("label"):
            decisions.append(chosen)

    write_csv(out / "adjudications_g389.csv", ADJ_FIELDS, decisions)
    write_csv(out / "reconciliation.csv", RECON_FIELDS, recon)
    write_csv(out / "audit_agreement.csv", AUDIT_FIELDS, audits)
    write_csv(out / "conflicts.csv", ("frame_key", "split", "sheet", "conflict_class",
                                      "adjudicator_label", "terra_label", "sol_label"),
              conflicts)
    gaps = [row["centre_distance_px"] for row in audits if row["centre_distance_px"] != ""]
    payload = {"judged_keys": len(judged), "decisions": len(decisions),
               "audit_keys": len(audits),
               "audit_label_agreement": (sum(row["labels_agree"] for row in audits) / len(audits)
                                         if audits else None),
               "audit_centre_p50_px": round(statistics.median(gaps), 2) if gaps else None,
               "audit_centre_max_px": max(gaps) if gaps else None,
               "audit_pairs_with_both_centres": len(gaps),
               "agreement_with_primaries": {name: sum(1 for row in recon
                                                      if row["agreement"] == name)
                                            for name in ("AGREES-BOTH", "AGREES-ONE",
                                                         "AGREES-NEITHER", "UNRESOLVED")},
               "conflicts_open": len(conflicts),
               "conflicts_resolved_from_pixels": sum(1 for row in recon
                                                     if row["conflict_class"]
                                                     and row["frame_key"] in resolved),
               "median_native_diameter_px": diameter}
    (out / "reconciliation.json").write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n",
                                             encoding="ascii", newline="\n")
    print(json.dumps(payload, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g389_reconcile")
    for flag in ("--terra", "--sol", "--ratings", "--queue", "--out-dir"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--resolved", default="")
    parser.add_argument("--median-diameter", default="37.0")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
