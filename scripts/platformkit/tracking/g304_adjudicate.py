"""G304 adjudication batch 1: two-locator matching, agreement table, sealed crop renders.

Annotation adjudication only. No registration, calibration, tracking, detector, homography
or prediction of any kind. Rules are quoted from the sealed prereg
docs/evidence/tracking/g304_adjudication_batch1_prereg_2026-09-07.md (SEAL 6c091d18...).
"""
from __future__ import annotations

import csv
import math
import os
from typing import Dict, Iterable, List, Optional, Tuple

AGREEMENT_THRESHOLD_PX = 4.0  # prereg section 3; spec value, not moved
FRAME_MIN_RESOLVED = 6        # prereg section 8
FRAME_MIN_STRUCTURES = 3      # prereg section 8
FRAME_GOOD_RULE = "p90 <= 12 px AND max <= 24 px"  # spec text; recorded, never applied here

STRUCTURE_OF: Dict[str, str] = {
    "CORNER_NEAR_L": "court_boundary_corner",
    "CORNER_NEAR_R": "court_boundary_corner",
    "CORNER_FAR_L": "court_boundary_corner",
    "CORNER_FAR_R": "court_boundary_corner",
    "LANE_BASE_L": "lane_boundary",
    "LANE_BASE_R": "lane_boundary",
    "FT_LINE_L": "free_throw_line",
    "FT_LINE_R": "free_throw_line",
    "KEY_TOP": "free_throw_circle",
    "THREE_PT_BASE_L": "three_point_arc",
    "THREE_PT_BASE_R": "three_point_arc",
    "CENTER_SIDELINE_NEAR": "sideline",
    "CENTER_SIDELINE_FAR": "sideline",
    "CENTER_CIRCLE_TOP": "center_circle",
    "CENTER_CIRCLE_BOTTOM": "center_circle",
}

RESOLVED_OUTCOMES = ("agreed", "pass1", "pass2")
UNRESOLVED_OUTCOMES = ("both_wrong", "unidentifiable")

Point = Tuple[float, float]
Key = Tuple[str, str]


def is_visible(raw: str) -> bool:
    """Both spellings: pass 1 writes TRUE/FALSE text, pass 2 writes 1/0."""
    return raw.strip().upper() in ("TRUE", "1")


def load_locator(path: str, eligible_row_ids: Iterable[str]) -> Dict[Key, Point]:
    """Normalize a locator CSV onto (row_id, landmark_name) -> (x, y). Prereg section 2."""
    eligible = set(eligible_row_ids)
    out: Dict[Key, Point] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("landmark_name") or "").strip()
            row_id = (row.get("row_id") or "").strip()
            if not name or row_id not in eligible or not is_visible(row.get("visible") or ""):
                continue
            out[(row_id, name)] = (float(row["x"]), float(row["y"]))
    return out


def load_eligible(path: str) -> Dict[str, dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["row_id"]: r for r in csv.DictReader(fh) if r["classification"] == "ELIGIBLE"}


def distance_px(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def pair_items(p1: Dict[Key, Point], p2: Dict[Key, Point]) -> List[dict]:
    """One record per (row_id, landmark_name) present in either pass. Prereg sections 2 and 4."""
    items: List[dict] = []
    for key in sorted(set(p1) | set(p2)):
        row_id, name = key
        a, b = p1.get(key), p2.get(key)
        if a is not None and b is not None:
            d = distance_px(a, b)
            presence = "both"
            disagreement = d > AGREEMENT_THRESHOLD_PX
        else:
            d = None
            presence = "pass1_only" if a is not None else "pass2_only"
            disagreement = True
        items.append({
            "row_id": row_id,
            "landmark_name": name,
            "structure": STRUCTURE_OF.get(name, "UNKNOWN"),
            "p1": a,
            "p2": b,
            "presence": presence,
            "distance_px": d,
            "needs_adjudication": disagreement,
        })
    return items


def final_coordinate(outcome: str, p1: Optional[Point], p2: Optional[Point]) -> Optional[Point]:
    """Prereg section 6."""
    if outcome == "agreed":
        return (round((p1[0] + p2[0]) / 2), round((p1[1] + p2[1]) / 2))
    if outcome == "pass1":
        return p1
    if outcome == "pass2":
        return p2
    return None


def frame_outcome(resolved_names: Iterable[str]) -> dict:
    """Prereg section 8: >= 6 resolved landmarks across >= 3 distinct structures."""
    names = list(resolved_names)
    structures = {STRUCTURE_OF.get(n, "UNKNOWN") for n in names}
    return {
        "resolved_landmarks": len(names),
        "structures": len(structures),
        "e1_ready": len(names) >= FRAME_MIN_RESOLVED and len(structures) >= FRAME_MIN_STRUCTURES,
    }


def agreement_table(items: List[dict], arena_of: Dict[str, str]) -> Dict[str, dict]:
    """Per-arena pairs / share within threshold / median / p90. Prereg section 4."""
    per: Dict[str, dict] = {}
    for it in items:
        arena = arena_of[it["row_id"]]
        acc = per.setdefault(arena, {"both": [], "pass1_only": 0, "pass2_only": 0})
        if it["presence"] == "both":
            acc["both"].append(it["distance_px"])
        else:
            acc[it["presence"]] += 1
    for acc in per.values():
        ds = sorted(acc.pop("both"))
        acc["pairs"] = len(ds)
        acc["within_threshold"] = sum(1 for d in ds if d <= AGREEMENT_THRESHOLD_PX)
        acc["share_within"] = (acc["within_threshold"] / len(ds)) if ds else None
        acc["median_px"] = ds[len(ds) // 2] if ds else None
        acc["p90_px"] = ds[int(0.9 * (len(ds) - 1))] if ds else None
        acc["max_px"] = ds[-1] if ds else None
    return per


def render_frame_sheet(frame_path: str, items: List[dict], out_path: str) -> str:
    """Prereg section 5: half-scale full frame + native 96x96 and 256 px context crops."""
    from PIL import Image, ImageDraw

    src = Image.open(frame_path).convert("RGB")
    rows = [it for it in items if it["needs_adjudication"]]
    cell, pad = 256, 8
    head = src.height // 2
    width = max(4 * cell + 5 * pad, src.width // 2)
    height = head + pad + len(rows) * (cell + 24) + pad
    sheet = Image.new("RGB", (width, height), (18, 18, 18))
    ov = src.resize((src.width // 2, src.height // 2))
    d0 = ImageDraw.Draw(ov)
    for it in items:
        for tag, pt, col in (("1", it["p1"], (255, 80, 80)), ("2", it["p2"], (80, 200, 255))):
            if pt is None:
                continue
            x, y = pt[0] / 2, pt[1] / 2
            d0.line([(x - 7, y), (x + 7, y)], fill=col, width=2)
            d0.line([(x, y - 7), (x, y + 7)], fill=col, width=2)
            d0.text((x + 8, y + 3), tag + ":" + it["landmark_name"], fill=col)
    sheet.paste(ov, (0, 0))
    dr = ImageDraw.Draw(sheet)
    for i, it in enumerate(rows):
        top = head + pad + i * (cell + 24)
        dist = "n/a" if it["distance_px"] is None else str(round(it["distance_px"], 1))
        dr.text((pad, top), "%s  [%s]  d=%s px" % (it["landmark_name"], it["presence"], dist),
                fill=(245, 245, 245))
        for j, (tag, pt) in enumerate((("P1", it["p1"]), ("P2", it["p2"]))):
            if pt is None:
                continue
            x, y = int(round(pt[0])), int(round(pt[1]))
            near = src.crop((x - 48, y - 48, x + 48, y + 48)).resize((cell, cell), Image.NEAREST)
            ctx = src.crop((x - 128, y - 128, x + 128, y + 128))
            for k, img in enumerate((near, ctx)):
                col = 2 * j + k
                ox = pad + col * (cell + pad)
                sheet.paste(img, (ox, top + 22))
                cx, cy = ox + cell // 2, top + 22 + cell // 2
                dr.line([(cx - 10, cy), (cx + 10, cy)], fill=(255, 255, 0), width=1)
                dr.line([(cx, cy - 10), (cx, cy + 10)], fill=(255, 255, 0), width=1)
                dr.text((ox + 3, top + 24), tag + (" 96px native" if k == 0 else " 256px ctx"),
                        fill=(255, 255, 0))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    sheet.save(out_path)
    return out_path
