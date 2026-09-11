"""G384 finisher adjudication: blind native montages and settled-label merge."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.platformkit.tracking.g363_ball_coverage import read_csv
from scripts.platformkit.tracking.g384_queue import interleaved_queue

DEC_FIELDS = ("ordinal", "frame_key", "split", "why", "label", "panel",
              "cx", "cy", "diameter", "reason")
FULL_W, FULL_H, CROP_N, CROP_D, PER_SHEET = 640, 360, 120, 180, 4


def completed_keys(path: Path) -> set[str]:
    """Read the actual completed decision keys before allocating another finisher pass."""
    if not path.exists():
        return set()
    if path.suffix == ".json":
        return {row["frame_key"] for row in json.loads(path.read_text(encoding="ascii"))}
    with path.open(encoding="ascii", newline="") as handle:
        return {row["frame_key"] for row in csv.DictReader(handle) if row.get("frame_key")}


DEFAULT_COMPLETED = Path("docs/evidence/tracking/g384_ball_phase2_receipt_2026-09-10/adjudications_g384.csv")


def load(root: Path, completed_path: Path | None = None) -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    """Read the landed G373 tables and build the fixed interleaved finisher order."""
    manifest = read_csv(root / "sheet_manifest_all.csv")
    queue = read_csv(root / "adjudication_queue.csv")
    order = interleaved_queue(manifest, queue, completed_keys(completed_path or DEFAULT_COMPLETED) if (completed_path or DEFAULT_COMPLETED).is_file() else set())
    man = {row["frame_key"]: row for row in manifest}
    rat: dict[str, dict] = {}
    for row in read_csv(root / "ratings_v2_merged.csv"):
        if row["rater"] in ("terra", "sol"):
            rat.setdefault(row["frame_key"], {})[row["rater"]] = row
    return order, man, rat


def panels(key: str, pair: dict[str, dict]) -> list[dict | None]:
    """Hide rater identity: a key-derived hash fixes the two panel slots."""
    boxed = [pair[name] for name in ("terra", "sol")
             if pair[name]["label"] == "VISIBLE" and pair[name].get("box_w")]
    if len(boxed) == 2 and int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 2:
        boxed.reverse()
    return boxed + [None] * (2 - len(boxed))


def _crop(img: Image.Image, rating: dict | None) -> Image.Image:
    """Cut a native-pixel window centred on a claimed ball centre."""
    tile = Image.new("RGB", (CROP_D, CROP_D), (24, 24, 24))
    if rating is None:
        return tile
    cx, cy, half = float(rating["cx"]), float(rating["cy"]), CROP_N // 2
    box = (int(cx) - half, int(cy) - half, int(cx) + half, int(cy) + half)
    tile = img.crop(box).resize((CROP_D, CROP_D), Image.LANCZOS)
    pen, mid = ImageDraw.Draw(tile), CROP_D // 2
    for a, b in (((mid, mid - 22), (mid, mid - 9)), ((mid, mid + 9), (mid, mid + 22)),
                 ((mid - 22, mid), (mid - 9, mid)), ((mid + 9, mid), (mid + 22, mid))):
        pen.line([a, b], fill=(0, 255, 0), width=1)
    return tile


def montage(rows: list[dict], man: dict, rat: dict, sheets: Path, out: Path) -> list[dict]:
    """Render one blind sheet of PER_SHEET frames: full view plus candidate windows."""
    canvas = Image.new("RGB", (FULL_W + CROP_D, FULL_H * len(rows)), (12, 12, 12))
    pen, legend = ImageDraw.Draw(canvas), []
    for slot, row in enumerate(rows):
        key = row["frame_key"]
        img = Image.open(sheets / man[key]["sheet"]).convert("RGB")
        top = slot * FULL_H
        canvas.paste(img.resize((FULL_W, FULL_H), Image.LANCZOS), (0, top))
        slots = panels(key, rat[key])
        canvas.paste(_crop(img, slots[0]), (FULL_W, top))
        canvas.paste(_crop(img, slots[1]), (FULL_W, top + CROP_D))
        pen.rectangle([0, top, FULL_W + CROP_D - 1, top + FULL_H - 1], outline=(90, 90, 90))
        pen.text((6, top + 6), "#%d %s" % (row["ordinal"], row["why"][:3]), fill=(255, 255, 0))
        pen.text((FULL_W + 4, top + 4), "P1", fill=(255, 255, 0))
        pen.text((FULL_W + 4, top + CROP_D + 4), "P2", fill=(255, 255, 0))
        legend.append({"ordinal": row["ordinal"], "frame_key": key, "split": row["split"],
                       "why": row["why"],
                       "p1": slots[0] and (slots[0]["cx"], slots[0]["cy"], slots[0]["box_w"]),
                       "p2": slots[1] and (slots[1]["cx"], slots[1]["cy"], slots[1]["box_w"])})
    canvas.save(out, quality=88)
    return legend


def append(path: Path, rows: list[dict]) -> None:
    """Append settled decisions; the decision log is append-only by construction."""
    completed = completed_keys(path)
    incoming = [row["frame_key"] for row in rows]
    if len(incoming) != len(set(incoming)) or set(incoming) & completed:
        raise ValueError("duplicate-decision-key")
    fresh = not path.exists()
    with path.open("a", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DEC_FIELDS, lineterminator="\n")
        if fresh:
            writer.writeheader()
        writer.writerows(rows)
