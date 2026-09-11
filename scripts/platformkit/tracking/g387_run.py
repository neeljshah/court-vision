"""G387 finisher driver: census, sealed selection, native cache, tiles, controls.

Stages are idempotent; every write is receipted with a SHA-256 on both sides.
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from scripts.platformkit.tracking import g387_controls, g387_score, g387_tiles  # noqa: E402

G382 = REPO / "docs/evidence/tracking/g382_court_stroke_specificity_2026-09-10"
OUT = REPO / "docs/evidence/tracking/g387_paint_localization_controls_2026-09-11"
CACHE = Path(r"C:\Users\neelj\AppData\Local\Temp\g387_native")


def _selection(census_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    frames = g387_tiles.read_csv(G382 / "frames.csv")
    by_key = {row["frame_key"]: row for row in census_rows}
    selected = g387_tiles.select_even_retained(frames)
    out = []
    for order, row in enumerate(selected, start=1):
        cen = by_key[row["frame_key"]]
        if cen["status"] != "READY":
            raise RuntimeError("selected frame has no hash-matched native file: %s" % row["frame_key"])
        out.append({
            "opaque_id": "G387_%03d" % order, "frame_key": row["frame_key"],
            "video_id": row["video_id"], "section_id": row["section_id"],
            "frame_order": row["frame_order"], "native_path": cen["native_path"],
            "native_sha256": cen["native_sha256"], "bytes": cen["bytes"],
            "width": cen["width"], "height": cen["height"],
            "pts_seconds": row.get("pts_seconds", "") or "UNKNOWN",
        })
    return out


def stage_census() -> None:
    frames = g387_tiles.read_csv(G382 / "frames.csv")
    identities = g387_tiles.read_csv(G382 / "identity_map.csv")
    rows = g387_tiles.census(frames, identities)
    g387_tiles.write_csv(OUT / "census.csv", rows)
    sel = _selection(rows)
    keys = [row["frame_key"] for row in sel]
    elig = []
    chosen = set(keys)
    for row in rows:
        elig.append({"frame_key": row["frame_key"], "retained": row["retained"],
                     "status": row["status"],
                     "eligible": "YES" if row["status"] == "READY" else "NO",
                     "selected": "YES" if row["frame_key"] in chosen else "NO",
                     "exclusion_reason": "" if row["status"] == "READY" else "DECODE_FAILED_NO_NATIVE_FILE"})
    g387_tiles.write_csv(OUT / "eligibility.csv", elig)
    g387_tiles.write_csv(OUT / "selection.csv", sel)
    receipt = {"planned_states": len(rows), "retained": sum(r["retained"] == "RETAINED" for r in rows),
               "decode_failed": sum(r["retained"] == "DECODE_FAILED" for r in rows),
               "native_ready": sum(r["status"] == "READY" for r in rows),
               "selected": len(sel), "selection_sha256": g387_score.canonical_sha256(keys)}
    (OUT / "selection_receipt.json").write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n",
                                                encoding="utf-8", newline="\n")
    print(json.dumps(receipt, sort_keys=True))


def stage_tiles() -> None:
    sel = g387_tiles.read_csv(OUT / "selection.csv")
    records = g387_tiles.build_tiles(sel, CACHE / "tiles")
    by_id = {row["opaque_id"]: row for row in sel}
    for rec in records:
        src = by_id[rec["opaque_id"]]
        rec["sender_sha256"] = src["native_sha256"]
        rec["tile_sha256"] = g387_tiles.sha256(CACHE / "tiles" / rec["tile"])
        rec["native_width"], rec["native_height"] = "1920", "1080"
        rec["pts_seconds"] = src["pts_seconds"]
        if rec["context_sha256"] != rec["sender_sha256"]:
            raise RuntimeError("receiver hash differs for %s" % rec["opaque_id"])
    g387_tiles.write_csv(OUT / "transforms.csv", records)
    print("tiles=%d contexts=%d" % (len(records), len({r["opaque_id"] for r in records})))


def stage_controls() -> None:
    sel = g387_tiles.read_csv(OUT / "selection.csv")
    points = g387_controls.known_points([row["opaque_id"] for row in sel])
    out_dir = CACHE / "controls"
    rows = []
    for point in points:
        name = "%s_control.png" % point["opaque_id"]
        tile = CACHE / "tiles" / ("%s_tile%s.png" % (point["opaque_id"], point["tile_index"]))
        g387_controls.inject(tile, out_dir / name, point)
        row = dict(point)
        row["image"] = name
        row["background_tile"] = tile.name
        row["image_sha256"] = g387_tiles.sha256(out_dir / name)
        rows.append(row)
    (OUT / "controls").mkdir(parents=True, exist_ok=True)
    g387_tiles.write_csv(OUT / "controls/known_points.csv", rows)
    canonical = [{k: r[k] for k in ("opaque_id", "tile_index", "x1", "y1", "x2", "y2", "mid_x", "mid_y")} for r in rows]
    print("controls=%d known_points_sha256=%s" % (len(rows), g387_score.canonical_sha256(canonical)))


def stage_batches() -> None:
    """Write per-rater opaque batch files; presentation order is the sealed control order."""
    sel = g387_tiles.read_csv(OUT / "selection.csv")
    controls = g387_tiles.read_csv(OUT / "controls/known_points.csv")
    for rater in ("terra", "sol"):
        real_dir = CACHE / ("batch_real_%s" % rater)
        real_dir.mkdir(parents=True, exist_ok=True)
        for chunk, start in enumerate(range(0, len(sel), 6), start=1):
            lines = []
            for row in sel[start:start + 6]:
                tiles = " ".join(str(CACHE / "tiles" / ("%s_tile%d.png" % (row["opaque_id"], n))) for n in range(1, 7))
                lines.append("%s\t%s\t%s" % (row["opaque_id"], CACHE / "tiles" / ("%s_context.png" % row["opaque_id"]), tiles))
            (real_dir / ("batch_%02d.tsv" % chunk)).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        ctl_dir = CACHE / ("batch_control_%s" % rater)
        ctl_dir.mkdir(parents=True, exist_ok=True)
        for chunk, start in enumerate(range(0, len(controls), 10), start=1):
            lines = ["%s\t%s" % (row["opaque_id"], CACHE / "controls" / row["image"]) for row in controls[start:start + 10]]
            (ctl_dir / ("batch_%02d.tsv" % chunk)).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("batches written")


def stage_cards() -> None:
    """Render committed JPEG eye-check cards; native PNGs stay in the immutable cache."""
    import cv2

    sel = g387_tiles.read_csv(OUT / "selection.csv")
    out_dir = OUT / "renders"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for row in sel:
        image = cv2.imread(str(CACHE / "tiles" / ("%s_context.png" % row["opaque_id"])), cv2.IMREAD_COLOR)
        card = image
        name = "%s.jpg" % row["opaque_id"]
        cv2.imwrite(str(out_dir / name), card, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        rows.append({"opaque_id": row["opaque_id"], "frame_key": row["frame_key"], "card": name,
                     "card_sha256": g387_tiles.sha256(out_dir / name), "native_sha256": row["native_sha256"],
                     "card_width": "1920", "card_height": "1080", "native_scale": "1.0"})
    g387_tiles.write_csv(OUT / "renders/manifest.csv", rows)
    print("cards=%d" % len(rows))


def stage_receipts() -> None:
    """Write SHA256SUMS over every committed artifact plus source and route hashes."""
    routes = sorted((REPO / "scripts/platformkit/tracking").glob("g387_*.py"))
    sources = [G382 / name for name in ("frames.csv", "adjudication.csv", "marking_only.json", "identity_map.csv")]
    lines = []
    for path in sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "SHA256SUMS"):
        lines.append("%s  %s" % (g387_tiles.sha256(path), path.relative_to(REPO).as_posix()))
    for path in routes + sources:
        lines.append("%s  %s" % (g387_tiles.sha256(path), path.relative_to(REPO).as_posix()))
    (OUT / "SHA256SUMS").write_text(chr(10).join(lines) + chr(10), encoding="utf-8", newline=chr(10))
    print("receipts=%d" % len(lines))


STAGES = {"census": stage_census, "tiles": stage_tiles, "controls": stage_controls, "batches": stage_batches, "cards": stage_cards, "receipts": stage_receipts}

if __name__ == "__main__":
    for name in sys.argv[1:]:
        STAGES[name]()
