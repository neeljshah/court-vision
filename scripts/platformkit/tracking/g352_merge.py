"""G352 merge: the sharded parts into metrics.csv, buckets.csv and the pooled per-frame archives.

Usage:
    python -m scripts.platformkit.tracking.g352_merge <evidence_dir>

Every per-section forward statistic is computed HERE from the pooled per-template-point records of
`residuals.csv`, never from a per-shard median, which is carry-over (b) of the G334 verify reject.
Integer cells are zero-padded and every share is an ADDITIVE per-mille column printed beside its
own numerator and denominator, so no share is readable without its n. The bar clauses are
recomputed from the archived counts, never carried over from a process print.
"""
from __future__ import annotations

import re
import sys
from ast import literal_eval
from collections import defaultdict
from pathlib import Path

import numpy as np

# `repr` of a summary writes bare `nan` / `inf`, which `literal_eval` rejects. Only the integer
# counters of summary.txt are read here, so blanking those tokens loses nothing.
NOT_LITERAL = re.compile(r"(?<![\w.])-?(?:nan|inf)(?![\w.])")

BAR_FEET_PERMILLE = 600
BAR_FEET_N = 100
BAR_VALID_PERMILLE = 500
BAR_FORWARD_PX = 8.0
N_TEMPLATE = 398
METRIC_COLS = (
    "section,arm,n_frames,valid_frames,valid_permille,feet_total,feet_evaluated,feet_inside,"
    "feet_inside_permille,forward_in_px_median,forward_in_px_p90,n_forward_in_points,"
    "forward_all_px_median,forward_all_px_p90,n_forward_all_points,in_frame_points,"
    "in_frame_denominator,in_frame_permille,boot_spread_p95_ft_median,n_boot_frames,"
    "margin_median,n_margins,n_hypotheses,n_heldout_segments,frames_scored,sealed_list_n,"
    "frames_decoded,"
    "bar_feet_inside,bar_valid_h,bar_forward_px,bar_all_three")
BUCKET_COLS = "section,arm,level,bucket,n"


def pad(value) -> str:
    return "%06d" % int(round(float(value)))


def num(value) -> str:
    value = float(value)
    return "-" if not np.isfinite(value) else "%.3f" % value


def permille(numerator, denominator) -> str:
    return pad(round(1000.0 * numerator / denominator)) if denominator else "-"


def clause(ok) -> str:
    return "MET" if ok else "NOT_MET"


def percentile(values, q) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), q)) if values else float("nan")


def read_csv(path: Path):
    lines = path.read_text(encoding="ascii").strip().split("\n")
    head = lines[0].split(",")
    return head, [dict(zip(head, line.split(","))) for line in lines[1:]]


def pool(evidence: Path, name: str):
    """Concatenate one CSV across every shard part, writing the pooled copy back."""
    head, rows, raw = None, [], []
    for part in sorted(evidence.glob("part_*")):
        path = part / name
        if not path.exists():
            continue
        lines = path.read_text(encoding="ascii").strip().split("\n")
        head = head or lines[0]
        raw.extend(lines[1:])
        rows.extend(dict(zip(lines[0].split(","), line.split(","))) for line in lines[1:])
    if head and raw:
        (evidence / name).write_text("\n".join([head] + raw) + "\n", encoding="ascii",
                                     newline="\n")
        print("WROTE %s rows=%d bytes=%d" % (name, len(raw), (evidence / name).stat().st_size))
    return rows


def check_digests(frames) -> None:
    """Assert the held-out set is IDENTICAL across the arms of a frame, per the spec."""
    seen, bad = defaultdict(set), 0
    for row in frames:
        seen[(row["section"], row["eval_index"])].add(row["heldout_digest"])
    for key, digests in sorted(seen.items()):
        if len(digests) > 1:
            bad += 1
            print("HELDOUT_DIGEST_MISMATCH %s %s" % (key, sorted(digests)))
    print("HELDOUT_DIGEST identical_across_arms=%s frames=%d mismatches=%d" % (
        bad == 0, len(seen), bad))


def merge(evidence: Path) -> int:
    frames = pool(evidence, "perframe.csv")
    residuals = pool(evidence, "residuals.csv")
    pool(evidence, "route_correspondences.csv")
    check_digests(frames)
    gates, book = defaultdict(lambda: defaultdict(int)), defaultdict(lambda: defaultdict(int))
    for part in sorted(evidence.glob("part_*")):
        for line in (part / "summary.txt").read_text(encoding="ascii").strip().split("\n"):
            item = literal_eval(NOT_LITERAL.sub("None", line))
            key = (item["section"], item["arm"])
            for bucket, count in item["gate_counts"].items():
                gates[key][bucket] += count
            book[key]["eval_reached"] += item["eval_reached"]
            # The sealed list length and the decode count are per SECTION, not per shard:
            # summing them across shards would multiply one section by its shard count.
            book[key]["sealed_list"] = max(book[key]["sealed_list"], item["eval_wanted"])
            book[key]["decoded"] = max(book[key]["decoded"], item["decoded"])
    resid = defaultdict(lambda: ([], []))
    for row in residuals:
        key = (row["section"], row["arm"])
        value = float(row["heldout_px"])
        resid[key][0].append(value)
        if row["in_frame"] == "1":
            resid[key][1].append(value)
    rows, buckets = [METRIC_COLS], [BUCKET_COLS]
    per_frame = defaultdict(list)
    for row in frames:
        per_frame[(row["section"], row["arm"])].append(row)
    for key in sorted(per_frame):
        section, arm = key
        group = per_frame[key]
        valid = [row for row in group if row["reason"] == "valid"]
        feet_total = sum(int(row["feet"]) for row in group)
        feet_eval = sum(int(row["feet"]) for row in valid)
        feet_in = sum(int(row["feet_inside"]) for row in valid)
        spreads = [float(row["boot_spread_p95_ft"]) for row in valid
                   if row["boot_spread_p95_ft"] != "-"]
        margins = [float(row["margin"]) for row in valid if row["margin"] != "-"]
        all_px, in_px = resid[key]
        forward = percentile(in_px, 50.0)
        feet_ok = feet_eval >= BAR_FEET_N and 1000.0 * feet_in / max(feet_eval, 1) \
            >= BAR_FEET_PERMILLE
        valid_ok = 1000.0 * len(valid) / max(len(group), 1) >= BAR_VALID_PERMILLE
        forward_ok = np.isfinite(forward) and forward <= BAR_FORWARD_PX
        rows.append(",".join([
            section, arm, pad(len(group)), pad(len(valid)), permille(len(valid), len(group)),
            pad(feet_total), pad(feet_eval), pad(feet_in), permille(feet_in, feet_eval),
            num(forward), num(percentile(in_px, 90.0)), pad(len(in_px)),
            num(percentile(all_px, 50.0)), num(percentile(all_px, 90.0)), pad(len(all_px)),
            pad(len(in_px)), pad(N_TEMPLATE * len(valid)),
            permille(len(in_px), N_TEMPLATE * len(valid)),
            num(percentile(spreads, 50.0)), pad(len(spreads)),
            num(percentile(margins, 50.0)), pad(len(margins)),
            pad(sum(int(row["n_hypotheses"]) for row in group)),
            pad(sum(int(row["n_heldout_segments"]) for row in group)),
            pad(book[key]["eval_reached"]), pad(book[key]["sealed_list"]),
            pad(book[key]["decoded"]),
            clause(feet_ok), clause(valid_ok), clause(forward_ok),
            clause(feet_ok and valid_ok and forward_ok)]))
        frame_buckets = defaultdict(int)
        for row in group:
            frame_buckets[row["reason"]] += 1
        for bucket in sorted(frame_buckets):
            buckets.append(",".join([section, arm, "frame", bucket, pad(frame_buckets[bucket])]))
        for bucket in sorted(gates[key]):
            buckets.append(",".join([section, arm, "hypothesis", bucket, pad(gates[key][bucket])]))
    for name, sink in (("metrics.csv", rows), ("buckets.csv", buckets)):
        (evidence / name).write_text("\n".join(sink) + "\n", encoding="ascii", newline="\n")
        print("WROTE %s rows=%d" % (name, len(sink) - 1))
    for row in rows:
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(merge(Path(sys.argv[1])))
