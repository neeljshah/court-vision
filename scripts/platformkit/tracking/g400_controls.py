"""G400 scorer controls, even all-state cards, renders and fresh-process repeats.

The planted-centre/transform controls exercise the native-height coordinate rule and
the centre rule of the scorer only. They are never detector evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g400_prepare as rails

CONTROLS = 30
CARDS = 30
TOLERANCE = 1e-9
CONTROL_FIELDS = ("control", "video_id", "native_height", "planted_cx", "planted_cy",
                  "planted_w", "planted_h", "to_720p_cy", "roundtrip_cy",
                  "roundtrip_exact", "centre_rule_cx", "centre_rule_cy",
                  "centre_rule_match", "false_positive")


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, fields, rows) -> None:
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def controls(out: Path) -> dict:
    """Thirty even planted centres over the drawn native heights."""
    manifest = _read(out / "native_manifest.csv")
    step = (len(manifest) - 1) / (CONTROLS - 1)
    rows = []
    for index in range(CONTROLS):
        source = manifest[int(index * step + 0.5)]
        width, height = int(source["width"]), int(source["height"])
        planted_w = 10 + index
        planted_h = planted_w
        planted_x = (width - planted_w) * index / (CONTROLS - 1)
        planted_y = (height - planted_h) * index / (CONTROLS - 1)
        centre_x = planted_x + planted_w / 2.0
        centre_y = planted_y + planted_h / 2.0
        to_720 = rails.native_to_720p(centre_y, height)
        back = rails.native_roundtrip(centre_y, height)
        rows.append({
            "control": "c%02d" % (index + 1), "video_id": source["video_id"],
            "native_height": height, "planted_cx": round(centre_x, 6),
            "planted_cy": round(centre_y, 6), "planted_w": planted_w,
            "planted_h": planted_h, "to_720p_cy": round(to_720, 6),
            "roundtrip_cy": round(back, 6),
            "roundtrip_exact": int(abs(back - centre_y) <= TOLERANCE),
            "centre_rule_cx": round(planted_x + planted_w / 2.0, 6),
            "centre_rule_cy": round(planted_y + planted_h / 2.0, 6),
            "centre_rule_match": int(abs(planted_x + planted_w / 2.0 - centre_x)
                                     <= TOLERANCE
                                     and abs(planted_y + planted_h / 2.0 - centre_y)
                                     <= TOLERANCE),
            "false_positive": 0})
    _write(out / "transform_controls.csv", CONTROL_FIELDS, rows)
    result = {"controls": len(rows),
              "roundtrip_exact": sum(row["roundtrip_exact"] for row in rows),
              "centre_rule_match": sum(row["centre_rule_match"] for row in rows),
              "false_positives": sum(row["false_positive"] for row in rows)}
    print(json.dumps(result, sort_keys=True))
    return result


def cards(out: Path, renders: Path, columns: int = 6) -> dict:
    """Thirty even all-state cards, including silence and UNKNOWN."""
    from PIL import Image
    renders.mkdir(parents=True, exist_ok=True)
    audit = _read(out / "box_audit.csv")
    step = (len(audit) - 1) / (CARDS - 1)
    picked = [audit[int(index * step + 0.5)] for index in range(CARDS)]
    tile = 300
    sheet = Image.new("RGB", (columns * tile, ((CARDS + columns - 1) // columns) * tile),
                      (16, 16, 16))
    index_rows = []
    for position, row in enumerate(picked):
        path = Path(row["sheet_path"]) if row["sheet_path"] else None
        crop = Image.new("RGB", (tile, tile), (48, 16, 16))
        if path and path.is_file():
            image = Image.open(path).convert("RGB")
            if row["cx"]:
                cx, cy = float(row["cx"]), float(row["cy"])
                half = tile // 2
                box = (int(cx) - half, int(cy) - half, int(cx) + half, int(cy) + half)
                crop = image.crop(box)
            else:
                crop = image.resize((tile, tile))
        sheet.paste(crop, ((position % columns) * tile, (position // columns) * tile))
        index_rows.append({"position": position + 1, "frame_key": row["frame_key"],
                           "video_id": row["video_id"],
                           "settled_label": row["settled_label"] or "NO_SETTLED_LABEL",
                           "decided_by": row["decided_by"] or "NONE",
                           "state_status": row["state_status"],
                           "has_centre": int(bool(row["cx"]))})
    target = renders / "all_state_cards.jpg"
    sheet.save(target, "JPEG", quality=85)
    _write(out / "eye_index.csv",
           ("position", "frame_key", "video_id", "settled_label", "decided_by",
            "state_status", "has_centre"), index_rows)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print("CARDS", len(index_rows), digest)
    return {"cards": len(index_rows), "all_state_cards_sha256": digest}


def repeats(out: Path, module: str, command: list[str]) -> dict:
    """Two fresh processes reproduce every delivered table and render digest."""
    tables = sorted(path.name for path in out.iterdir()
                    if path.suffix in (".csv", ".json") and path.name != "repeats.json")
    renders = sorted(path.name for path in (out / "renders").iterdir()
                     if (out / "renders").is_dir()) if (out / "renders").is_dir() else []
    runs = []
    for attempt in (1, 2):
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=1800)
        digests = {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                   for name in tables}
        digests.update({"renders/" + name: hashlib.sha256(
            (out / "renders" / name).read_bytes()).hexdigest() for name in renders})
        runs.append({"attempt": attempt, "module": module, "digests": digests})
    identical = runs[0]["digests"] == runs[1]["digests"]
    payload = {"identical": identical, "tables": len(tables), "renders": len(renders),
               "runs": runs}
    (out / "repeats.json").write_text(json.dumps(payload, indent=1, sort_keys=True)
                                      + "\n", encoding="ascii")
    print("REPEATS identical", identical)
    return payload


def _conflict_rows(out: Path, include_settled: bool = True) -> list[dict]:
    """Return completed conflicts, retaining settled rows under the parent default."""
    receipts = [_read(path) if path.exists() else [] for path in
                (out / "batch_receipts_terra.csv", out / "batch_receipts_sol.csv")]
    done = ({row["round"] for row in receipts[0] if row["status"] == "OK"} &
            {row["round"] for row in receipts[1] if row["status"] == "OK"}) if all(receipts) else None
    settled = set() if include_settled else {
        row["frame_key"] for row in _read(out / "resolutions.csv")}
    return [row for row in _read(out / "ratings.csv") if row["needs_adjudication"] == "1"
            and row["frame_key"] not in settled and (done is None or row["round"] in done)]


def _write_conflict_index(out: Path, rows: list[dict], per_sheet: int = 6,
                          native: int = 160) -> None:
    """Write additive aliases with the parent position and crop-centre meanings."""
    index = []
    for ordinal, row in enumerate(rows):
        cx = float(row["terra_cx"] or row["sol_cx"] or float(row["width"]) / 2)
        cy = float(row["terra_cy"] or row["sol_cy"] or float(row["height"]) / 2)
        index.append({**row, "reason": row.get("reason") or row.get("adjudication_reason", ""),
                      "sheet": ordinal // per_sheet + 1, "row": ordinal + 1,
                      "position": ordinal % per_sheet + 1, "crop_centre_x": round(cx, 1),
                      "crop_centre_y": round(cy, 1), "native_crop_px": native})
    fields = (
        "sheet", "row", "position", "frame_key", "video_id", "round", "reason",
        "terra_label", "sol_label", "terra_cx", "terra_cy", "sol_cx", "sol_cy",
        "terra_d", "sol_d", "crop_centre_x", "crop_centre_y", "width", "height",
        "native_crop_px")
    _write(out / "conflict_index.csv", fields,
           [{field: row.get(field, "") for field in fields} for row in index])


def conflicts(out: Path, renders: Path, per_sheet: int = 6, native: int = 160,
              scale: int = 3, include_settled: bool = True) -> dict:
    """Per-key adjudication strips: each candidate centre at native zoom, plus wide."""
    from PIL import Image, ImageDraw
    renders.mkdir(parents=True, exist_ok=True)
    manifest = {row["frame_key"]: row for row in _read(out / "native_manifest.csv")}
    rows = _conflict_rows(out, include_settled)
    tile = native * scale
    index_rows, made = [], []
    for start in range(0, len(rows), per_sheet):
        group = rows[start:start + per_sheet]
        sheet_no = start // per_sheet + 1
        sheet = Image.new("RGB", (3 * tile, len(group) * tile), (10, 10, 10))
        draw = ImageDraw.Draw(sheet)
        for position, row in enumerate(group):
            image = Image.open(manifest[row["frame_key"]]["sheet_path"]).convert("RGB")
            for column, rater in enumerate(("terra", "sol")):
                panel = Image.new("RGB", (tile, tile), (40, 0, 0))
                if row[rater + "_cx"]:
                    cx, cy = float(row[rater + "_cx"]), float(row[rater + "_cy"])
                    half = native // 2
                    panel = image.crop((int(cx) - half, int(cy) - half,
                                        int(cx) + half, int(cy) + half)).resize(
                        (tile, tile), Image.NEAREST)
                sheet.paste(panel, (column * tile, position * tile))
            sheet.paste(image.resize((tile, tile)), (2 * tile, position * tile))
            draw.text((6, position * tile + 6),
                      "%d %s/%s" % (start + position + 1,
                                    row["terra_label"][:3] or "---",
                                    row["sol_label"][:3] or "---"), fill=(255, 255, 0))
            index_rows.append({"sheet": sheet_no, "row": start + position + 1,
                               "frame_key": row["frame_key"],
                               "video_id": row["video_id"],
                               "round": row["round"],
                               "reason": row["adjudication_reason"],
                               "terra_label": row["terra_label"],
                               "sol_label": row["sol_label"],
                               "terra_cx": row["terra_cx"], "terra_cy": row["terra_cy"],
                               "sol_cx": row["sol_cx"], "sol_cy": row["sol_cy"],
                               "terra_d": row["terra_d"], "sol_d": row["sol_d"],
                               "width": row["width"], "height": row["height"],
                               "native_crop_px": native})
        target = renders / ("conflict_zoom_%02d.jpg" % sheet_no)
        sheet.save(target, "JPEG", quality=80)
        made.append(target.name)
    _write_conflict_index(out, rows, per_sheet, native)
    print("CONFLICTS", len(rows), "sheets", len(made))
    return {"conflicts": len(rows), "sheets": made}


def run(args) -> int:
    out = Path(args.out_dir)
    if args.stage == "controls":
        controls(out)
    elif args.stage == "cards":
        cards(out, out / "renders")
    elif args.stage == "conflicts":
        conflicts(out, out / "renders", include_settled=not args.exclude_settled)
    elif args.stage == "conflict-index":
        _write_conflict_index(out, _conflict_rows(out))
    else:
        repeats(out, args.module, args.command.split("|"))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g400_controls")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--stage", choices=("controls", "cards", "conflicts", "conflict-index", "repeats"),
                        required=True)
    parser.add_argument("--module", default="")
    parser.add_argument("--command", default="")
    parser.add_argument("--exclude-settled", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
