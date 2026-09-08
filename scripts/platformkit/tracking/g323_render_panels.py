"""G323 -- headless panel + contact-sheet renderer for the sealed 60-box blind rating.

Prereg: docs/evidence/tracking/g323_prereg_2026-09-07.md section 5. Each panel is a context tile
(the whole frame, both readings drawn) beside a crop of the box, captioned with the OPAQUE panel id
and nothing else -- no game, no frame, no ratio, no region, no tercile, no player id -- so neither
rater can infer a stratum from the sheet.

  SOLID GREEN = the post-TOPCUT reading, y + 60 (TOPCUT, src/tracking/video_handler.py:11)
  THIN RED    = the no-offset reading
Headless PIL only -- never cv2.imshow.

Usage:
  python scripts/platformkit/tracking/g323_render_panels.py \
      --sample <sample.csv> --frames <dir> --maps <dir> --out <panel dir> --sheets <sheet dir>
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import os
import sys

from PIL import Image, ImageDraw, ImageFont

TOPCUT = 60
CTX_W = 340           # width of the context tile
CROP_W = 190          # width of the crop
BAR_H = 20
GAP = 6
SHEET_COLS = 3
PANELS_PER_SHEET = 15
MAX_SHEET_BYTES = 500 * 1024
QUALITIES = (78, 70, 62, 54, 46, 38)


def _font():
    try:
        return ImageFont.truetype("arial.ttf", 15)
    except Exception:
        return ImageFont.load_default()


def _rect(dr, box, colour, width):
    x1, y1, x2, y2 = box
    dr.rectangle([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)],
                 outline=colour, width=width)


def frame_index(maps_dir):
    """(game_id, frame) -> extracted jpg basename, from the per-game extraction maps."""
    idx = {}
    for path in glob.glob(os.path.join(maps_dir, "map_*.txt")):
        game = os.path.basename(path)[4:-4]
        with open(path) as fh:
            for line in fh:
                name, frame = line.split()
                idx[(game, int(frame))] = name
    return idx


def render_panel(frame_path, row, font):
    """One panel: context tile with both readings drawn, plus a crop of the post-TOPCUT reading."""
    img = Image.open(frame_path).convert("RGB")
    W, H = img.size
    x1, y1 = float(row["bbox_x1"]), float(row["bbox_y1"])
    x2, y2 = float(row["bbox_x2"]), float(row["bbox_y2"])
    off = (x1, y1 + TOPCUT, x2, y2 + TOPCUT)

    ctx = img.copy()
    dr = ImageDraw.Draw(ctx)
    _rect(dr, (x1, y1, x2, y2), (220, 40, 40), max(1, W // 640))
    _rect(dr, off, (40, 230, 60), max(2, W // 380))
    ch = max(1, int(CTX_W * H / W))
    ctx = ctx.resize((CTX_W, ch))

    cx1, cy1 = max(0, int(min(off[0], off[2]))), max(0, int(min(off[1], off[3])))
    cx2, cy2 = min(W, int(max(off[0], off[2]))), min(H, int(max(off[1], off[3])))
    if cx2 - cx1 < 4 or cy2 - cy1 < 4:
        crop = Image.new("RGB", (CROP_W, ch), (30, 30, 30))
    else:
        c = img.crop((cx1, cy1, cx2, cy2))
        nh = max(1, int(CROP_W * c.size[1] / c.size[0]))
        if nh > ch:
            nw = max(1, int(CROP_W * ch / nh))
            crop = c.resize((nw, ch))
        else:
            crop = c.resize((CROP_W, nh))

    panel = Image.new("RGB", (CTX_W + GAP + CROP_W, ch + BAR_H), (16, 16, 16))
    panel.paste(ctx, (0, BAR_H))
    panel.paste(crop, (CTX_W + GAP, BAR_H))
    ImageDraw.Draw(panel).text((4, 3), row["panel_id"], fill=(245, 245, 245), font=font)
    return panel


def save_sheet(panels, path):
    """Grid the panels and shrink JPEG quality until the sheet fits MAX_SHEET_BYTES."""
    cw = max(p.size[0] for p in panels)
    rh = max(p.size[1] for p in panels)
    rows = (len(panels) + SHEET_COLS - 1) // SHEET_COLS
    sheet = Image.new("RGB", (SHEET_COLS * (cw + GAP), rows * (rh + GAP)), (8, 8, 8))
    for i, p in enumerate(panels):
        sheet.paste(p, ((i % SHEET_COLS) * (cw + GAP), (i // SHEET_COLS) * (rh + GAP)))
    for q in QUALITIES:
        sheet.save(path, "JPEG", quality=q, optimize=True)
        if os.path.getsize(path) <= MAX_SHEET_BYTES:
            return q, os.path.getsize(path)
    return QUALITIES[-1], os.path.getsize(path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--maps", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheets", required=True)
    a = ap.parse_args(argv)

    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.sheets, exist_ok=True)
    idx = frame_index(a.maps)
    font = _font()
    with open(a.sample, newline="") as fh:
        rows = list(csv.DictReader(fh))

    panels, manifest = [], []
    for row in rows:
        name = idx.get((row["game_id"], int(row["frame"])))
        if name is None:
            print("MISSING FRAME for %s (%s f=%s)" % (row["panel_id"], row["game_id"], row["frame"]))
            return 1
        p = render_panel(os.path.join(a.frames, name), row, font)
        out = os.path.join(a.out, row["panel_id"] + ".jpg")
        p.save(out, "JPEG", quality=92)
        manifest.append("%s  %s" % (
            hashlib.sha256(open(out, "rb").read()).hexdigest(), row["panel_id"] + ".jpg"))
        panels.append(p)

    n_sheets = 0
    for i in range(0, len(panels), PANELS_PER_SHEET):
        n_sheets += 1
        path = os.path.join(a.sheets, "g323_sheet_%d.jpg" % n_sheets)
        q, size = save_sheet(panels[i:i + PANELS_PER_SHEET], path)
        print("sheet %d: %d panels, quality %d, %d bytes" % (n_sheets, len(panels[i:i + PANELS_PER_SHEET]), q, size))
    with open(os.path.join(a.sheets, "g323_panel_manifest_2026-09-07.txt"), "w", newline="\n") as fh:
        fh.write("\n".join(manifest) + "\n")
    print("panels %d, sheets %d" % (len(panels), n_sheets))
    return 0


if __name__ == "__main__":
    sys.exit(main())
