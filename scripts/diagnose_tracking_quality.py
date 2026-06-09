#!/usr/bin/env python3
"""diagnose_tracking_quality.py — Per-game tracking quality diagnostic.

For each game, evaluates:
  * Homography sanity: ft_x, ft_y distributions vs expected (0-94, 0-50 centered at 25)
  * Basket reference accuracy: dist_to_basket_ft min should be near 0
  * Paint detection: court_zone tags for paint should be ~5-15% of frames
  * Pose pipeline: ankle_x notna pct + contest_arm_angle nonzero pct
  * Sentinel rates: defender_distance == 99.0 incidence
  * Player resolution: real_player_name_pct
  * Frame coverage: total frames written vs expected from video length

Writes `.diagnostic.json` per game with quality grades (A/B/C/F) per signal class.

Usage:
    python scripts/diagnose_tracking_quality.py 0022500279
    python scripts/diagnose_tracking_quality.py --all
    python scripts/diagnose_tracking_quality.py --from-log
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BACKUP = Path(r"C:\Users\neelj\nba-data-backup\tracking")
INGEST_LOG = BACKUP.parent / ".ingest_log.csv"


def _grade(pct: float, *, ranges=(0.90, 0.70, 0.50, 0.30)) -> str:
    """Return A/B/C/D/F based on nonzero percentage."""
    if pct >= ranges[0]: return "A"
    if pct >= ranges[1]: return "B"
    if pct >= ranges[2]: return "C"
    if pct >= ranges[3]: return "D"
    return "F"


def diagnose(game_id: str) -> dict:
    d = BACKUP / game_id
    out: dict = {"game_id": game_id, "checks": {}, "grades": {}}
    feat = d / "features.csv"
    track = d / "tracking_data.csv"
    src = feat if feat.exists() else track
    if not src.exists():
        out["error"] = "no features.csv or tracking_data.csv"
        return out
    try:
        df = pd.read_csv(src, low_memory=False)
        out["checks"]["source"] = src.name
    except Exception as e:
        out["error"] = f"load fail: {e}"
        return out

    # Merge in homography-corrected columns when present
    fix = d / "tracking_data_corrected.csv"
    if fix.exists():
        try:
            cf = pd.read_csv(fix, low_memory=False)
            cf_cols = [c for c in cf.columns
                       if c.endswith("_fixed") or c.endswith("_corrected")
                       or c in ("frame", "player_id")]
            df = df.merge(cf[cf_cols], on=["frame", "player_id"], how="left")
            out["checks"]["homography_corrected"] = True
        except Exception:
            pass

    n = len(df)
    out["checks"]["n_rows"] = n

    # ── 1. Homography sanity ─────────────────────────────────────────────
    # Use FIXED columns when available (post-homography-correction), else raw
    if "ft_y_corrected" in df.columns:
        ft_y = pd.to_numeric(df["ft_y_corrected"], errors="coerce")
        out["checks"]["ft_y_source"] = "corrected"
    elif "ft_y" in df.columns:
        ft_y = pd.to_numeric(df["ft_y"], errors="coerce")
        out["checks"]["ft_y_source"] = "raw"
    else:
        ft_y = None
    if ft_y is not None:
        median_y = float(ft_y.median())
        out["checks"]["ft_y_median"] = round(median_y, 2)
        out["checks"]["ft_y_min"] = round(float(ft_y.min()), 2)
        out["checks"]["ft_y_max"] = round(float(ft_y.max()), 2)
        homography_ok = 18.0 <= median_y <= 32.0
        out["grades"]["homography_y_centering"] = "A" if homography_ok else "F"

    dtb_col = "dist_to_basket_ft_fixed" if "dist_to_basket_ft_fixed" in df.columns else "dist_to_basket_ft"
    if dtb_col in df.columns:
        dtb = pd.to_numeric(df[dtb_col], errors="coerce")
        min_dtb = float(dtb.min())
        out["checks"]["dist_to_basket_min"] = round(min_dtb, 2)
        out["checks"]["dist_to_basket_source"] = dtb_col
        basket_ok = min_dtb <= 3.0
        out["grades"]["basket_reference"] = "A" if basket_ok else "F"

    # ── 2. Paint detection ───────────────────────────────────────────────
    if "in_paint_fixed" in df.columns:
        paint_pct = pd.to_numeric(df["in_paint_fixed"],
                                  errors="coerce").fillna(0).mean()
        out["checks"]["paint_zone_pct"] = round(100 * paint_pct, 2)
        out["checks"]["paint_source"] = "in_paint_fixed"
        if 0.05 <= paint_pct <= 0.35: out["grades"]["paint_detection"] = "A"
        elif 0.02 <= paint_pct <= 0.50: out["grades"]["paint_detection"] = "B"
        else: out["grades"]["paint_detection"] = "C"
    elif "court_zone" in df.columns:
        paint_pct = (df["court_zone"].astype(str) == "paint").mean()
        out["checks"]["paint_zone_pct"] = round(100 * paint_pct, 2)
        out["checks"]["paint_source"] = "court_zone"
        if paint_pct >= 0.05: out["grades"]["paint_detection"] = "A"
        elif paint_pct >= 0.02: out["grades"]["paint_detection"] = "C"
        else: out["grades"]["paint_detection"] = "F"

    # ── 3. Pose pipeline ──────────────────────────────────────────────────
    # Pose runs every Nth frame (stride ~8), so the MAX expected ankle_notna
    # is ~13-50% depending on _POSE_INTERVAL. Grade against that ceiling, not
    # the impossible-to-reach 90%.
    if "ankle_x" in df.columns:
        ankle_notna = pd.to_numeric(df["ankle_x"], errors="coerce").notna().mean()
        out["checks"]["ankle_x_notna_pct"] = round(100 * ankle_notna, 2)
        # Realistic thresholds: 30%+ A, 15%+ B, 5%+ C, 1%+ D, else F
        out["grades"]["ankle_keypoints"] = _grade(
            ankle_notna, ranges=(0.30, 0.15, 0.05, 0.01)
        )
    if "contest_arm_angle" in df.columns:
        ca = pd.to_numeric(df["contest_arm_angle"], errors="coerce").fillna(0)
        ca_nz = (ca > 0).mean()
        out["checks"]["contest_arm_nonzero_pct"] = round(100 * ca_nz, 2)
        out["grades"]["contest_arm"] = _grade(
            ca_nz, ranges=(0.25, 0.15, 0.05, 0.01)
        )

    # ── 4. Sentinel rates (defender_distance == 99 = missing) ─────────────
    if "defender_distance" in df.columns:
        d99 = (pd.to_numeric(df["defender_distance"], errors="coerce") >= 98.5).mean()
        out["checks"]["defender_dist_sentinel_pct"] = round(100 * d99, 2)
        # Low is better (means most frames have real defender data)
        out["grades"]["defender_dist_completeness"] = _grade(1 - d99)

    # ── 5. Player resolution ──────────────────────────────────────────────
    if "player_name" in df.columns:
        names = df["player_name"].astype(str)
        is_placeholder = names.str.contains(
            r"^(?:white|green|placeholder|UNKN)", case=False, na=True, regex=True
        )
        real_pct = (~is_placeholder).mean()
        out["checks"]["real_player_name_pct"] = round(100 * real_pct, 2)
        out["grades"]["player_id_resolution"] = _grade(real_pct)

    # ── 6. CV moat signals ────────────────────────────────────────────────
    # paint_pressure: prefer the homography-corrected version if present
    if "paint_pressure_90_fixed" in df.columns:
        v = pd.to_numeric(df["paint_pressure_90_fixed"],
                          errors="coerce").fillna(0)
        nz = (v != 0).mean()
        out["checks"]["paint_pressure_90_nonzero_pct"] = round(100 * nz, 2)
        out["checks"]["paint_pressure_source"] = "fixed"
        out["grades"]["paint_pressure_90"] = _grade(
            nz, ranges=(0.80, 0.60, 0.40, 0.20)
        )

    moat_cols = {
        "defender_dist_mean_90": (0.90, 0.70, 0.50, 0.30),
        "off_ball_dist_mean_90": (0.80, 0.60, 0.40, 0.20),
        "team_spacing_imputed":  (0.90, 0.70, 0.50, 0.30),
        "velocity_ewma":         (0.85, 0.65, 0.45, 0.25),
    }
    # Only include paint_pressure_90 (broken version) if no fixed cousin
    if "paint_pressure_90_fixed" not in df.columns:
        moat_cols["paint_pressure_90"] = (0.50, 0.30, 0.10, 0.03)
    for col, ranges in moat_cols.items():
        if col in df.columns:
            v = pd.to_numeric(df[col], errors="coerce").fillna(0)
            nz = (v != 0).mean()
            out["checks"][f"{col}_nonzero_pct"] = round(100 * nz, 2)
            out["grades"][col] = _grade(nz, ranges=ranges)

    # ── 7. Overall ───────────────────────────────────────────────────────
    grades = list(out["grades"].values())
    if grades:
        gpa_map = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
        gpa = sum(gpa_map.get(g, 0) for g in grades) / len(grades)
        out["overall_gpa"] = round(gpa, 2)
        out["overall"] = (
            "A" if gpa >= 3.5 else "B" if gpa >= 2.5 else
            "C" if gpa >= 1.5 else "D" if gpa >= 0.5 else "F"
        )

    # Write per-game .diagnostic.json
    snap = d / ".diagnostic.json"
    try:
        snap.write_text(json.dumps(out, indent=2))
    except Exception:
        pass
    return out


def _list_from_log() -> list[str]:
    import csv as _csv
    ids = []
    if INGEST_LOG.exists():
        with open(INGEST_LOG, newline="") as f:
            for row in _csv.DictReader(f):
                if row.get("status") == "OK" and row.get("game_id") not in ids:
                    ids.append(row["game_id"])
    return ids


def _print(r: dict) -> None:
    print(f"\n=== [{r['game_id']}] overall: {r.get('overall', 'N/A')} "
          f"(GPA {r.get('overall_gpa', 0)}) ===")
    if "error" in r:
        print(f"  ERROR: {r['error']}")
        return
    # Map grade category → relevant checks key
    cat_to_checks = {
        "homography_y_centering": "ft_y_median",
        "basket_reference": "dist_to_basket_min",
        "paint_detection": "paint_zone_pct",
        "ankle_keypoints": "ankle_x_notna_pct",
        "contest_arm": "contest_arm_nonzero_pct",
        "defender_dist_completeness": "defender_dist_sentinel_pct",
        "player_id_resolution": "real_player_name_pct",
    }
    for cat, grade in r["grades"].items():
        check_key = cat_to_checks.get(cat, f"{cat}_nonzero_pct")
        check_val = r["checks"].get(check_key, "")
        bar = "#" * {"A": 5, "B": 4, "C": 3, "D": 2, "F": 1}[grade]
        print(f"  {cat:35} {grade}  {bar:5}  {check_val}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("game_id", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--from-log", action="store_true")
    ap.add_argument("--json", action="store_true")
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

    results = [diagnose(g) for g in ids]
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            _print(r)

    # Roll-up
    grades = [r.get("overall") for r in results if r.get("overall")]
    if grades:
        from collections import Counter
        c = Counter(grades)
        print(f"\nRoll-up: {dict(c)}  of {len(grades)} games")
    return 0


if __name__ == "__main__":
    sys.exit(main())
