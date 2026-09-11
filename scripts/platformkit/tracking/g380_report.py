"""G380 aggregation: diff the independent trace against the stamped labels, then summarise.

  trace     build trace.csv (one row per emitted producer row) and its agreement
  summarize fold every measured artifact into summary.json
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

TRACE_FIELDS = ("frame", "order", "trace_branch_label", "trace_final_label", "trace_event",
                "stamped_label", "stamped_branch", "stamped_event", "agree")


def _trace_rows(path: Path) -> list:
    """Rebuild the per-emitted-row label sequence the independent hook observed."""
    pending, rows = None, []
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        parts = line.split(",")
        if parts[0] == "L" and len(parts) >= 5:
            pending = {"frame": int(parts[2]), "slot": int(parts[1]),
                       "trace_branch_label": parts[3], "trace_final_label": parts[3],
                       "trace_event": parts[5] if len(parts) >= 6 else ""}
        elif parts[0] == "R" and len(parts) >= 4 and pending is not None:
            pending["trace_branch_label"] = parts[1]
            pending["trace_final_label"] = parts[2]
            rows.append(pending)
            pending = None
    return rows


def _csv_rows(path: Path) -> dict:
    grouped = defaultdict(list)
    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            try:
                grouped[int(row["frame"])].append(row)
            except (KeyError, ValueError, TypeError):
                continue
    return grouped


def cmd_trace(args) -> None:
    """Diff the independent trace against the stamped labels, one emitted row at a time.

    The unit is the FRAME, not the row offset: the producer's post-clamp duplicate
    suppression removes rows after the labels are read, and the CSV writer does not
    promise the within-frame order the trace saw.  So every stamped row is matched
    to an unconsumed traced row of the same final label in the same frame, and the
    metric is how many stamped rows find one.  A frame carrying MORE stamped rows
    than the trace observed would be a real disagreement and is counted separately.
    """
    traced, stamped = _trace_rows(Path(args.trace)), _csv_rows(Path(args.csv))
    by_frame = defaultdict(list)
    for row in traced:
        by_frame[row["frame"]].append(row)
    out, agree, compared, over = [], 0, 0, 0
    for frame in sorted(stamped):
        have = list(by_frame.get(frame, []))
        if len(stamped[frame]) > len(have):
            over += 1
        for order, row in enumerate(stamped[frame]):
            label = row.get("position_source", "MISSING")
            hit = next((item for item in have if item["trace_final_label"] == label), None)
            if hit is not None:
                have.remove(hit)
                agree += 1
            compared += 1
            out.append({"frame": frame, "order": order,
                        "trace_branch_label": hit["trace_branch_label"] if hit else "",
                        "trace_final_label": hit["trace_final_label"] if hit else "",
                        "trace_event": hit["trace_event"] if hit else "",
                        "stamped_label": label,
                        "stamped_branch": row.get("source_branch", ""),
                        "stamped_event": row.get("matched_event_id", ""),
                        "agree": hit is not None})
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TRACE_FIELDS), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out)
    block = {"emitted_rows": compared, "traced_rows": len(traced), "agree": agree,
             "unmatched": compared - agree, "frames": len(stamped),
             "frames_with_more_stamped_than_traced": over,
             "agreement": round(agree / compared, 6) if compared else "UNKNOWN",
             "trace_final_label_counts": dict(Counter(r["trace_final_label"] for r in traced)),
             "stamped_label_counts": dict(Counter(r["stamped_label"] for r in out))}
    Path(args.out).with_name("trace_summary.json").write_text(
        json.dumps(block, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(block, sort_keys=True))


def _read(path: Path) -> list:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def cmd_summarize(args) -> None:
    out = Path(args.out)
    pairs, identity = _read(out / "replay_pairs.csv"), _read(out / "identity.csv")
    receipts, controls = _read(out / "receipts.csv"), _read(out / "controls.csv")
    traced_sections = _read(out / "receipts_trace.csv")
    a3 = _read(out / "receipts_trace_a3.csv")
    overlays = _read(out / "renders" / "overlays_index.csv")
    ok = [row for row in pairs if row["status"] == "OK"]
    done = {row["game_id"] for row in ok}
    excluded = {row["game_id"]: row["status"] for row in pairs if row["status"] != "OK"}
    ratios = [float(row["ratio"]) for row in ok if row["ratio"]]
    identity = [row for row in identity if row["game_id"] in done]
    receipts = [row for row in receipts if row["game_id"] in done]
    identical = [row for row in identity if row["identical"] == "True"]
    labels = Counter()
    for row in receipts:
        if row.get("label_counts"):
            labels.update(json.loads(row["label_counts"]))
    total = sum(labels.values())
    block = {
        "paired_replay": {
            "planned": len(pairs), "completed_pairs": len(ok),
            "source_gone": sum(1 for r in pairs if r["status"] == "SOURCE_GONE"),
            "arm_failed": sum(1 for r in pairs if r["status"] == "ARM_FAILED"),
            "distinct_videos": len({r["game_id"].split("_s")[0] for r in ok}),
            "median_ratio": round(statistics.median(ratios), 6) if ratios else "UNKNOWN",
            "ratio_bar": 1.10,
            "throughput_verdict": ("PASS" if ratios and statistics.median(ratios) <= 1.10
                                   and len(ok) >= 30 else "NOT VALIDATED"),
        },
        "unchanged_column_identity": {
            "n": len(identity), "identical": len(identical),
            "differences": len(identity) - len(identical),
            "ball_identical": sum(1 for r in identity if r["ball_identical"] == "True"),
        },
        "receipts": {
            "n": len(receipts),
            "present": sum(1 for r in receipts if r["receipt_present"] == "True"),
            "receipt_equals_trace": sum(1 for r in receipts
                                        if r.get("receipt_equals_trace") == "True"),
            "trace_subset_of_receipt": sum(1 for r in receipts
                                           if r.get("trace_subset_of_receipt") == "True"),
        },
        "excluded_from_identity_and_receipts": excluded,
        "controls": {"n": len(controls),
                     "construct": sum(1 for r in controls if r["kind"] == "CONSTRUCT"),
                     "pass": sum(1 for r in controls if r["result"] == "PASS"),
                     "fail": sum(1 for r in controls if r["result"] == "FAIL"),
                     "observed": sum(1 for r in controls if r["result"] == "OBSERVED")},
        "receipt_trace_sections": {
            "n": len(traced_sections),
            "receipt_equals_trace": sum(1 for r in traced_sections
                                        if r.get("receipt_equals_trace") == "True"),
            "trace_subset_of_receipt": sum(1 for r in traced_sections
                                           if r.get("trace_subset_of_receipt") == "True"),
            "bar": "1.000000 equality, sealed and unmoved",
        },
        # Amendment A3: the trace set is every producer-EVALUATED ATTEMPT, logged by the
        # independent hook before any row filter.  Every drawn section stays in n.
        "receipt_trace_attempt_level_a3": {
            "n": len(a3),
            "distinct_videos": len({row.get("video") for row in a3}),
            "ran": sum(1 for row in a3 if row.get("status") == "OK"),
            "receipt_equals_trace": sum(1 for row in a3
                                        if row.get("receipt_equals_trace") == "True"),
            "trace_subset_of_receipt": sum(1 for row in a3
                                           if row.get("trace_subset_of_receipt") == "True"),
            "receipt_only_ticks_total": sum(int(row.get("receipt_only_ticks") or 0)
                                            for row in a3),
            "trace_only_ticks_total": sum(int(row.get("trace_only_ticks") or 0) for row in a3),
            "bar": "1.000000 equality on n >= 30 sections / >= 10 videos, sealed and unmoved",
        },
        "eye_check": {
            "even_live_overlays": sum(1 for r in overlays if r["kind"] == "EVEN"),
            "construct_overlays": sum(1 for r in overlays if r["kind"] == "CONSTRUCT"),
            "live_HELD_rows": labels.get("HELD", 0),
        },
        "label_distribution": dict(labels),
        "provenance_carrying_share": round(
            sum(v for k, v in labels.items() if k != "MISSING") / total, 6) if total else "UNKNOWN",
        "g368_clamp_or_subpixel_resolved": {
            "CLAMP": labels.get("CLAMP", 0), "SUBPIXEL": labels.get("SUBPIXEL", 0),
            "HELD": labels.get("HELD", 0),
            "clamp_share_of_the_pooled_class": round(
                labels.get("CLAMP", 0) / (labels.get("CLAMP", 0) + labels.get("SUBPIXEL", 0)), 6)
            if labels.get("CLAMP", 0) + labels.get("SUBPIXEL", 0) else "UNKNOWN",
            "note": "G368 pooled these as one unresolved class on 0.584961 of held steps",
        },
    }
    if args.merge and (out / "summary.json").is_file():
        current = json.loads((out / "summary.json").read_text(encoding="ascii"))
        current.update(block)
        block = current
    (out / "summary.json").write_text(json.dumps(block, indent=2, sort_keys=True) + "\n",
                                      encoding="ascii")
    print(json.dumps(block, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    trace = sub.add_parser("trace")
    trace.add_argument("--trace", required=True)
    trace.add_argument("--csv", required=True)
    trace.add_argument("--out", required=True)
    trace.set_defaults(handler=cmd_trace)
    summarize = sub.add_parser("summarize")
    summarize.add_argument("--out", required=True)
    summarize.add_argument("--merge", action="store_true")
    summarize.set_defaults(handler=cmd_summarize)
    args = parser.parse_args()
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
