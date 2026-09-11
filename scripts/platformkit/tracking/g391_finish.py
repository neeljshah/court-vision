"""G391: kappa and the blind adjudication queue, then the unblinded class census.

Stage `queue` runs entirely blind: it never opens the reference or the score table,
so the adjudicator decides from pixels without knowing which calls were scored
false. Stage `unblind` joins the sealed packet map and reports every class against
BOTH denominators, and records suspected reference errors as an audit output --
the G389 reference and the G390 verdict are immutable here.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import math
from pathlib import Path

EV = "docs/evidence/tracking"
OUT_NAME = "g391_ball_false_call_audit_2026-09-11"
REFERENCE = EV + "/g389_ball_reference_completion_2026-09-11/reference_v3.csv"
FRAMES = EV + "/g389_ball_reference_completion_2026-09-11/frames_v3.csv"
SCORES = EV + "/g390_ball_a8_sealed_pass_2026-09-11/paired_frame_scores.csv"
RATERS = ("terra", "sol")
OBJECTS = ("BALL", "PERSON_OR_APPAREL", "CROWD", "SIGNAGE_OR_GRAPHIC", "EQUIPMENT",
           "COURT_OR_LOGO", "OTHER", "UNKNOWN")
STATES = ("BALL_AT_MARKER", "BALL_ELSEWHERE", "NO_BALL_VISIBLE", "BALL_UNCERTAIN")
TARGET_HEIGHT = 720.0


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def kappa(first: list[str], second: list[str], universe: tuple[str, ...]) -> float | None:
    """Cohen kappa over the sealed category set."""
    n = len(first)
    if n == 0 or n != len(second):
        return None
    observed = sum(1 for a, b in zip(first, second) if a == b) / n
    expected = sum((first.count(c) / n) * (second.count(c) / n) for c in universe)
    return None if expected >= 1.0 else (observed - expected) / (1.0 - expected)


def paired(rows: list[dict]) -> dict[str, dict[str, dict]]:
    by_packet: dict[str, dict[str, dict]] = collections.defaultdict(dict)
    for row in rows:
        by_packet[row["packet_id"]][row["rater"]] = row
    return by_packet


def stage_queue(out_dir: Path) -> int:
    """Blind: kappa on both sealed fields and the disagreement queue for pixels."""
    rows = read(out_dir / "blind_ratings.csv")
    packets = [row["packet_id"] for row in read(out_dir / "packets.csv")]
    by_packet = paired(rows)
    both = [p for p in packets if len(by_packet[p]) == 2]
    objects = [[by_packet[p][r]["object"] for p in both] for r in RATERS]
    states = [[by_packet[p][r]["ball_state"] for p in both] for r in RATERS]
    queue = [{"packet_id": p,
              "terra_object": by_packet[p]["terra"]["object"],
              "sol_object": by_packet[p]["sol"]["object"],
              "terra_ball_state": by_packet[p]["terra"]["ball_state"],
              "sol_ball_state": by_packet[p]["sol"]["ball_state"],
              "field": ("object+ball_state"
                        if by_packet[p]["terra"]["object"] != by_packet[p]["sol"]["object"]
                        and by_packet[p]["terra"]["ball_state"]
                        != by_packet[p]["sol"]["ball_state"]
                        else "object"
                        if by_packet[p]["terra"]["object"] != by_packet[p]["sol"]["object"]
                        else "ball_state"),
              "card": EV + "/" + OUT_NAME + "/cards/" + p + ".jpg"}
             for p in both
             if by_packet[p]["terra"]["object"] != by_packet[p]["sol"]["object"]
             or by_packet[p]["terra"]["ball_state"] != by_packet[p]["sol"]["ball_state"]]
    write(out_dir / "adjudication_queue.csv", queue,
          ["packet_id", "field", "terra_object", "sol_object", "terra_ball_state",
           "sol_ball_state", "card"])
    agreement = {
        "n_packets": len(packets), "n_rated_by_both": len(both),
        "n_rated_by_one_or_none": len(packets) - len(both),
        "kappa_object": kappa(objects[0], objects[1], OBJECTS),
        "kappa_ball_state": kappa(states[0], states[1], STATES),
        "raw_agreement_object": sum(1 for a, b in zip(*objects) if a == b) / len(both),
        "raw_agreement_ball_state": sum(1 for a, b in zip(*states) if a == b) / len(both),
        "n_disagreements": len(queue),
        "terra_object_counts": dict(collections.Counter(objects[0])),
        "sol_object_counts": dict(collections.Counter(objects[1])),
    }
    (out_dir / "audit_agreement.json").write_text(json.dumps(agreement, indent=2),
                                                  encoding="ascii")
    print("AGREEMENT both=%d kappa_object=%.4f kappa_state=%.4f disagreements=%d"
          % (agreement["n_rated_by_both"], agreement["kappa_object"] or 0.0,
             agreement["kappa_ball_state"] or 0.0, len(queue)))
    return 0


def resolve(packet: str, by_packet: dict, decisions: dict) -> tuple[str, str, str]:
    """One reconciled judgment; both originals stay archived in blind_ratings.csv."""
    pair = by_packet[packet]
    if len(pair) < 2:
        rater = next(iter(pair), None)
        if rater is None:
            return "UNKNOWN", "BALL_UNCERTAIN", "UNRATED"
        return pair[rater]["object"], pair[rater]["ball_state"], "SINGLE_RATER"
    terra, sol = pair["terra"], pair["sol"]
    if terra["object"] == sol["object"] and terra["ball_state"] == sol["ball_state"]:
        return terra["object"], terra["ball_state"], "AGREED"
    decision = decisions.get(packet)
    if not decision:
        return "UNKNOWN", "BALL_UNCERTAIN", "UNRESOLVED"
    return decision["object"], decision["ball_state"], "ADJUDICATED"


def audit_class(obj: str, state: str, label: str) -> str:
    """The sealed audit classes, derived from the reconciled object and location."""
    # What the call LANDED ON is the taxonomy. Whether a ball happens to be
    # elsewhere in the frame does not make a call on a spectator anything but a
    # background confusion, so ball_state only decides the BALL branch.
    if obj == "UNKNOWN":
        return "UNCERTAIN_REFERENCE_OR_PIXELS"
    if obj == "BALL":
        if state == "BALL_AT_MARKER":
            return ("NEAR_MISS_LOCALISATION" if label == "VISIBLE"
                    else "SUSPECTED_REFERENCE_ERROR")
        if state == "BALL_ELSEWHERE":
            return "DUPLICATE_OR_SECOND_BALL"
        return "UNCERTAIN_REFERENCE_OR_PIXELS"
    return "BACKGROUND_CONFUSION_" + obj


def stage_unblind(out_dir: Path, root: Path) -> int:
    """Unblind and report every class for false and true calls, both denominators."""
    ratings = read(out_dir / "blind_ratings.csv")
    packets = read(out_dir / "packets.csv")
    keys = {row["packet_id"]: row["frame_key"]
            for row in read(out_dir / "packet_key_map_SEALED.csv")}
    adjudication = out_dir / "adjudication.csv"
    decisions = {row["packet_id"]: row for row in read(adjudication)} \
        if adjudication.exists() else {}
    scores = {row["frame_key"]: row for row in read(root / SCORES) if row["arm"] == "A8"}
    reference = {row["frame_key"]: row for row in read(root / REFERENCE)
                 if row["split"] == "heldout"}
    frames = {row["frame_key"]: row for row in read(root / FRAMES)}
    by_packet = paired(ratings)
    rows, disputes = [], []
    for packet in packets:
        pid = packet["packet_id"]
        key = keys[pid]
        obj, state, how = resolve(pid, by_packet, decisions)
        score = scores[key]
        ref = reference[key]
        outcome = "TRUE_CALL" if int(score["tp"]) == 1 else "FALSE_CALL"
        rows.append({"packet_id": pid, "frame_key": key, "outcome": outcome,
                     "reference_label": ref["label"], "object": obj,
                     "ball_state": state, "resolution": how,
                     "audit_class": audit_class(obj, state, ref["label"]),
                     "distance_720p": score["distance_720p"],
                     "threshold_720p": score["threshold_720p"],
                     "game": packet["game"], "section": packet["section"],
                     "frame_index": packet["frame_index"]})
        if rows[-1]["audit_class"] == "SUSPECTED_REFERENCE_ERROR" and outcome == "FALSE_CALL":
            scale = TARGET_HEIGHT / float(frames[key]["height"])
            rater_d = ""
            pair = by_packet.get(pid, {})
            centres = [(float(r["ball_cx"]), float(r["ball_cy"])) for r in pair.values()
                       if r["ball_cx"]]
            if centres and ref["cx"]:
                rater_d = round(min(math.hypot(cx - float(ref["cx"]),
                                               cy - float(ref["cy"])) * scale
                                    for cx, cy in centres), 4)
            disputes.append({"packet_id": pid, "frame_key": key,
                             "reference_label": ref["label"],
                             "reference_cx": ref["cx"], "reference_cy": ref["cy"],
                             "reconciled_object": obj, "reconciled_ball_state": state,
                             "resolution": how,
                             "rater_to_reference_720p": rater_d,
                             "note": "raters place the game ball at the candidate on a "
                                     "non-VISIBLE reference frame"})
    write(out_dir / "object_ledger.csv", rows, list(rows[0].keys()))
    write(out_dir / "reference_disputes.csv", disputes,
          list(disputes[0].keys()) if disputes else
          ["packet_id", "frame_key", "reference_label", "reference_cx", "reference_cy",
           "reconciled_object", "reconciled_ball_state", "resolution",
           "rater_to_reference_720p", "note"])
    counts = census(rows)
    write(out_dir / "object_counts.csv", counts,
          ["audit_class", "object", "false_calls", "share_of_169_false",
           "true_calls", "share_of_90_true", "all_calls", "share_of_259_calls"])
    summary = {
        "n_calls": len(rows), "n_false_calls": sum(1 for r in rows
                                                   if r["outcome"] == "FALSE_CALL"),
        "n_true_calls": sum(1 for r in rows if r["outcome"] == "TRUE_CALL"),
        "resolution": dict(collections.Counter(r["resolution"] for r in rows)),
        "suspected_reference_errors": len(disputes),
        "denominators": {"false_calls": 169, "true_calls": 90, "all_calls": 259,
                         "held_out_states": 549},
        "agreement": json.loads((out_dir / "audit_agreement.json").read_text()),
        "classes": counts,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="ascii")
    print("UNBLIND calls=%d false=%d true=%d unresolved=%d suspected_ref_errors=%d"
          % (len(rows), summary["n_false_calls"], summary["n_true_calls"],
             summary["resolution"].get("UNRESOLVED", 0), len(disputes)))
    for row in counts:
        print("  %-42s FP %3d (%.3f)  TP %3d (%.3f)"
              % (row["audit_class"], row["false_calls"], row["share_of_169_false"],
                 row["true_calls"], row["share_of_90_true"]))
    return 0


def stage_eyecheck(out_dir: Path) -> int:
    """Even 30-card samples over the FP set and over all calls; never a head slice."""
    rows = read(out_dir / "object_ledger.csv")
    renders = out_dir / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    index = []
    for name, subset in (("fp", [r for r in rows if r["outcome"] == "FALSE_CALL"]),
                         ("all", rows)):
        step = len(subset) / 30.0
        picks = [subset[min(len(subset) - 1, int(round(position * step)))]
                 for position in range(30)]
        seen: set[str] = set()
        for position, row in enumerate(picks):
            duplicate = row["packet_id"] in seen
            seen.add(row["packet_id"])
            target = renders / ("%s_%02d_%s.jpg" % (name, position, row["packet_id"]))
            if not duplicate:
                target.write_bytes((out_dir / "cards" / (row["packet_id"] + ".jpg")).read_bytes())
            index.append({"sample": name, "position": position, "packet_id": row["packet_id"],
                          "duplicate_of_earlier_pick": int(duplicate),
                          "outcome": row["outcome"], "reference_label": row["reference_label"],
                          "audit_class": row["audit_class"], "object": row["object"],
                          "ball_state": row["ball_state"], "resolution": row["resolution"],
                          "game": row["game"], "section": row["section"],
                          "frame_index": row["frame_index"],
                          "render": ("renders/" + target.name) if not duplicate else ""})
    write(out_dir / "eye_check_index.csv", index, list(index[0].keys()))
    duplicates = sum(row["duplicate_of_earlier_pick"] for row in index)
    print("EYE-CHECK cards=%d duplicates=%d" % (len(index), duplicates))
    return 0


def census(rows: list[dict]) -> list[dict]:
    """Per-class counts and shares against BOTH denominators, never one alone."""
    n_false = sum(1 for r in rows if r["outcome"] == "FALSE_CALL") or 1
    n_true = sum(1 for r in rows if r["outcome"] == "TRUE_CALL") or 1
    keyed = collections.Counter((r["audit_class"], r["object"]) for r in rows)
    out = []
    for audit, obj in sorted(keyed):
        subset = [r for r in rows if r["audit_class"] == audit and r["object"] == obj]
        false_calls = sum(1 for r in subset if r["outcome"] == "FALSE_CALL")
        true_calls = len(subset) - false_calls
        out.append({"audit_class": audit, "object": obj, "false_calls": false_calls,
                    "share_of_169_false": round(false_calls / n_false, 4),
                    "true_calls": true_calls,
                    "share_of_90_true": round(true_calls / n_true, 4),
                    "all_calls": len(subset),
                    "share_of_259_calls": round(len(subset) / len(rows), 4)})
    return out


def write(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(prog="g391_finish")
    parser.add_argument("--root", default=r"C:\Users\neelj\nba-track-a10")
    parser.add_argument("--stage", choices=("queue", "unblind", "eyecheck"), required=True)
    args = parser.parse_args()
    root = Path(args.root)
    out_dir = root / EV / OUT_NAME
    if args.stage == "queue":
        return stage_queue(out_dir)
    if args.stage == "eyecheck":
        return stage_eyecheck(out_dir)
    return stage_unblind(out_dir, root)


if __name__ == "__main__":
    raise SystemExit(main())
