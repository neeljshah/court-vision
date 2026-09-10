"""G376 report -- corrected denominators, evenly spaced strips and the row summary.

Denominator definitions are sealed in g376_prereg_2026-09-10.md section 5
(SEAL sha256 32bcad44e602ac870f06e02cf5118272bf1343797906905f0ed4d8d4705173ee).
Reads the classification artifacts only; writes nothing under `src/` or `data/`.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking.g376_m1 import ABSENT, M1_FIELDS

MARK = {"OBSERVED": "O", "SCHEDULED_NO_DETECTION": "D", "NOT_SCHEDULED": "N", "UNKNOWN": "U"}
LEGEND = ("O observed  D scheduled_no_detection (evaluated, no track row)  "
          "N not_scheduled (declaration over-counts)  U unknown")
STRIPS = 10
STRIP_TICKS = 80
CONSEQUENCE_FIELDS = ("section_id", "set", "declared_ticks", "producer_evaluated_ticks",
                      "route_capped_ticks", "ledger_evaluated_frames", "observed_ticks",
                      "observed_ticks_in_declared", "ledger_minus_producer",
                      "restate_evaluated_frames",
                      "zero_share_over_declared", "zero_share_over_producer_evaluated",
                      "g368_observed_pairs", "g368_producer_pairs") + M1_FIELDS
RAW_NOTE = ("observed_ticks, zero_share_over_declared and zero_share_over_producer_evaluated are "
            "RAW distinct tracking_data.csv frame counts, not G370 M1 quantities "
            "(AMENDMENT A1.2); the m1_* columns are the A1.1 corrected ones.")
_f = "{:.6f}".format


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def consequence_rows(classification: list[dict[str, str]],
                     m1: dict[str, dict[str, str]] | None = None) -> list[dict[str, Any]]:
    """Per-section corrected denominators; an unreconstructable section stays ABSENT."""
    m1 = m1 or {}   # AMENDMENT A1.1 columns; ABSENT until m1_denominators.csv exists
    rows = []
    for row in classification:
        declared = _int(row["declared_ticks"]) or 0
        producer = _int(row["producer_evaluated_ticks"])
        observed = _int(row["observed_ticks"]) or 0
        ledger = _int(row["ledger_evaluated_frames"])
        declared_observed = _int(row["observed"]) or 0
        zero = declared - declared_observed
        rows.append({
            "section_id": row["section_id"], "set": row["set"],
            "declared_ticks": declared,
            "producer_evaluated_ticks": "ABSENT" if producer is None else producer,
            "route_capped_ticks": _int(row["route_capped_ticks"])
            if _int(row["route_capped_ticks"]) is not None else "ABSENT",
            "ledger_evaluated_frames": "ABSENT" if ledger is None else ledger,
            "observed_ticks": observed,
            "observed_ticks_in_declared": declared_observed,
            "ledger_minus_producer": "ABSENT" if (producer is None or ledger is None)
            else ledger - producer,
            "restate_evaluated_frames": "ABSENT" if (producer is None or ledger is None)
            else int(ledger != producer),
            "zero_share_over_declared": _f(zero / declared) if declared else "ABSENT",
            "zero_share_over_producer_evaluated":
                _f(max(0, producer - observed) / producer) if producer else "ABSENT",
            "g368_observed_pairs": max(0, observed - 1),
            "g368_producer_pairs": "ABSENT" if producer is None else max(0, producer - 1),
        })
        rows[-1].update({field: m1.get(row["section_id"], {}).get(field, ABSENT)
                         for field in M1_FIELDS})
    return rows


def strips(ticks_path: Path, out_dir: Path) -> list[dict[str, Any]]:
    """A3: STRIPS windows spaced evenly over the whole declared-tick ordering, never a head slice."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with Path(ticks_path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    step = max(1, len(rows) // STRIPS)
    written = []
    for index in range(STRIPS):
        start = min(index * step, max(0, len(rows) - STRIP_TICKS))
        window = rows[start:start + STRIP_TICKS]
        if not window:
            continue
        path = out_dir / ("strip_%02d.txt" % index)
        lines = ["G376 strip %d of %d -- declared ticks %d..%d of %d"
                 % (index + 1, STRIPS, start, start + len(window) - 1, len(rows)), LEGEND, ""]
        lines += ["%-24s %-9s frame=%-8s %s %s"
                  % (row["section_id"], row["set"], row["frame"],
                     MARK.get(row["tick_class"], "?"), row["sub_reason"]) for row in window]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append({"strip": path.name, "bytes": path.stat().st_size,
                        "first_row": start, "ticks": len(window)})
    return written


def run(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.out)
    with (out_dir / "classification.csv").open(newline="", encoding="utf-8") as handle:
        classification = list(csv.DictReader(handle))
    m1_path = out_dir / "m1_denominators.csv"
    m1 = {}
    if m1_path.exists():
        with m1_path.open(newline="", encoding="utf-8") as handle:
            m1 = {r["section_id"]: r for r in csv.DictReader(handle)}
    rows = consequence_rows(classification, m1)
    with (out_dir / "consequence.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CONSEQUENCE_FIELDS))
        writer.writeheader()
        writer.writerows(rows)
    written = strips(out_dir / "ticks.csv", out_dir / "strips")
    summary = json.loads((out_dir / "classification_summary.json").read_text(encoding="utf-8"))
    controls = list(csv.DictReader((out_dir / "controls.csv").open(newline="", encoding="utf-8"))) \
        if (out_dir / "controls.csv").exists() else []
    rerun = json.loads((out_dir / "rerun_summary.json").read_text(encoding="utf-8")) \
        if (out_dir / "rerun_summary.json").exists() else {}
    for set_name in summary["per_set"]:
        subset = [r for r in rows if r["set"] == set_name]
        producer = [r for r in subset if r["producer_evaluated_ticks"] != "ABSENT"]
        declared = sum(r["declared_ticks"] for r in subset)
        observed = sum(r["observed_ticks"] for r in subset)
        declared_observed = sum(r["observed_ticks_in_declared"] for r in subset)
        producer_total = sum(r["producer_evaluated_ticks"] for r in producer)
        scored = [m1[r["section_id"]] for r in subset if r["section_id"] in m1
                  and m1[r["section_id"]]["m1_zero_ticks_over_producer_evaluated"] != ABSENT]
        m1_evaluated = sum(int(r["producer_evaluated_ticks"]) for r in scored)
        m1_zero = sum(int(r["m1_zero_ticks_over_producer_evaluated"]) for r in scored)
        m1_declared = sum(int(r["declared_ticks"]) for r in scored)
        m1_zero_declared = sum(int(r["m1_zero_ticks_over_declared"]) for r in scored)
        summary["per_set"][set_name]["corrected_denominators"] = {
            "declared_ticks": declared,
            "producer_evaluated_ticks": producer_total,
            "observed_ticks": observed,
            "observed_ticks_in_declared": declared_observed,
            "route_capped_ticks": sum(r["route_capped_ticks"] for r in subset
                                      if isinstance(r["route_capped_ticks"], int)),
            "zero_share_over_declared":
                _f((declared - declared_observed) / declared) if declared else None,
            "zero_share_over_producer_evaluated":
                _f(max(0, producer_total - observed) / producer_total) if producer_total else None,
            "sections_to_restate": sum(1 for r in producer if r["restate_evaluated_frames"] == 1),
            "g368_observed_pairs": sum(r["g368_observed_pairs"] for r in subset),
            "g368_producer_pairs": sum(r["g368_producer_pairs"] for r in producer),
            "g368_pair_denominator_ratio":
                _f(sum(r["g368_observed_pairs"] for r in producer)
                   / sum(r["g368_producer_pairs"] for r in producer))
                if sum(r["g368_producer_pairs"] for r in producer) else None,
            "m1_sections_scored": len(scored),
            "m1_producer_evaluated_ticks": m1_evaluated,
            "m1_zero_ticks_over_producer_evaluated": m1_zero,
            "m1_zero_share_over_producer_evaluated":
                _f(m1_zero / m1_evaluated) if m1_evaluated else None,
            "g370_declared_ticks": m1_declared,
            "g370_m1_zero_ticks_over_declared": m1_zero_declared,
            "g370_m1_zero_share_over_declared":
                _f(m1_zero_declared / m1_declared) if m1_declared else None,
        }
    summary["raw_column_semantics"] = RAW_NOTE
    summary["controls"] = controls
    summary["controls_passed"] = bool(controls) and all(int(c["passed"]) for c in controls)
    summary["rerun"] = rerun
    summary["strips"] = written
    summary["strip_bytes_max"] = max((s["bytes"] for s in written), default=0)
    summary["bars"] = {
        set_name: {
            "classified_share": _f(1.0 - float(values["shares"]["unknown"])),
            "bar_classified_at_least": "0.95",
            "met": float(values["shares"]["unknown"]) <= 0.05,
        } for set_name, values in summary["per_set"].items()}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    summary = run(args)
    print(json.dumps({"bars": summary["bars"], "controls_passed": summary["controls_passed"],
                      "strip_bytes_max": summary["strip_bytes_max"],
                      "corrected": {k: v["corrected_denominators"]
                                    for k, v in summary["per_set"].items()}},
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
