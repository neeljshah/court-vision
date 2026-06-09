#!/usr/bin/env python3
"""
cv_scorecard.py — Honest, measured quality scorecard for the CourtVision tracker.

Reads a tracking_data.csv (or a directory containing one) and computes the exact
quality metrics that gate this project. EVERY number printed here is measured from
the CSV — nothing is claimed. Designed to be the single source of truth for
baseline-vs-improved comparisons.

Metrics
-------
players_per_frame   : distinct non-referee tracks per frame (median / p10 / p90 / mean).
                      Target = 10. This is the headline recall number.
id_switch_proxy     : "teleports" — consecutive rows for the same player_id whose
                      court-space displacement implies an impossible speed
                      (> SPEED_CAP ft/s). High = ID confusion / track swaps.
                      Reported per 1000 track-steps and per minute. (No ground-truth
                      MOTA available; this is a self-consistency proxy.)
homography_valid_pct: mean of homography_valid column (fraction of frames with a
                      trusted court mapping).
possession_realism  : distinct possession_id count and possessions/minute
                      (NBA reality ~3.8-4.2 total possessions/min).
defender_distance   : nearest_opponent distribution + % physically impossible
                      (> 94 ft, the court length).
team_spacing        : distribution + order-of-magnitude check (px^2 vs ft^2 drift).
jump_detected_rate  : fraction of rows with jump_detected==1 (sane << 0.10).
dist_to_basket_ft   : distribution (should be 0-94 ft).
schema              : exact column set + which expected fields are missing.

Usage
-----
    python scripts/cv_scorecard.py <tracking_data.csv | dir> [--fps 60] [--json out.json] [--label NAME]
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import pandas as pd

# A player cannot move faster than ~ this on a court. Usain Bolt ~ 12.4 m/s = 40.7 ft/s.
# Anything above is an ID switch / detection jumping to a different person.
SPEED_CAP_FTPS = 40.0
COURT_LEN_FT = 94.0
COURT_WID_FT = 50.0
REF_LABELS = {"referee", "ref", "official", "", "nan", "none"}


def _safe_num(series):
    return pd.to_numeric(series, errors="coerce")


def _dist_stats(arr, name):
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"name": name, "n": 0}
    return {
        "name": name,
        "n": int(arr.size),
        "min": round(float(np.min(arr)), 3),
        "p05": round(float(np.percentile(arr, 5)), 3),
        "median": round(float(np.median(arr)), 3),
        "mean": round(float(np.mean(arr)), 3),
        "p95": round(float(np.percentile(arr, 95)), 3),
        "max": round(float(np.max(arr)), 3),
    }


def _court_xy(df):
    """Return per-row (x_ft, y_ft) in court feet, using the best available columns.
    Preference: ft_x/ft_y (already clamped 0-94) > x_norm/y_norm*court > x/y_position (unknown units)."""
    if "ft_x" in df and "ft_y" in df and _safe_num(df["ft_x"]).notna().mean() > 0.5:
        return _safe_num(df["ft_x"]).to_numpy(), _safe_num(df["ft_y"]).to_numpy(), "ft_x/ft_y"
    if "x_norm" in df and "y_norm" in df and _safe_num(df["x_norm"]).notna().mean() > 0.5:
        return (_safe_num(df["x_norm"]).to_numpy() * COURT_LEN_FT,
                _safe_num(df["y_norm"]).to_numpy() * COURT_WID_FT, "x_norm/y_norm")
    return (_safe_num(df.get("x_position", pd.Series(dtype=float))).to_numpy(),
            _safe_num(df.get("y_position", pd.Series(dtype=float))).to_numpy(), "x_position/y_position(raw)")


def scorecard(csv_path, fps=60.0, label=None):
    df = pd.read_csv(csv_path, low_memory=False)
    n_rows = len(df)
    out = {"label": label or os.path.basename(os.path.dirname(csv_path) or csv_path),
           "csv": csv_path, "n_rows": n_rows, "fps_assumed": fps}
    if n_rows == 0:
        out["error"] = "empty CSV"
        return out

    # ---- frames & duration ----
    frames = _safe_num(df["frame"]) if "frame" in df else pd.Series(range(n_rows))
    n_frames = int(frames.nunique())
    frame_span = int(frames.max() - frames.min() + 1) if n_frames else 0
    # infer fps from timestamp if available
    fps_inferred = None
    if "timestamp" in df:
        ts = _safe_num(df["timestamp"])
        if ts.notna().sum() > 10 and (ts.max() - ts.min()) > 0:
            fps_inferred = round(frame_span / (ts.max() - ts.min()), 2)
    minutes = (frame_span / fps) / 60.0 if frame_span else 0.0
    out.update({"n_distinct_frames": n_frames, "frame_span": frame_span,
                "fps_inferred_from_ts": fps_inferred, "approx_minutes": round(minutes, 2)})

    # ---- players per frame (non-referee) ----
    team = df["team"].astype(str).str.lower().str.strip() if "team" in df else pd.Series(["?"] * n_rows)
    is_player = ~team.isin(REF_LABELS)
    pf = df[is_player].groupby(frames[is_player]).apply(
        lambda g: g["player_id"].nunique() if "player_id" in g else len(g))
    pf = pf.to_numpy()
    out["players_per_frame"] = {
        "median": float(np.median(pf)) if pf.size else 0,
        "p10": round(float(np.percentile(pf, 10)), 2) if pf.size else 0,
        "p90": round(float(np.percentile(pf, 90)), 2) if pf.size else 0,
        "mean": round(float(np.mean(pf)), 2) if pf.size else 0,
        "max": int(np.max(pf)) if pf.size else 0,
        "pct_frames_ge9": round(float(np.mean(pf >= 9)) * 100, 1) if pf.size else 0,
        "pct_frames_ge10": round(float(np.mean(pf >= 10)) * 100, 1) if pf.size else 0,
        "target": 10,
    }

    # ---- ID-switch / teleport proxy ----
    teleports = 0
    steps = 0
    if "player_id" in df:
        x_ft, y_ft, xy_src = _court_xy(df)
        out["court_xy_source"] = xy_src
        work = pd.DataFrame({"pid": df["player_id"].astype(str), "frame": frames,
                             "x": x_ft, "y": y_ft})
        work = work[np.isfinite(work["x"]) & np.isfinite(work["y"])].sort_values(["pid", "frame"])
        for pid, g in work.groupby("pid"):
            if len(g) < 2:
                continue
            dx = g["x"].diff().to_numpy()[1:]
            dy = g["y"].diff().to_numpy()[1:]
            dfr = g["frame"].diff().to_numpy()[1:]
            dist = np.hypot(dx, dy)
            dt = np.clip(dfr / fps, 1.0 / fps, None)
            speed = dist / dt
            steps += len(speed)
            teleports += int(np.sum(speed > SPEED_CAP_FTPS))
        out["id_switch_proxy"] = {
            "teleports": teleports, "track_steps": steps,
            "per_1000_steps": round(teleports / steps * 1000, 2) if steps else None,
            "per_minute": round(teleports / minutes, 2) if minutes else None,
            "speed_cap_ftps": SPEED_CAP_FTPS,
            "note": "self-consistency proxy (no ground-truth MOTA)",
        }

    # ---- possession realism ----
    if "possession_id" in df:
        pid = _safe_num(df["possession_id"])
        n_poss = int(pid.nunique())
        out["possession_realism"] = {
            "n_distinct_possession_id": n_poss,
            "per_minute": round(n_poss / minutes, 2) if minutes else None,
            "nba_realistic_per_minute": "3.8-4.2",
        }

    # ---- defender distance sanity ----
    for col in ("nearest_opponent", "nearest_teammate", "distance_to_ball", "dist_to_basket_ft"):
        if col in df:
            v = _safe_num(df[col])
            s = _dist_stats(v, col)
            vv = v[np.isfinite(v)]
            s["pct_impossible_gt94ft"] = round(float(np.mean(vv > COURT_LEN_FT)) * 100, 2) if len(vv) else None
            out.setdefault("distance_sanity", {})[col] = s

    # ---- team spacing units ----
    if "team_spacing" in df:
        out["team_spacing"] = _dist_stats(_safe_num(df["team_spacing"]), "team_spacing")
    if "spacing_hull_area" in df:
        out["spacing_hull_area"] = _dist_stats(_safe_num(df["spacing_hull_area"]), "spacing_hull_area")

    # ---- jump_detected rate ----
    if "jump_detected" in df:
        jd = _safe_num(df["jump_detected"])
        out["jump_detected_rate"] = {
            "pct_rows": round(float(jd.fillna(0).astype(bool).mean()) * 100, 2),
            "sane_threshold_pct": "<10",
        }

    # ---- homography valid ----
    if "homography_valid" in df:
        hv = _safe_num(df["homography_valid"])
        out["homography_valid_pct"] = round(float(hv.fillna(0).mean()) * 100, 2)

    # ---- schema ----
    EXPECTED = {"frame", "player_id", "team", "x_position", "y_position", "x_norm", "y_norm",
                "ft_x", "ft_y", "dist_to_basket_ft", "nearest_opponent", "team_spacing",
                "possession_id", "jump_detected", "homography_valid"}
    cols = set(df.columns)
    out["schema"] = {"n_cols": len(cols), "missing_expected": sorted(EXPECTED - cols)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="tracking_data.csv or directory containing one")
    ap.add_argument("--fps", type=float, default=60.0)
    ap.add_argument("--json", default=None, help="write JSON here")
    ap.add_argument("--label", default=None)
    args = ap.parse_args()
    csv = args.path
    if os.path.isdir(csv):
        csv = os.path.join(csv, "tracking_data.csv")
    if not os.path.exists(csv):
        print(f"ERROR: no CSV at {csv}", file=sys.stderr)
        sys.exit(1)
    res = scorecard(csv, fps=args.fps, label=args.label)
    print(json.dumps(res, indent=2, default=str))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(res, f, indent=2, default=str)
        print(f"\n[written] {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
