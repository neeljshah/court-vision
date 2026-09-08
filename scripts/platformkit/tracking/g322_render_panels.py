"""G322 -- headless panel + contact-sheet renderer for the sealed 20-box eye check.

Prereg: docs/evidence/tracking/g322_prereg_attempt2_2026-09-07.md sections 5 and 6.
Each panel draws TWO rectangles on the same extracted frame:
  SOLID GREEN  = the post-TOPCUT reading, y + 60 (the sealed default; TOPCUT=60,
                 src/tracking/video_handler.py:11, src/pipeline/unified_pipeline.py:1689)
  THIN RED     = the no-offset reading, the sealed fallback of prereg section 6
so the rendering assumption is visible in the panel instead of being asserted.
Headless PIL only -- never cv2.imshow.

Usage:
  python scripts/platformkit/tracking/g322_render_panels.py \
      --panels <panels.csv> --frames <dir> --out <dir> --sheets <dir> [--tag 2026-09-07]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import sys

from PIL import Image, ImageDraw, ImageFont

TOPCUT = 60
FULL_W = 620          # width of the whole-frame half of a panel
CROP_W = 300          # width of the zoom half
BAR_H = 26
SHEET_COLS = 1
PANELS_PER_SHEET = 10


def _font():
    try:
        return ImageFont.truetype("arial.ttf", 14)
    except Exception:
        return ImageFont.load_default()


def _rect(dr, box, colour, width):
    x1, y1, x2, y2 = box
    dr.rectangle([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)],
                 outline=colour, width=width)


def render_panel(frame_path, row, font):
    """One panel: whole frame with both readings drawn, plus a zoom of the offset reading."""
    img = Image.open(frame_path).convert("RGB")
    W, H = img.size
    x1, y1 = float(row["bbox_x1"]), float(row["bbox_y1"])
    x2, y2 = float(row["bbox_x2"]), float(row["bbox_y2"])
    off = (x1, y1 + TOPCUT, x2, y2 + TOPCUT)

    full = img.copy()
    dr = ImageDraw.Draw(full)
    _rect(dr, (x1, y1, x2, y2), (220, 40, 40), max(1, W // 640))          # no-offset
    _rect(dr, off, (40, 230, 60), max(2, W // 400))                        # post-TOPCUT
    fh = max(1, int(FULL_W * H / W))
    full = full.resize((FULL_W, fh))

    cx1, cy1 = max(0, int(min(off[0], off[2]))), max(0, int(min(off[1], off[3])))
    cx2, cy2 = min(W, int(max(off[0], off[2]))), min(H, int(max(off[1], off[3])))
    if cx2 - cx1 < 4 or cy2 - cy1 < 4:
        crop = Image.new("RGB", (CROP_W, fh), (30, 30, 30))
    else:
        c = img.crop((cx1, cy1, cx2, cy2))
        ch = max(1, int(CROP_W * c.size[1] / c.size[0]))
        crop = c.resize((CROP_W, min(ch, fh)))

    panel = Image.new("RGB", (FULL_W + CROP_W + 8, fh + BAR_H), (16, 16, 16))
    panel.paste(full, (0, BAR_H))
    panel.paste(crop, (FULL_W + 8, BAR_H))
    cap = ("%s f=%s pid=%s rank=%s/%s box_h=%.0f frame_h=%.0f ratio=%.3f"
           % (row["game_id"], row["frame"], row["player_id"], row["rank"],
              row["n_candidates"], float(row["box_h"]), float(row["frame_h"]),
              float(row["ratio"])))
    ImageDraw.Draw(panel).text((4, 5), cap, fill=(240, 240, 240), font=font)
    return panel


def contact_sheet(panels, width_cap=900, quality=55):
    """Stack panels vertically into one sheet, scaled to width_cap."""
    scaled = []
    for p in panels:
        h = max(1, int(width_cap * p.size[1] / p.size[0]))
        scaled.append(p.resize((width_cap, h)))
    sheet = Image.new("RGB", (width_cap, sum(p.size[1] for p in scaled)), (16, 16, 16))
    y = 0
    for p in scaled:
        sheet.paste(p, (0, y))
        y += p.size[1]
    return sheet, quality


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--panels", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sheets", required=True)
    ap.add_argument("--tag", default="2026-09-07")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.sheets, exist_ok=True)
    font = _font()

    rows = list(csv.DictReader(open(a.panels, newline="", encoding="ascii")))
    by_game = {}
    for r in rows:
        by_game.setdefault(r["game_id"], []).append(r)

    panels, manifest = [], []
    for gid in dict.fromkeys(r["game_id"] for r in rows):
        grp = by_game[gid]
        order = sorted(range(len(grp)), key=lambda i: int(grp[i]["frame"]))
        # ffmpeg wrote _01.._05 in ascending frame order for each game
        for slot, idx in enumerate(order, start=1):
            grp[idx]["_png"] = os.path.join(a.frames, "%s_%02d.png" % (gid, slot))
        for i, r in enumerate(grp, start=1):
            p = render_panel(r["_png"], r, font)
            name = "g322_panel_%s_%s_%02d.jpg" % (a.tag, gid, i)
            path = os.path.join(a.out, name)
            p.save(path, "JPEG", quality=80)
            manifest.append((hashlib.sha256(open(path, "rb").read()).hexdigest(), name))
            panels.append(p)

    for s in range(0, len(panels), PANELS_PER_SHEET):
        sheet, q = contact_sheet(panels[s:s + PANELS_PER_SHEET])
        out = os.path.join(a.sheets, "g322_sheet_%s_%d.jpg" % (a.tag, s // PANELS_PER_SHEET + 1))
        sheet.save(out, "JPEG", quality=q, optimize=True)
        while os.path.getsize(out) > 500 * 1024 and q > 20:
            q -= 8
            sheet.save(out, "JPEG", quality=q, optimize=True)
        print("%s %d B q=%d" % (out, os.path.getsize(out), q))

    mpath = os.path.join(a.sheets, "g322_panel_manifest_%s.txt" % a.tag)
    with open(mpath, "w", encoding="ascii", newline="\n") as fh:
        for h, n in manifest:
            fh.write("%s  %s\n" % (h, n))
    print("panels: %d  manifest: %s" % (len(panels), mpath))
    return 0


if __name__ == "__main__":
    sys.exit(main())
