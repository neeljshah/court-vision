#!/usr/bin/env python3
"""fix_homography_offset.py — Empirical correction for the homography offset
that breaks paint-related CV features.

Background: `resources/Rectify1.npy` maps panorama → 2D court, but the output
coord system doesn't match the assumed NBA-standard (5.25 / 88.75 / 25 ft
basket centers in a 94×50 ft court). Verified on g279: `ft_y` median is 41.47
instead of 25, `dist_to_basket_ft` min is 8.73 instead of 0. See
[[Open Issues]] #13.

This script doesn't fix M1 itself. Instead it:
  1. Reads tracking_data.csv for a game.
  2. Estimates the two basket positions empirically from player density:
     - Left basket: high-density cluster in low-x half (ft_x < 47)
     - Right basket: high-density cluster in high-x half (ft_x >= 47)
  3. Writes corrected columns to a SIDE CSV (`tracking_data_corrected.csv`)
     with `dist_to_basket_ft_fixed`, `in_paint_fixed`, `basket_x_emp`,
     `basket_y_emp`, plus a `homography_corrected` boolean.
  4. Optionally regenerates the corrected per-player CV profile.

The original tracking_data.csv is NOT modified — corrections live in the
side file so downstream consumers can opt in.

Usage:
    python scripts/fix_homography_offset.py 0022500279
    python scripts/fix_homography_offset.py --all
    python scripts/fix_homography_offset.py --from-log
    python scripts/fix_homography_offset.py 0022500279 --visualize    # print landmark estimates
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

BACKUP = Path(r"C:\Users\neelj\nba-data-backup\tracking")
INGEST_LOG = BACKUP.parent / ".ingest_log.csv"

# NBA standard
COURT_LEN_FT  = 94.0
COURT_WID_FT  = 50.0
BASKET_X_L_FT = 5.25     # left basket x from baseline
BASKET_X_R_FT = 88.75    # right basket x from baseline
BASKET_Y_FT   = 25.0     # both baskets centered on width

# NBA paint (key) dimensions:
#   16 ft from baseline to free-throw line
#   12 ft wide (6 ft on either side of basket centerline)
# Paint extends FROM the basket DOWN the lane TOWARD the free-throw line.
# "In paint" means: closer to baseline than free-throw line AND inside the lane.
PAINT_LENGTH_FT = 16.0   # baseline → free-throw line; from basket: 16 - 4.75 = ~11 ft towards center court
PAINT_HALF_W_FT = 6.0    # half-width of lane (12 ft total)
PAINT_RADIUS_FT = 8.0    # also keep a circular threshold for "near basket" use


def _estimate_basket_positions(df: pd.DataFrame) -> Optional[dict]:
    """Estimate basket (x, y) in the recorded ft-coord system.

    Restricts the search to the END-ZONE strips along the long axis where
    baskets are actually located (x in [0, 15] for left, x in [79, 94] for
    right). Within each strip, finds the y-mode = where players cluster
    most along the width axis = basket y position.

    Returns dict with basket_l_*, basket_r_* + diagnostic homography_shift_y.
    """
    if "ft_x" not in df.columns or "ft_y" not in df.columns:
        return None

    ft_x = pd.to_numeric(df["ft_x"], errors="coerce")
    ft_y = pd.to_numeric(df["ft_y"], errors="coerce")
    mask = ft_x.notna() & ft_y.notna() & (ft_x.between(0, COURT_LEN_FT)) \
        & (ft_y.between(0, COURT_WID_FT))
    if mask.sum() < 1000:
        return None

    fx = ft_x[mask].to_numpy()
    fy = ft_y[mask].to_numpy()

    # End-zone strips: 0-15 ft from each baseline (the paint + restricted area
    # both fall in here). The basket is at x=5.25 from baseline, well inside
    # the 0-15 strip.
    L_END_MAX = 15.0
    R_END_MIN = COURT_LEN_FT - 15.0

    left_strip  = fx <= L_END_MAX
    right_strip = fx >= R_END_MIN

    if left_strip.sum() < 100 or right_strip.sum() < 100:
        # Strip-restricted search starved — try a wider strip
        L_END_MAX = 20.0
        R_END_MIN = COURT_LEN_FT - 20.0
        left_strip  = fx <= L_END_MAX
        right_strip = fx >= R_END_MIN

    def _strip_basket(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
        """Within a baseline strip, find the (x, y) where player density peaks.
        Y-mode is the most-trustworthy basket-y estimator (basket attracts
        cluster). X-mode within the strip is the basket-x estimator."""
        if len(x) < 100:
            return (np.nan, np.nan)
        # 1D mode on y (width axis) via histogram + smoothing
        y_bins = 30
        y_hist, y_edges = np.histogram(y, bins=y_bins, range=(0, COURT_WID_FT))
        try:
            from scipy.ndimage import uniform_filter1d
            y_hist_s = uniform_filter1d(y_hist.astype(float), size=3)
        except ImportError:
            y_hist_s = y_hist
        iy = int(np.argmax(y_hist_s))
        y_mode = (y_edges[iy] + y_edges[iy + 1]) / 2

        # 1D mode on x (length axis) within the strip
        x_bins = 20
        x_hist, x_edges = np.histogram(x, bins=x_bins,
                                        range=(x.min(), x.max()))
        try:
            from scipy.ndimage import uniform_filter1d
            x_hist_s = uniform_filter1d(x_hist.astype(float), size=3)
        except ImportError:
            x_hist_s = x_hist
        ix = int(np.argmax(x_hist_s))
        x_mode = (x_edges[ix] + x_edges[ix + 1]) / 2
        return float(x_mode), float(y_mode)

    bL_x, bL_y = _strip_basket(fx[left_strip], fy[left_strip])
    bR_x, bR_y = _strip_basket(fx[right_strip], fy[right_strip])

    if not (np.isfinite(bL_x) and np.isfinite(bR_x)):
        return None

    # Sanity: basket-y in both halves should be close (same midcourt width)
    if abs(bL_y - bR_y) > 8.0:
        avg_y = float(np.mean(fy))
        bL_y = bR_y = avg_y

    shift_y = float(np.mean([bL_y, bR_y]) - BASKET_Y_FT)

    return {
        "basket_l_x": round(bL_x, 2),
        "basket_l_y": round(bL_y, 2),
        "basket_r_x": round(bR_x, 2),
        "basket_r_y": round(bR_y, 2),
        "homography_shift_y": round(shift_y, 2),
        "n_samples": int(mask.sum()),
        "n_left_strip":  int(left_strip.sum()),
        "n_right_strip": int(right_strip.sum()),
    }


def fix_game(game_id: str, visualize: bool = False) -> dict:
    """Apply empirical basket fix to one game. Returns diagnostic dict.

    Strategy: derive a global y-axis shift so the median player ft_y aligns
    with court center (25 ft). Then use the STANDARD NBA basket positions
    in the corrected coord system. This is simpler than mode-finding and
    avoids the bias of "density mode = paint area not basket itself".
    """
    d = BACKUP / game_id
    td_path = d / "tracking_data.csv"
    if not td_path.exists():
        return {"game_id": game_id, "ok": False, "error": "tracking_data.csv missing"}

    df = pd.read_csv(td_path, low_memory=False)

    ft_x = pd.to_numeric(df["ft_x"], errors="coerce")
    ft_y = pd.to_numeric(df["ft_y"], errors="coerce")
    mask = ft_x.notna() & ft_y.notna() & ft_x.between(0, COURT_LEN_FT) \
        & ft_y.between(0, COURT_WID_FT)
    if mask.sum() < 1000:
        return {"game_id": game_id, "ok": False,
                "error": f"insufficient data ({mask.sum()} valid rows)"}

    # Global y-axis shift: align player median ft_y with court center (25 ft).
    # Player y-positions are symmetric around mid-court width over a full game
    # (offense + defense, both sides of paint), so median ft_y is the most
    # robust estimate of where y=25 actually lands in the raw coord system.
    median_y_raw = float(ft_y[mask].median())
    shift_y = median_y_raw - BASKET_Y_FT
    ft_y_corrected = ft_y - shift_y

    # X-axis: DON'T shift globally. Short clips often capture only one
    # half-court so median ft_x is biased. Instead, use empirical x-mode
    # from the basket density estimator (which finds per-half peaks).
    emp = _estimate_basket_positions(df)
    if emp is None:
        return {"game_id": game_id, "ok": False,
                "error": "basket position estimation failed"}

    # Empirical landmarks dict (for visualize/JSON output)
    landmarks = dict(emp)
    landmarks["median_ft_y_raw"] = round(median_y_raw, 2)
    landmarks["shift_y"]         = round(shift_y, 2)

    if visualize:
        print(f"\n=== [{game_id}] empirical landmarks + shifts ===")
        for k, v in landmarks.items():
            print(f"  {k}: {v}")

    # Use empirical x for baskets + corrected (centered) y = 25
    bL_x, bL_y = emp["basket_l_x"], BASKET_Y_FT
    bR_x, bR_y = emp["basket_r_x"], BASKET_Y_FT
    # Override ft_y to use the corrected (centered) value for distance
    ft_y = ft_y_corrected

    dist_L = np.hypot(ft_x - bL_x, ft_y - bL_y)
    dist_R = np.hypot(ft_x - bR_x, ft_y - bR_y)
    dist_fixed = np.minimum(dist_L, dist_R)

    # Determine which basket is closer (used for paint shape projection)
    nearer_left = dist_L < dist_R
    near_bx = np.where(nearer_left, bL_x, bR_x)
    near_by = np.where(nearer_left, bL_y, bR_y)

    # NBA paint = rectangle from baseline 16 ft TOWARD center court,
    # half-width 6 ft. Basket sits 4.75 ft from baseline, so paint extends
    # 16 - 4.75 = ~11.25 ft from basket toward center court along x-axis.
    # IN_PAINT requires:
    #   - |ft_y - basket_y| <= 6 (lane half-width)
    #   - AND ft_x on the near-basket side of free-throw line
    in_paint_box = (
        (np.abs(ft_y - near_by) <= PAINT_HALF_W_FT)
        & np.where(
            nearer_left,
            ft_x <= (bL_x + (PAINT_LENGTH_FT - 4.75)),  # left side: toward center from L
            ft_x >= (bR_x - (PAINT_LENGTH_FT - 4.75)),  # right side: toward center from R
        )
    )
    in_paint_fixed = in_paint_box.astype(int)
    near_basket = (dist_fixed <= PAINT_RADIUS_FT).astype(int)

    out = pd.DataFrame({
        "frame":         df["frame"],
        "player_id":     df.get("player_id", ""),
        "ft_x":          ft_x.round(2),          # unchanged from raw
        "ft_y_corrected": ft_y.round(2),         # raw - shift_y
        "dist_to_basket_ft_fixed": dist_fixed.round(2),
        "in_paint_fixed":          in_paint_fixed,
        "near_basket_fixed":       near_basket,
        "basket_x_emp":            near_bx,
        "basket_y_emp":            near_by,
        "homography_corrected":    True,
    })
    out_path = d / "tracking_data_corrected.csv"
    out.to_csv(out_path, index=False)

    # Write the landmarks JSON next to it
    landmarks["game_id"] = game_id
    landmarks["paint_length_ft"]      = PAINT_LENGTH_FT
    landmarks["paint_half_w_ft"]      = PAINT_HALF_W_FT
    landmarks["near_basket_radius_ft"] = PAINT_RADIUS_FT
    landmarks["paint_time_pct_fixed"] = round(
        100.0 * in_paint_fixed.mean(), 2
    )
    landmarks["near_basket_pct_fixed"] = round(
        100.0 * near_basket.mean(), 2
    )
    landmarks["dist_to_basket_min_fixed"]    = round(float(dist_fixed.min()), 2)
    landmarks["dist_to_basket_median_fixed"] = round(float(dist_fixed.median()), 2)
    (d / ".homography_fix.json").write_text(json.dumps(landmarks, indent=2))

    return {
        "game_id": game_id,
        "ok": True,
        "landmarks": landmarks,
        "out": str(out_path),
    }


def _list_from_log() -> list[str]:
    ids = []
    if INGEST_LOG.exists():
        with open(INGEST_LOG, newline="") as f:
            for row in csv.DictReader(f):
                if row.get("status") == "OK" and row.get("game_id") not in ids:
                    ids.append(row["game_id"])
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("game_id", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--from-log", action="store_true")
    ap.add_argument("--visualize", action="store_true")
    args = ap.parse_args()

    if args.all:
        ids = sorted(p.name for p in BACKUP.iterdir() if p.is_dir())
    elif args.from_log:
        ids = _list_from_log()
    elif args.game_id:
        ids = [args.game_id]
    else:
        ap.print_help()
        return 1

    n_ok = 0
    for g in ids:
        r = fix_game(g, visualize=args.visualize)
        if r["ok"]:
            n_ok += 1
            lm = r["landmarks"]
            print(f"  [{g}] basket_L=({lm['basket_l_x']}, {lm['basket_l_y']})  "
                  f"basket_R=({lm['basket_r_x']}, {lm['basket_r_y']})  "
                  f"shift_y={lm['homography_shift_y']}  "
                  f"paint_time%={lm.get('paint_time_pct_fixed', 'N/A')}")
        else:
            print(f"  [{g}] FAIL: {r.get('error', 'unknown')}")
    print(f"\n{n_ok}/{len(ids)} games fixed.")
    return 0 if n_ok == len(ids) else 2


if __name__ == "__main__":
    sys.exit(main())
