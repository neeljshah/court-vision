"""G376 -- classify every DECLARED evaluated tick against the reconstructed producer schedule.

Classes and their decision order are sealed in g376_prereg_2026-09-10.md section 3
(SEAL sha256 32bcad44e602ac870f06e02cf5118272bf1343797906905f0ed4d8d4705173ee). Reads only.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Iterator, Mapping

from scripts.platformkit.tracking.g376_schedule import (
    latest_ledger_records, section_facts, snapshot_manifest)

CLASSES = ("OBSERVED", "SCHEDULED_NO_DETECTION", "NOT_SCHEDULED", "UNKNOWN")
SUB_REASONS = ("SUSPENDED", "BEYOND_ROUTE_CAP", "OFF_PRODUCER_LATTICE", "GATED_OR_UNREACHED")
TICK_FIELDS = ("section_id", "set", "frame", "tick_class", "sub_reason")
_f = "{:.6f}".format


def classify_section(facts: Mapping[str, Any]) -> Iterator[tuple[int, str, str]]:
    """One (frame, class, sub_reason) per declared tick; the four classes partition the set."""
    unknown = facts["schedule_reason"] or facts.get("pin_moved")
    tracked, evaluated, suspended = facts["tracked"], facts["evaluated"], facts["suspended"]
    stride, cap = facts["stride"], facts["route_max_frames"]
    lattice = facts["observed_stride"]
    cap_frame = stride * (cap // stride) if (cap and stride) else None
    for frame in facts["declared"]:
        if unknown:
            yield frame, "UNKNOWN", str(unknown)
            continue
        if frame in tracked:
            yield frame, "OBSERVED", ""
        elif frame in evaluated:
            yield frame, "SCHEDULED_NO_DETECTION", ""
        elif frame in suspended:
            yield frame, "NOT_SCHEDULED", "SUSPENDED"
        elif cap_frame is not None and frame >= cap_frame:
            yield frame, "NOT_SCHEDULED", "BEYOND_ROUTE_CAP"
        elif lattice and frame % lattice:
            yield frame, "NOT_SCHEDULED", "OFF_PRODUCER_LATTICE"
        else:
            yield frame, "NOT_SCHEDULED", "GATED_OR_UNREACHED"


def section_row(facts: Mapping[str, Any], ticks: list[tuple[int, str, str]]) -> dict[str, Any]:
    """Per-section counts, shares and the four sealed denominators. No tick is dropped."""
    counts = {name: 0 for name in CLASSES}
    subs = {name: 0 for name in SUB_REASONS}
    for _, tick_class, sub in ticks:
        counts[tick_class] += 1
        if sub in subs:
            subs[sub] += 1
    declared = len(ticks)
    share = (lambda n: _f(n / declared) if declared else "")
    evaluated_ticks = "" if facts["schedule_reason"] else len(facts["evaluated"])
    row = {"section_id": facts["section_id"], "set": facts["set"],
           "declared_ticks": declared, "declared_reason": facts["declared_reason"],
           "schedule_reason": facts["schedule_reason"],
           "stride": facts["stride"] or "", "decoded_frames": facts["decoded_frames"] or "",
           "ledger_evaluated_frames": facts["ledger_evaluated_frames"] or "",
           "verdict_evaluated_frames": facts["verdict_evaluated_frames"] or "",
           "producer_evaluated_ticks": evaluated_ticks,
           "route_max_frames": facts["route_max_frames"] or "",
           "route_capped_ticks": facts["route_capped_ticks"] or "",
           "verdict_attempted_frames_capped": facts["verdict_attempted_frames_capped"] or "",
           "observed_ticks": len(facts["tracked"]), "ball_rows": facts["ball_rows"],
           "tracking_rows": facts["tracking_rows"], "observed_stride": facts["observed_stride"] or "",
           "suspended_frames": len(facts["suspended"]),
           "zero_observation_ticks": declared - counts["OBSERVED"],
           "zero_observation_share": share(declared - counts["OBSERVED"]),
           "tracking_path": facts["tracking_path"], "tracking_bytes": facts["tracking_bytes"],
           "ball_path": facts["ball_path"], "ball_bytes": facts["ball_bytes"]}
    row.update({name.lower(): counts[name] for name in CLASSES})
    row.update({name.lower() + "_share": share(counts[name]) for name in CLASSES})
    row.update({"sub_" + name.lower(): subs[name] for name in SUB_REASONS})
    return row


def _sections(args: argparse.Namespace) -> list[tuple[str, str, Mapping[str, Any]]]:
    """The two sealed section sets with the ledger record each was declared from."""
    out: list[tuple[str, str, Mapping[str, Any]]] = []
    sealed_ids = [r["section_id"] for r in csv.DictReader(
        Path(args.sealed_census).open(encoding="utf-8", newline=""))]
    sealed_ledger = latest_ledger_records(Path(args.sealed_ledger))
    for section_id in sealed_ids:
        out.append((section_id, "SEALED34", sealed_ledger.get(section_id, {})))
    fresh_ledger = latest_ledger_records(Path(args.fresh_ledger))
    for row in csv.DictReader(Path(args.fresh_csv).open(encoding="utf-8", newline="")):
        if row.get("selected") == "1":
            out.append((row["section_name"], "FRESH69", fresh_ledger.get(row["section_name"], {})))
    return out


def _pins(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {r["section_id"] + "/" + r["file"]: r["sha256"] for r in rows}


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Classify both sets, write ticks.csv and classification.csv, return the set summary."""
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    sections = _sections(args)
    before = snapshot_manifest({sid: name for sid, name, _ in sections},
                               Path(args.snapshot), out_dir / "snapshot_manifest.csv")
    section_rows, per_set = [], {}
    with (out_dir / "ticks.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TICK_FIELDS))
        writer.writeheader()
        for section_id, set_name, record in sections:
            facts = section_facts(section_id, set_name, Path(args.snapshot) / section_id, record)
            ticks = list(classify_section(facts))
            writer.writerows({"section_id": section_id, "set": set_name, "frame": frame,
                              "tick_class": tick_class, "sub_reason": sub}
                             for frame, tick_class, sub in ticks)
            section_rows.append(section_row(facts, ticks))
    after = snapshot_manifest({sid: name for sid, name, _ in sections},
                              Path(args.snapshot), out_dir / "snapshot_manifest_after.csv")
    after_pins = _pins(after)
    moved = [key for key, digest in _pins(before).items() if after_pins.get(key) != digest]
    with (out_dir / "classification.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(section_rows[0]))
        writer.writeheader()
        writer.writerows(section_rows)
    for set_name in ("SEALED34", "FRESH69"):
        rows = [r for r in section_rows if r["set"] == set_name]
        declared = sum(r["declared_ticks"] for r in rows)
        totals = {name.lower(): sum(r[name.lower()] for r in rows) for name in CLASSES}
        subs = {name.lower(): sum(r["sub_" + name.lower()] for r in rows) for name in SUB_REASONS}
        zero = sum(r["zero_observation_ticks"] for r in rows)
        evaluated = [r for r in rows if r["producer_evaluated_ticks"] != ""]
        per_set[set_name] = {
            "sections": len(rows), "declared_ticks": declared,
            "counts": totals, "not_scheduled_sub_reasons": subs,
            "shares": {name: _f(totals[name] / declared) if declared else None for name in totals},
            "zero_observation_ticks": zero,
            "zero_observation_share": _f(zero / declared) if declared else None,
            "producer_evaluated_ticks": sum(r["producer_evaluated_ticks"] for r in evaluated),
            "observed_ticks": sum(r["observed_ticks"] for r in rows),
            "sections_without_schedule": sum(1 for r in rows if r["schedule_reason"]),
            "sections_non_integral_decoded_over_evaluated": sum(
                1 for r in rows if r["decoded_frames"] and r["ledger_evaluated_frames"]
                and r["decoded_frames"] % r["ledger_evaluated_frames"]),
            "sections_evaluated_frames_to_restate": sum(
                1 for r in evaluated if r["producer_evaluated_ticks"] != r["ledger_evaluated_frames"]),
        }
    summary = {"per_set": per_set, "pins_moved_during_run": moved,
               "snapshot": str(Path(args.snapshot).resolve())}
    (out_dir / "classification_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--sealed-census", required=True)
    parser.add_argument("--sealed-ledger", required=True)
    parser.add_argument("--fresh-csv", required=True)
    parser.add_argument("--fresh-ledger", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    summary = run(args)
    for set_name, values in summary["per_set"].items():
        print("%s declared=%d %s" % (set_name, values["declared_ticks"],
                                     json.dumps(values["shares"], sort_keys=True)))
        print("  zero_observation_share=%s non_integral=%d restate=%d unknown_sections=%d"
              % (values["zero_observation_share"],
                 values["sections_non_integral_decoded_over_evaluated"],
                 values["sections_evaluated_frames_to_restate"],
                 values["sections_without_schedule"]))
        print("  not_scheduled_sub_reasons=%s"
              % json.dumps(values["not_scheduled_sub_reasons"], sort_keys=True))
    print("pins_moved_during_run=%d" % len(summary["pins_moved_during_run"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
