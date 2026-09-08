"""G315 -- HEADLESS panel + contact-sheet renderer for the same-id step screen.

Never `cv2.imshow`; PIL only, writes files. One PANEL per candidate step: frame A and
frame B side by side with that frame's own box drawn, a zoom crop of each box beneath, and
the player_id / frame indices / gap / normalised step printed on it. One CONTACT SHEET per
game stacks that game's panels.

Frames must already be extracted (read-only) from the pod source video; `--frames <dir>`
holds `<game_id>/f%03d.jpg` in ASCENDING frame order plus `frames_<game_id>.txt` listing
those frame indices, one per line, in the same order.

  python -m scripts.platformkit.tracking.g315_render_panels \
      --examples <examples.csv> --frames <dir> --panels <dir> --sheets <dir>
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

from PIL import Image, ImageDraw

FRAME_W = 760          # each full frame in the top row
CROP_H = 420           # each zoom crop in the bottom row
CAPTION_H = 46
CROP_MARGIN = 0.6      # box expanded by 60 pct before cropping
COL_A = (0, 220, 60)   # frame A box
COL_B = (255, 70, 40)  # frame B box
SHEET_W = 820          # contact-sheet width; panels are downscaled into it (2 MB commit budget)
SHEET_QUALITY = 46


def load_frame_index(frames_dir, game_id):
    """{frame_number: path}. The extractor emits f001.jpg.. in ascending frame order."""
    listing = os.path.join(frames_dir, "frames_%s.txt" % game_id)
    with open(listing, "r", encoding="ascii") as fh:
        nums = [int(x) for x in fh if x.strip()]
    gdir = os.path.join(frames_dir, game_id)
    files = sorted(f for f in os.listdir(gdir) if f.endswith(".jpg"))
    if len(files) != len(nums):
        raise SystemExit("%s: %d frames extracted, %d requested -- refusing to guess"
                         % (game_id, len(files), len(nums)))
    return {n: os.path.join(gdir, f) for n, f in zip(nums, files)}


def crop_box(img, box, cell_w, cell_h):
    """Zoom crop around box, expanded by CROP_MARGIN, letterboxed into cell_w x cell_h."""
    x1, y1, x2, y2 = box
    w, h = max(2.0, x2 - x1), max(2.0, y2 - y1)
    mx, my = w * CROP_MARGIN, h * CROP_MARGIN
    b = (max(0, int(x1 - mx)), max(0, int(y1 - my)),
         min(img.width, int(x2 + mx)), min(img.height, int(y2 + my)))
    if b[2] - b[0] < 4 or b[3] - b[1] < 4:
        return Image.new("RGB", (cell_w, cell_h), (24, 24, 24))
    sub = img.crop(b)
    scale = min(cell_w / sub.width, cell_h / sub.height)
    sub = sub.resize((max(1, int(sub.width * scale)), max(1, int(sub.height * scale))),
                     Image.LANCZOS)
    cell = Image.new("RGB", (cell_w, cell_h), (24, 24, 24))
    cell.paste(sub, ((cell_w - sub.width) // 2, (cell_h - sub.height) // 2))
    return cell


def half(path, box, colour, label):
    """One side of a panel: the full frame with its box, above a zoom crop of that box."""
    img = Image.open(path).convert("RGB")
    scale = FRAME_W / img.width
    top = img.resize((FRAME_W, max(1, int(img.height * scale))), Image.LANCZOS)
    d = ImageDraw.Draw(top)
    sb = tuple(v * scale for v in box)
    d.rectangle([sb[0], sb[1], sb[2], sb[3]], outline=colour, width=3)
    d.ellipse([(sb[0] + sb[2]) / 2 - 4, sb[3] - 4, (sb[0] + sb[2]) / 2 + 4, sb[3] + 4],
              fill=colour)
    d.text((6, 6), label, fill=colour)
    bottom = crop_box(img, box, FRAME_W, CROP_H)
    ImageDraw.Draw(bottom).text((6, 6), label + " (zoom)", fill=colour)
    out = Image.new("RGB", (FRAME_W, top.height + CROP_H), (16, 16, 16))
    out.paste(top, (0, 0))
    out.paste(bottom, (0, top.height))
    return out


def render_panel(row, frame_paths, out_path):
    """One candidate step -> one panel image. Returns the panel size."""
    box_a = tuple(float(row[k]) for k in ("ax1", "ay1", "ax2", "ay2"))
    box_b = tuple(float(row[k]) for k in ("bx1", "by1", "bx2", "by2"))
    fa, fb = int(row["frame_a"]), int(row["frame_b"])
    left = half(frame_paths[fa], box_a, COL_A, "A  frame %d" % fa)
    right = half(frame_paths[fb], box_b, COL_B, "B  frame %d" % fb)
    panel = Image.new("RGB", (left.width + right.width, left.height + CAPTION_H),
                      (16, 16, 16))
    panel.paste(left, (0, CAPTION_H))
    panel.paste(right, (left.width, CAPTION_H))
    cap = ("%s | player_id %s | frame %d -> %d | gap %s (%s) | step %.4f of frame height "
           "| candidate rank %s of %s"
           % (row["panel_id"], row["player_id"], fa, fb, row["gap"], row["gap_bin"],
              float(row["step_norm"]), row["cand_rank"], row["n_candidates"]))
    ImageDraw.Draw(panel).text((8, 16), cap, fill=(235, 235, 235))
    panel.save(out_path, "JPEG", quality=88)
    return panel.size


def contact_sheet(panel_paths, out_path):
    """Stack a game's panels into one sheet, downscaled to SHEET_W."""
    imgs = []
    for p in panel_paths:
        im = Image.open(p).convert("RGB")
        s = SHEET_W / im.width
        imgs.append(im.resize((SHEET_W, max(1, int(im.height * s))), Image.LANCZOS))
    sheet = Image.new("RGB", (SHEET_W, sum(i.height + 4 for i in imgs)), (16, 16, 16))
    y = 0
    for im in imgs:
        sheet.paste(im, (0, y))
        y += im.height + 4
    sheet.save(out_path, "JPEG", quality=SHEET_QUALITY, optimize=True)
    return sheet.size, os.path.getsize(out_path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="G315 headless panel renderer")
    ap.add_argument("--examples", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument("--panels", required=True)
    ap.add_argument("--sheets", required=True)
    args = ap.parse_args(argv)

    os.makedirs(args.panels, exist_ok=True)
    os.makedirs(args.sheets, exist_ok=True)
    with open(args.examples, "r", encoding="ascii", newline="") as fh:
        rows = list(csv.DictReader(fh))

    by_game, index = {}, {}
    for r in rows:
        by_game.setdefault(r["game_id"], []).append(r)
    total = 0
    for game, grows in sorted(by_game.items()):
        index[game] = load_frame_index(args.frames, game)
        paths = []
        for r in grows:
            p = os.path.join(args.panels, "%s.jpg" % r["panel_id"])
            size = render_panel(r, index[game], p)
            paths.append(p)
            total += 1
            print("PANEL %s %dx%d %d bytes" % (r["panel_id"], size[0], size[1],
                                               os.path.getsize(p)))
        sp = os.path.join(args.sheets, "g315_sheet_%s.jpg" % game)
        (w, h), nbytes = contact_sheet(paths, sp)
        print("SHEET %s %dx%d %d bytes (%d panels)" % (sp, w, h, nbytes, len(paths)))
    print("TOTAL %d panels" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
