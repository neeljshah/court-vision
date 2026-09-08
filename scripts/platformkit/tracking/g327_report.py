"""G327 scoring -- every reported value recomputed from the PER-ARM CSVs alone.

The attempt-1 defect this module exists to remove: a value that came from the summary
JSON rather than from the committed rows. Nothing here opens a summary. The only input
besides the seven `g327a2_boxes_<arm>.csv` files is `g327a2_arms.csv`, the run's own
per-arm record of the MEASURED network tensor shape and dtype, which decides whether an
isolation arm's named factor was ACTUALLY APPLIED -- it carries no comparison value.

SCREENING ONLY: these numbers say whether two passes AGREE, never which one is right.

Q6 SERIALISATION. Every share is a FRACTION PAIR of integers, never a bare decimal, and
every pixel delta is an INTEGER THOUSANDTH of a pixel. Integer cells are zero-padded to
six digits. No restricted digit sequence can survive that form.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from scripts.platformkit.tracking.g327_arms import (
    IOU_MATCH, bit_identical, canon, greedy_pairs, read_arm_csv, rows_for,
)

REF = "single"
PIN_ARMS = ("pad", "fp32", "nmsord")
PIN_BAR = 110       # sealed; CAUSE PINNED needs exactly one applied arm at or above this
DET_BAR = 120       # sealed; DETERMINISTIC needs all 120
ARM_ORDER = ("single_repeat", "batch2", "batch8", "pad", "fp32", "nmsord")


def frac(num: int, den: int) -> str:
    """A share as a zero-padded integer fraction pair. Never a bare decimal (Q6)."""
    return "%06d/%06d" % (num, den)


def milli(px: float) -> int:
    """A pixel distance as an integer thousandth of a pixel (Q6)."""
    return int(round(float(px) * 1000.0))


def pct_rank(values: list, q: float) -> int:
    """Nearest-rank percentile over integers -- no interpolation, so no new decimal."""
    if not values:
        return 0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return s[k]


def load_arms(artifact: Path) -> dict:
    """The run's per-arm MEASURED tensor record. Shapes/dtypes only, never a metric."""
    out: dict = {}
    lines = (artifact / "g327a2_arms.csv").read_text(encoding="ascii").splitlines()
    head = lines[0].split(",")
    for line in lines[1:]:
        if not line.strip():
            continue
        rec = dict(zip(head, line.split(",")))
        out.setdefault(rec["arm"], []).append(rec)
    return out


def pair_stats(ref_rows: list, arm_rows: list, sort: bool) -> dict:
    """Coordinate agreement over IoU-matched pairs, plus full bit-identity per frame."""
    ident = [bit_identical(r, a, sort) for r, a in zip(ref_rows, arm_rows)]
    deltas, exact_coord, exact_full, matched = [], 0, 0, 0
    boxes_ref = boxes_arm = 0
    count_delta = 0
    for r, a in zip(ref_rows, arm_rows):
        cr, ca = canon(r, sort), canon(a, sort)
        boxes_ref += len(cr)
        boxes_arm += len(ca)
        count_delta += abs(len(ca) - len(cr))
        for i, k in greedy_pairs(cr, ca):
            matched += 1
            d = np.abs(cr[i, :4] - ca[k, :4]).max()
            deltas.append(milli(d))
            exact_coord += int(d == 0.0)
            exact_full += int(np.array_equal(cr[i], ca[k]))
    return {"frames": len(ref_rows), "bit_identical_frames": int(sum(ident)),
            "boxes_ref": boxes_ref, "boxes_arm": boxes_arm, "matched_pairs": matched,
            "abs_count_delta_total": count_delta,
            "agree_ref_in_arm": frac(matched, boxes_ref) if boxes_ref else "",
            "agree_arm_in_ref": frac(matched, boxes_arm) if boxes_arm else "",
            "coordinate_exact_pairs": frac(exact_coord, matched) if matched else "",
            "bit_exact_pairs": frac(exact_full, matched) if matched else "",
            "delta_milli_px_median": pct_rank(deltas, 0.5),
            "delta_milli_px_p99": pct_rank(deltas, 0.99),
            "delta_milli_px_max": max(deltas) if deltas else 0,
            "iou_match": IOU_MATCH, "ordering": "sorted" if sort else "emission"}


def table(report: dict) -> str:
    """The PER-GAME / PER-ARM table the memo carries, or names with its sha256."""
    out = ["# G327 attempt 2 -- per-game / per-arm agreement and bit-identity",
           "",
           "Every value below is recomputed from the seven per-arm CSVs alone. Shares are",
           "integer fraction pairs; pixel deltas are integer thousandths of a pixel.",
           "Denominator is every evaluated frame of that game, zero-box frames included.",
           "",
           "| slot | game | arm | frames | boxes ref | boxes arm | bit-identical frames |"
           " abs count delta | agree ref-in-arm | agree arm-in-ref | coord-exact pairs |"
           " bit-exact pairs | delta milli-px med | p99 | max |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for g in report["games"]:
        for arm in ARM_ORDER:
            c = g["arms"][arm]
            out.append("| %06d | %s | %s | %06d | %06d | %06d | %06d/%06d | %06d | %s |"
                       " %s | %s | %s | %06d | %06d | %06d |"
                       % (g["slot"], g["game"], arm, c["frames"], c["boxes_ref"],
                          c["boxes_arm"], c["bit_identical_frames"], c["frames"],
                          c["abs_count_delta_total"], c["agree_ref_in_arm"],
                          c["agree_arm_in_ref"], c["coordinate_exact_pairs"],
                          c["bit_exact_pairs"], c["delta_milli_px_median"],
                          c["delta_milli_px_p99"], c["delta_milli_px_max"]))
    out += ["", "## Pooled over every evaluated frame", "",
            "| arm | bit-identical frames | applied? | measured tensor shape | dtype |",
            "|---|---|---|---|---|"]
    for arm in ARM_ORDER:
        t = report["totals"][arm]
        out.append("| %s | %06d/%06d | %s | %s | %s |"
                   % (arm, t["bit_identical_frames"], t["frames"],
                      report["isolation_arm_applied"].get(arm, "n/a"),
                      report["measured_tensor_shapes"].get(arm, ""),
                      report["measured_tensor_dtypes"].get(arm, "")))
    out += ["", "## Zero-box frames per arm (explicit CSV rows, in every denominator)",
            "", "| slot | " + " | ".join(ARM_ORDER) + " | " + REF + " |",
            "|---|" + "---|" * (len(ARM_ORDER) + 1)]
    for g in report["games"]:
        out.append("| %06d | " % g["slot"]
                   + " | ".join("%06d" % g["zero_box_frames"][a] for a in ARM_ORDER)
                   + " | %06d |" % g["zero_box_frames"][REF])
    return "\n".join(out) + "\n"


def score(args) -> None:
    """LOCAL arithmetic over the committed per-arm CSVs. Writes the report and table."""
    artifact = Path(args.artifact)
    order, tables = {}, {}
    for arm in (REF,) + ARM_ORDER:
        o, t = read_arm_csv(artifact / ("g327a2_boxes_%s.csv" % arm))
        order[arm], tables[arm] = o, t
    slots = sorted(order[REF])
    meta = load_arms(artifact)
    shapes = {a: " ".join(sorted({r["tensor_shape"] for r in meta.get(a, [])}))
              for a in meta}
    dtypes = {a: " ".join(sorted({r["dtype"] for r in meta.get(a, [])})) for a in meta}
    report = {"iou_match": IOU_MATCH, "pin_bar": PIN_BAR, "det_bar": DET_BAR,
              "reconstructed_from": "per-arm CSVs only",
              "measured_tensor_shapes": shapes, "measured_tensor_dtypes": dtypes,
              "games": [], "totals": {}}
    totals: dict = {a: {"frames": 0, "bit_identical_frames": 0} for a in ARM_ORDER}
    for slot in slots:
        idxs = order[REF][slot]
        ref = rows_for(tables[REF][slot], idxs)
        cells, zeros = {}, {REF: sum(1 for r in ref if not len(r[0]))}
        for arm in ARM_ORDER:
            if order[arm].get(slot) != idxs:
                raise ValueError("arm %s slot %d frame list differs from %s"
                                 % (arm, slot, REF))
            rows = rows_for(tables[arm][slot], idxs)
            cells[arm] = pair_stats(ref, rows, sort=(arm == "nmsord"))
            zeros[arm] = sum(1 for r in rows if not len(r[0]))
            totals[arm]["frames"] += cells[arm]["frames"]
            totals[arm]["bit_identical_frames"] += cells[arm]["bit_identical_frames"]
        # The CSVs carry no clip name -- by design, since the scorer reads nothing else.
        # The slot is the game's identity here; the summary JSON maps slot -> clip.
        report["games"].append({"slot": slot, "game": "slot_%06d" % slot,
                                "arms": cells, "zero_box_frames": zeros})
    report["totals"] = totals
    # An isolation arm counts only if the factor it names was ACTUALLY APPLIED, judged by
    # the MEASURED tensor record: ultralytics caches one predictor and can ignore a
    # per-call kwarg, which is how attempt 1 found ARM PAD to be a measured no-op.
    applied = {"pad": shapes.get("pad") != shapes.get("batch8"),
               "fp32": dtypes.get("fp32") != dtypes.get("batch8"), "nmsord": True}
    report["isolation_arm_applied"] = applied
    cleared = [a for a in PIN_ARMS
               if applied[a] and totals[a]["bit_identical_frames"] >= PIN_BAR]
    report["arms_not_applied"] = [a for a in PIN_ARMS if not applied[a]]
    report["arms_clearing_pin_bar"] = cleared
    baseline_fails = totals["batch8"]["bit_identical_frames"] < PIN_BAR
    report["batch8_below_pin_bar"] = bool(baseline_fails)
    report["verdict_cause"] = ("CAUSE PINNED: %s" % cleared[0]) if (
        len(cleared) == 1 and baseline_fails) else (
        "NOT PINNED (CONFOUNDED)" if len(cleared) > 1 else "NOT PINNED")
    det = totals["single_repeat"]["bit_identical_frames"]
    n = totals["single_repeat"]["frames"]
    report["verdict_determinism"] = ("DETERMINISTIC %d/%d" % (det, n) if det >= DET_BAR
                                     else "NOT DETERMINISTIC %d/%d" % (det, n))
    Path(args.out).write_text(json.dumps(report, indent=1), encoding="ascii")
    Path(args.table).write_text(table(report), encoding="ascii")
    print(report["verdict_cause"], "|", report["verdict_determinism"])
    for arm in ARM_ORDER:
        t = totals[arm]
        print("  %-14s bit-identical %3d/%-4d applied=%s"
              % (arm, t["bit_identical_frames"], t["frames"],
                 report["isolation_arm_applied"].get(arm, "n/a")))
