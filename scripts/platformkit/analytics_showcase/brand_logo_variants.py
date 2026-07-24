"""Brand logo variant generator -- de-checkerboards the CourtVision mark and
composites clean brand assets (on-dark, on-light, app-icon squares, favicons,
mono tints).

The source PNG's "transparent background" is actually a flattened checkerboard
transparency-indicator baked into opaque pixels (alpha channel is 255
everywhere) -- a common editor-export bug, made worse here by a slightly
non-square resize (the checker cells are ~18.0px wide but ~18.5px tall, so a
single fixed grid position drifts out of phase within a few hundred pixels
and a position-based match goes wrong far from wherever it was calibrated).

Instead of tracking the checker's exact phase, this keys background by a
local-texture test: split each small tile's pixel values at their biggest
gap -- a flat checkerboard tile (even shadow-darkened) is always two tight
clusters, while the mark's brushed-metal texture is a continuous spread with
no such gap. That test is invariant to the grid's exact position and scale,
which is what makes it work here.

Not a stats module: no edge_claimed numeric claim, just an asset build + a
provenance report (out/brand_logo_variants.json) recording what was detected
and produced.

Usage:
    python -m scripts.platformkit.analytics_showcase.brand_logo_variants
    python -m scripts.platformkit.analytics_showcase.brand_logo_variants --check
"""
import argparse
import json
import os

import numpy as np
from PIL import Image, ImageDraw

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BRAND_DIR = os.path.join(REPO_ROOT, "webapp", "public", "brand")
SRC_PNG = os.path.join(BRAND_DIR, "courtvision-logo.png")
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "brand_logo_variants.json")

DARK_BG = (11, 14, 19)      # #0B0E13 -- flatters the silver ring + amber glow
LIGHT_BG = (248, 249, 250)  # #F8F9FA -- clean near-white

TILE = 22       # >= the ~18px checker cell, so every tile straddles a transition
GAP_T = 9.0     # min sorted-value jump that counts as "two flat clusters"
CLUSTER_STD_T = 6.5   # each cluster must be this flat (checker, not gradient)
TILE_SAT_T = 20.0     # low color saturation only (excludes the amber accent)
TRIM_DENSITY = 5      # ignore rows/cols with fewer opaque px than this when computing
# the trim bbox, so a handful of stray un-keyed background pixels near the
# canvas edge don't pin the crop to the full canvas.
# ponytail: a residual speckle of un-keyed tiles (and blocky ~22px edges) can
# remain near the silhouette -- cleaned up below, not chased to pixel-perfect;
# a full alpha-matting solve is over-engineering for a one-off logo cleanup.


def _bimodal_bg_mask(arr):
    """Classify TILExTILE tiles as background via the two-flat-clusters test,
    then fold in any tile that's surrounded by confirmed-background tiles
    (mops up isolated leftover speckle without ever touching the mark, whose
    tiles come in large contiguous runs, not isolated singletons)."""
    h, w = arr.shape[:2]
    gray = arr.mean(axis=2)
    sat = arr.max(axis=2) - arr.min(axis=2)
    ny, nx = -(-h // TILE), -(-w // TILE)
    tile_bg = np.zeros((ny, nx), dtype=bool)
    for by in range(ny):
        y0, y1 = by * TILE, min((by + 1) * TILE, h)
        for bx in range(nx):
            x0, x1 = bx * TILE, min((bx + 1) * TILE, w)
            vals = np.sort(gray[y0:y1, x0:x1].reshape(-1))
            gaps = np.diff(vals)
            if len(gaps) == 0:
                continue
            gi = int(gaps.argmax())
            lo, hi = vals[:gi + 1], vals[gi + 1:]
            if (gaps[gi] > GAP_T and lo.std() < CLUSTER_STD_T and hi.std() < CLUSTER_STD_T
                    and sat[y0:y1, x0:x1].mean() < TILE_SAT_T):
                tile_bg[by, bx] = True

    for _ in range(2):
        neighbor_bg = np.zeros((ny, nx), dtype=int)
        neighbor_bg[:-1] += tile_bg[1:]
        neighbor_bg[1:] += tile_bg[:-1]
        neighbor_bg[:, :-1] += tile_bg[:, 1:]
        neighbor_bg[:, 1:] += tile_bg[:, :-1]
        tile_bg = tile_bg | (neighbor_bg >= 3)

    is_bg = np.zeros((h, w), dtype=bool)
    for by in range(ny):
        if not tile_bg[by].any():
            continue
        y0, y1 = by * TILE, min((by + 1) * TILE, h)
        for bx in range(nx):
            if tile_bg[by, bx]:
                x0, x1 = bx * TILE, min((bx + 1) * TILE, w)
                is_bg[y0:y1, x0:x1] = True
    return is_bg


def _key_out_background(im_rgb):
    """Return an RGBA array with checkerboard pixels set to alpha=0."""
    arr = np.array(im_rgb).astype(int)
    is_bg = _bimodal_bg_mask(arr)
    alpha = np.where(is_bg, 0, 255).astype(np.uint8)
    rgba = np.dstack([arr.astype(np.uint8), alpha])
    info = {"tile_px": TILE, "gap_threshold": GAP_T, "bg_frac": round(float(is_bg.mean()), 4)}
    return rgba, info


def _density_bbox(alpha, min_count):
    """Bbox of rows/cols with more than min_count opaque px -- ignores a few
    stray un-keyed shadow pixels near the canvas edge that would otherwise
    pin the raw alpha bbox to the full canvas."""
    opaque = alpha > 0
    rows = np.where(opaque.sum(axis=1) > min_count)[0]
    cols = np.where(opaque.sum(axis=0) > min_count)[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    return int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1


def load_mark():
    """Load the source PNG, key out the baked checkerboard, trim to content bbox."""
    src = Image.open(SRC_PNG).convert("RGB")
    rgba, checker_info = _key_out_background(src)
    mark = Image.fromarray(rgba, mode="RGBA")
    bbox = _density_bbox(rgba[..., 3], TRIM_DENSITY)
    if bbox:
        mark = mark.crop(bbox)
    return mark, checker_info


def _palette_report(mark):
    """Dominant colors among opaque pixels, split into low-saturation ('metal')
    and high-saturation ('accent') clusters."""
    arr = np.array(mark)
    opaque = arr[arr[..., 3] > 128][:, :3].astype(int)
    maxc, minc = opaque.max(axis=1), opaque.min(axis=1)
    sat = maxc - minc
    metal = opaque[sat <= 30]
    accent = opaque[sat > 30]
    report = {
        "n_opaque_px": int(len(opaque)),
        "metal_mean_rgb": [round(x, 1) for x in metal.mean(axis=0)] if len(metal) else None,
        "accent_mean_rgb": [round(x, 1) for x in accent.mean(axis=0)] if len(accent) else None,
        "accent_px_frac": round(len(accent) / max(len(opaque), 1), 4),
    }
    return report


def _composite_flat(mark, bg_rgb, pad_frac=0.10):
    w, h = mark.size
    pad = int(max(w, h) * pad_frac)
    canvas = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), bg_rgb + (255,))
    canvas.alpha_composite(mark, (pad, pad))
    return canvas.convert("RGB")


def _square_icon(mark, bg_rgb, size=1024, radius_frac=0.22, mark_frac=0.74):
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * radius_frac), fill=bg_rgb + (255,))
    target = int(size * mark_frac)
    w, h = mark.size
    scale = target / max(w, h)
    resized = mark.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    rw, rh = resized.size
    canvas.alpha_composite(resized, ((size - rw) // 2, (size - rh) // 2))
    return canvas


def _mono_tint(mark, rgb):
    alpha = mark.split()[-1]
    solid = Image.new("RGBA", mark.size, rgb + (0,))
    solid.putalpha(alpha)
    return solid


def build():
    os.makedirs(BRAND_DIR, exist_ok=True)
    mark, checker_info = load_mark()

    outputs = {}

    on_dark = _composite_flat(mark, DARK_BG)
    on_dark.save(os.path.join(BRAND_DIR, "logo-on-dark.png"))
    outputs["logo-on-dark.png"] = on_dark.size

    on_light = _composite_flat(mark, LIGHT_BG)
    on_light.save(os.path.join(BRAND_DIR, "logo-on-light.png"))
    outputs["logo-on-light.png"] = on_light.size

    sq_dark = _square_icon(mark, DARK_BG)
    sq_dark.save(os.path.join(BRAND_DIR, "logo-square-dark.png"))
    outputs["logo-square-dark.png"] = sq_dark.size

    sq_light = _square_icon(mark, LIGHT_BG)
    sq_light.save(os.path.join(BRAND_DIR, "logo-square-light.png"))
    outputs["logo-square-light.png"] = sq_light.size

    for sz in (192, 512):
        fav = sq_dark.resize((sz, sz), Image.LANCZOS)
        name = f"favicon-{sz}.png"
        fav.save(os.path.join(BRAND_DIR, name))
        outputs[name] = fav.size

    mono_white = _mono_tint(mark, (255, 255, 255))
    mono_white.save(os.path.join(BRAND_DIR, "logo-mono-white.png"))
    outputs["logo-mono-white.png"] = mono_white.size

    mono_dark = _mono_tint(mark, DARK_BG)
    mono_dark.save(os.path.join(BRAND_DIR, "logo-mono-dark.png"))
    outputs["logo-mono-dark.png"] = mono_dark.size

    result = {
        "edge_claimed": False,
        "method": "tile-local bimodal-cluster background key (see module docstring), trim, composite",
        "source": os.path.relpath(SRC_PNG, REPO_ROOT).replace("\\", "/"),
        "checkerboard_detected": checker_info,
        "mark_trimmed_size": list(mark.size),
        "palette": _palette_report(mark),
        "bg_colors": {"dark": DARK_BG, "light": LIGHT_BG},
        "outputs": {k: list(v) for k, v in outputs.items()},
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def check():
    for name in ("logo-on-dark.png", "logo-on-light.png", "logo-square-dark.png",
                 "logo-square-light.png", "favicon-192.png", "favicon-512.png",
                 "logo-mono-white.png", "logo-mono-dark.png"):
        p = os.path.join(BRAND_DIR, name)
        assert os.path.exists(p), f"missing output: {p}"
        im = Image.open(p)
        if "A" in im.mode:
            extrema = im.split()[-1].getextrema()
            assert extrema != (0, 0), f"{name}: fully-transparent background"
    assert os.path.exists(OUT_JSON), f"missing {OUT_JSON}"
    report = json.loads(open(OUT_JSON, encoding="utf-8").read())
    assert report["edge_claimed"] is False
    assert len(report["outputs"]) == 8
    print(f"PASS: brand_logo_variants -- 8/8 outputs present, none fully-transparent "
          f"(bg_frac={report['checkerboard_detected']['bg_frac']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        res = build()
        print(json.dumps({"palette": res["palette"], "mark_trimmed_size": res["mark_trimmed_size"],
                           "outputs": list(res["outputs"].keys())}, indent=2))
