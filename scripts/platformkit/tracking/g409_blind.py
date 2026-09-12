"""Blind-mark comparison for G409.

The blind marks were written in G406 before any producer or comparator box was
displayed (blind_order_receipt.csv timestamps the ordering). They are reused
here unchanged as a detector-independent native-pixel judgement: every stored
producer row is scored against them before and after the code-derived uncrop.
"""
from __future__ import annotations

import json
import statistics as stats
from pathlib import Path

from scripts.platformkit.tracking import g409_build as B

TOPCUT = B.TOPCUT


def load_blind() -> dict[str, dict]:
    path = B.G406 / "blind_marks.jsonl"
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["card_id"]] = rec
    return out


def iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def best_mark(box, marks) -> tuple[str, float]:
    best_id, best = "", 0.0
    for mark in marks:
        value = iou(box, (mark["bbox_x1"], mark["bbox_y1"], mark["bbox_x2"], mark["bbox_y2"]))
        if value > best:
            best_id, best = mark["person_id"], value
    return best_id, best


def build_per_tick() -> tuple[list[dict], list[dict], dict]:
    blind = load_blind()
    rows = B.read_csv(B.G406 / "all_masked_rows.csv")
    order = {r["card_id"]: r for r in B.read_csv(B.G406 / "blind_order_receipt.csv")}
    out = []
    for row in rows:
        card = row["card_id"]
        marks = blind[card]["marks"]
        stored = tuple(float(row["bbox_" + k]) for k in ("x1", "y1", "x2", "y2"))
        mapped = (stored[0], stored[1] + TOPCUT, stored[2], stored[3] + TOPCUT)
        bid, biou = best_mark(stored, marks)
        mid, miou = best_mark(mapped, marks)
        out.append({
            "box_id": row["box_id"], "card_id": card, "draw_kind": row["draw_kind"],
            "section_id": row["section_id"], "frame": row["frame"],
            "position_source": row["position_source"],
            "native_width": row["native_width"], "native_height": row["native_height"],
            "stored_x1": stored[0], "stored_y1": stored[1],
            "stored_x2": stored[2], "stored_y2": stored[3],
            "mapped_x1": mapped[0], "mapped_y1": mapped[1],
            "mapped_x2": mapped[2], "mapped_y2": mapped[3],
            "stored_straddles_crop_line": "1" if stored[1] <= 0 else "0",
            "blind_best_id_before": bid, "blind_best_iou_before": round(biou, 4),
            "blind_best_id_after": mid, "blind_best_iou_after": round(miou, 4),
            "blind_iou_improved": "1" if miou > biou else "0",
            "blind_hit_before": "1" if biou >= 0.5 else "0",
            "blind_hit_after": "1" if miou >= 0.5 else "0",
            "blind_completed_utc": order[card]["blind_completed_utc"],
            "overlay_opened_utc": order[card]["overlay_opened_utc"],
            "transform": "native_y = stored_y + %d (unified_pipeline.py:1693)" % TOPCUT,
        })
    receipts = []
    for card in sorted(blind):
        rec = blind[card]
        receipts.append({
            "card_id": card, "n_marks": len(rec["marks"]),
            "n_uncertain": sum(1 for m in rec["marks"] if m["certainty"] != "CERTAIN"),
            "native_width": rec["native_width"], "native_height": rec["native_height"],
            "view_sha256": rec["view_sha256"],
            "blind_completed_utc": order[card]["blind_completed_utc"],
            "overlay_opened_utc": order[card]["overlay_opened_utc"],
            "marks_precede_overlay": "1" if order[card]["blind_completed_utc"]
                                     < order[card]["overlay_opened_utc"] else "0",
            "source": "G406 blind_marks.jsonl reused verbatim; no new marking in G409",
        })
    before = [r["blind_best_iou_before"] for r in out]
    after = [r["blind_best_iou_after"] for r in out]
    summary = {
        "rows": len(out),
        "distinct_frames": len({r["card_id"] for r in out}),
        "median_best_iou_before": round(stats.median(before), 4),
        "median_best_iou_after": round(stats.median(after), 4),
        "hits_ge_0_50_before": sum(1 for r in out if r["blind_hit_before"] == "1"),
        "hits_ge_0_50_after": sum(1 for r in out if r["blind_hit_after"] == "1"),
        "improved": sum(1 for r in out if r["blind_iou_improved"] == "1"),
        "not_improved": sum(1 for r in out if r["blind_iou_improved"] == "0"),
        "blind_marks_precede_every_overlay": all(r["marks_precede_overlay"] == "1"
                                                 for r in receipts),
    }
    return out, receipts, summary


def render_rows() -> dict[str, dict[str, list]]:
    """Per card: every stored row, its code-mapped box and every comparator box."""
    by_card: dict[str, dict[str, list]] = {}
    for row in B.read_csv(B.G406 / "all_masked_rows.csv"):
        entry = by_card.setdefault(row["card_id"], {"stored": [], "mapped": [], "comparator": []})
        box = tuple(float(row["bbox_" + k]) for k in ("x1", "y1", "x2", "y2"))
        entry["stored"].append(box)
        entry["mapped"].append((box[0], box[1] + TOPCUT, box[2], box[3] + TOPCUT))
    for det in B.read_csv(B.G406 / "comparator_detections.csv"):
        entry = by_card.setdefault(det["card_id"], {"stored": [], "mapped": [], "comparator": []})
        entry["comparator"].append(tuple(float(det["bbox_" + k]) for k in ("x1", "y1", "x2", "y2")))
    return by_card


def frame_path(card_id: str) -> Path:
    return B.FRAMES / (card_id + ".png")
