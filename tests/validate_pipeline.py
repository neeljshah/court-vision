"""
tests/validate_pipeline.py — Full pipeline output validator

Runs the complete tracking pipeline on a video, then audits every output CSV
for correctness, completeness, and data quality.

Usage
-----
    conda activate basketball_ai
    cd C:/Users/neelj/nba-ai-system

    # Run pipeline then validate (recommended)
    python tests/validate_pipeline.py --run

    # Validate existing outputs only (pipeline already run)
    python tests/validate_pipeline.py

    # Custom video + frame limit
    python tests/validate_pipeline.py --run --video path/to/clip.mp4 --frames 300
"""

import argparse
import os
import subprocess
import sys

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR    = os.path.join(PROJECT_DIR, "data")
DEFAULT_VID = os.path.join(PROJECT_DIR, "resources", "Short4Mosaicing.mp4")

# ── Thresholds ────────────────────────────────────────────────────────────────

# Tracking
MIN_PLAYERS_PER_FRAME  = 2.0    # avg players tracked per frame
MIN_TRACK_STABILITY    = 0.60   # ID stability score (0–1)
MAX_OOB_PCT            = 0.10   # max fraction of out-of-bounds positions
MIN_VELOCITY_NONZERO   = 0.50   # fraction of rows where velocity > 0

# Ball
MIN_BALL_DETECTION_RATE = 0.05  # at least 5% of frames detect the ball
                                # (Hough is hard; even low is informative)

# Features
MIN_FEATURE_COLS = 20           # at least this many columns in features.csv
MIN_NAN_FREE_PCT = 0.80         # at least 80% of feature columns should be mostly non-NaN

# Court bounds (pixels — rough, varies by video resolution)
COURT_X_RANGE = (0, 3000)
COURT_Y_RANGE = (0, 2000)

# ── Required columns per file ─────────────────────────────────────────────────

TRACKING_REQUIRED = {
    "frame", "player_id", "team",
    "x_position", "y_position",
    "velocity", "ball_possession",
}

BALL_REQUIRED = {"frame", "detected"}

POSSESSION_REQUIRED = {
    "possession_id", "team", "duration_frames",
}

SHOT_REQUIRED = {
    "frame", "team", "court_zone",
}

PLAYER_STATS_REQUIRED = {
    "player_id", "team",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

PASS  = "PASS"
FAIL  = "FAIL"
WARN  = "WARN"
SKIP  = "SKIP"


class Report:
    def __init__(self):
        self._rows: list[tuple[str, str, str]] = []

    def add(self, status: str, name: str, detail: str = ""):
        self._rows.append((status, name, detail))

    def ok(self,   name: str, detail: str = ""): self.add(PASS, name, detail)
    def fail(self, name: str, detail: str = ""): self.add(FAIL, name, detail)
    def warn(self, name: str, detail: str = ""): self.add(WARN, name, detail)
    def skip(self, name: str, detail: str = ""): self.add(SKIP, name, detail)

    def print(self):
        icons = {PASS: "✓", FAIL: "✗", WARN: "!", SKIP: "~"}
        width = max(len(n) for _, n, _ in self._rows) + 2
        for status, name, detail in self._rows:
            icon = icons[status]
            line = f"  {icon}  {name:<{width}}"
            if detail:
                line += f"  {detail}"
            print(line)
        print()

    @property
    def passed(self) -> bool:
        return not any(s == FAIL for s, _, _ in self._rows)

    @property
    def counts(self) -> dict:
        from collections import Counter
        return dict(Counter(s for s, _, _ in self._rows))


# ── File-level validators ─────────────────────────────────────────────────────

def _check_file(r: Report, path: str, label: str) -> pd.DataFrame | None:
    if not os.path.exists(path):
        r.fail(f"{label} exists", "NOT FOUND")
        return None
    size_kb = os.path.getsize(path) / 1024
    try:
        df = pd.read_csv(path)
    except Exception as e:
        r.fail(f"{label} readable", str(e))
        return None
    r.ok(f"{label} exists", f"{len(df)} rows, {len(df.columns)} cols, {size_kb:.1f} KB")
    return df


def _check_cols(r: Report, df: pd.DataFrame, required: set, label: str):
    missing = required - set(df.columns)
    if missing:
        r.fail(f"{label} columns", f"missing: {sorted(missing)}")
    else:
        r.ok(f"{label} columns", f"all required columns present")


def _check_nonempty(r: Report, df: pd.DataFrame, label: str, min_rows: int = 1) -> bool:
    if len(df) < min_rows:
        r.fail(f"{label} non-empty", f"only {len(df)} rows")
        return False
    return True


# ── Section: tracking_data.csv ────────────────────────────────────────────────

def validate_tracking(r: Report):
    path = os.path.join(DATA_DIR, "tracking_data.csv")
    print("── tracking_data.csv ─────────────────────────────────────────")
    df = _check_file(r, path, "tracking_data")
    if df is None:
        return

    _check_cols(r, df, TRACKING_REQUIRED, "tracking_data")
    if not _check_nonempty(r, df, "tracking_data"):
        return

    # Per-frame player count
    if "frame" in df.columns and "player_id" in df.columns:
        pf = df.groupby("frame")["player_id"].count()
        avg = pf.mean()
        zero_frames = (pf == 0).sum()
        total_frames = pf.shape[0]
        if avg >= MIN_PLAYERS_PER_FRAME:
            r.ok("avg players/frame", f"{avg:.1f}")
        else:
            r.fail("avg players/frame", f"{avg:.1f} (min {MIN_PLAYERS_PER_FRAME})")
        if zero_frames / max(1, total_frames) <= 0.20:
            r.ok("frames with 0 players", f"{zero_frames}/{total_frames}")
        else:
            r.warn("frames with 0 players", f"{zero_frames}/{total_frames} ({100*zero_frames/total_frames:.0f}%)")

    # Team distribution
    if "team" in df.columns:
        teams = df["team"].value_counts().to_dict()
        r.ok("team distribution", str(teams))

    # x/y positions in bounds
    if "x_position" in df.columns and "y_position" in df.columns:
        xy = df[["x_position", "y_position"]].dropna()
        oob = ((xy["x_position"] < COURT_X_RANGE[0]) | (xy["x_position"] > COURT_X_RANGE[1]) |
               (xy["y_position"] < COURT_Y_RANGE[0]) | (xy["y_position"] > COURT_Y_RANGE[1]))
        oob_pct = oob.mean()
        x_range = f"x=[{xy['x_position'].min():.0f}, {xy['x_position'].max():.0f}]"
        y_range = f"y=[{xy['y_position'].min():.0f}, {xy['y_position'].max():.0f}]"
        if oob_pct <= MAX_OOB_PCT:
            r.ok("court position bounds", f"{x_range}  {y_range}")
        else:
            r.fail("court position bounds", f"{oob_pct*100:.1f}% OOB — {x_range} {y_range}")

    # Velocity non-zero
    if "velocity" in df.columns:
        vel = df["velocity"].dropna()
        nonzero_pct = (vel > 0).mean()
        if nonzero_pct >= MIN_VELOCITY_NONZERO:
            r.ok("velocity non-zero", f"{nonzero_pct*100:.0f}% of rows > 0")
        else:
            r.warn("velocity non-zero", f"only {nonzero_pct*100:.0f}% > 0 (expected ≥{MIN_VELOCITY_NONZERO*100:.0f}%)")

    # Ball possession
    if "ball_possession" in df.columns:
        poss_pct = df["ball_possession"].mean()
        r.ok("ball possession", f"{poss_pct*100:.1f}% of player-frames have possession")

    # Event detection
    if "event" in df.columns:
        event_counts = df["event"].value_counts().to_dict()
        non_none = {k: v for k, v in event_counts.items() if k not in ("none", "", "nan")}
        if non_none:
            r.ok("events detected", str(non_none))
        else:
            r.warn("events detected", "no events (shot/pass/dribble) found — clip may be too short")

    # Possession ID
    if "possession_id" in df.columns:
        n_poss = df["possession_id"].nunique()
        r.ok("possession_id in tracking", f"{n_poss} unique possession IDs")
    else:
        r.warn("possession_id in tracking", "column missing — unified_pipeline may not be outputting it")

    # court_zone
    if "court_zone" in df.columns:
        zones = df["court_zone"].value_counts().to_dict()
        r.ok("court zones", str(zones))
    else:
        r.warn("court_zone", "column missing")

    print()


# ── Section: ball_tracking.csv ────────────────────────────────────────────────

def validate_ball(r: Report):
    path = os.path.join(DATA_DIR, "ball_tracking.csv")
    print("── ball_tracking.csv ─────────────────────────────────────────")
    df = _check_file(r, path, "ball_tracking")
    if df is None:
        return

    _check_cols(r, df, BALL_REQUIRED, "ball_tracking")
    if not _check_nonempty(r, df, "ball_tracking"):
        return

    if "detected" in df.columns:
        det_rate = df["detected"].mean()
        if det_rate >= MIN_BALL_DETECTION_RATE:
            r.ok("ball detection rate", f"{det_rate*100:.1f}% of frames")
        else:
            r.warn("ball detection rate",
                   f"{det_rate*100:.1f}% — very low. "
                   "Hough circles struggle on this clip. "
                   "Consider YOLO ball detector.")

    # Check 2D ball positions when detected
    if "ball_x2d" in df.columns and "ball_y2d" in df.columns:
        detected = df[df["detected"] == 1][["ball_x2d", "ball_y2d"]].dropna()
        if len(detected) > 0:
            r.ok("ball 2D positions", f"{len(detected)} frames with 2D coords")
        else:
            r.warn("ball 2D positions", "no 2D ball positions (homography not applied to ball?)")
    else:
        r.warn("ball 2D columns", "ball_x2d / ball_y2d missing")

    print()


# ── Section: possessions.csv ──────────────────────────────────────────────────

def validate_possessions(r: Report):
    path = os.path.join(DATA_DIR, "possessions.csv")
    print("── possessions.csv ───────────────────────────────────────────")
    df = _check_file(r, path, "possessions")
    if df is None:
        return

    _check_cols(r, df, POSSESSION_REQUIRED, "possessions")

    if len(df) == 0:
        r.warn("possessions non-empty", "0 rows — clip may be too short or events not triggered")
        print()
        return

    if "team" in df.columns:
        team_poss = df["team"].value_counts().to_dict()
        r.ok("possessions by team", str(team_poss))

    if "duration_frames" in df.columns:
        dur = df["duration_frames"]
        r.ok("possession duration", f"mean={dur.mean():.1f}f  min={dur.min()}f  max={dur.max()}f")

    if "avg_spacing" in df.columns:
        spacing_nan = df["avg_spacing"].isna().mean()
        if spacing_nan < 0.5:
            r.ok("spacing data", f"{(1-spacing_nan)*100:.0f}% of possessions have spacing")
        else:
            r.warn("spacing data", f"{spacing_nan*100:.0f}% NaN — convex hull may be failing")

    if "shot_attempted" in df.columns:
        shots = df["shot_attempted"].sum()
        r.ok("shot_attempted flag", f"{int(shots)} possessions ended in shot attempt")

    print()


# ── Section: shot_log.csv ─────────────────────────────────────────────────────

def validate_shot_log(r: Report):
    path = os.path.join(DATA_DIR, "shot_log.csv")
    print("── shot_log.csv ──────────────────────────────────────────────")
    df = _check_file(r, path, "shot_log")
    if df is None:
        return

    if len(df) == 0:
        r.warn("shot_log non-empty",
               "0 shots — expected on very short clips (<30s). "
               "Run on a full game quarter to validate.")
        print()
        return

    _check_cols(r, df, SHOT_REQUIRED, "shot_log")

    if "court_zone" in df.columns:
        zones = df["court_zone"].value_counts().to_dict()
        r.ok("shot zones", str(zones))

    if "defender_distance" in df.columns:
        def_dist = df["defender_distance"].dropna()
        if len(def_dist) > 0:
            r.ok("defender_distance", f"mean={def_dist.mean():.1f}  min={def_dist.min():.1f}")
        else:
            r.warn("defender_distance", "all NaN")

    if "team_spacing" in df.columns:
        spacing = df["team_spacing"].dropna()
        if len(spacing) > 0:
            r.ok("shot team_spacing", f"mean={spacing.mean():.1f}")
        else:
            r.warn("shot team_spacing", "all NaN")

    print()


# ── Section: player_clip_stats.csv ────────────────────────────────────────────

def validate_player_stats(r: Report):
    path = os.path.join(DATA_DIR, "player_clip_stats.csv")
    print("── player_clip_stats.csv ─────────────────────────────────────")
    df = _check_file(r, path, "player_clip_stats")
    if df is None:
        return

    _check_cols(r, df, PLAYER_STATS_REQUIRED, "player_clip_stats")
    if not _check_nonempty(r, df, "player_clip_stats"):
        return

    r.ok("player count", f"{len(df)} players tracked across clip")

    if "total_distance" in df.columns:
        dist = df["total_distance"].dropna()
        if dist.gt(0).any():
            r.ok("total_distance", f"max={dist.max():.0f}  mean={dist.mean():.0f} px")
        else:
            r.warn("total_distance", "all zero — velocity not accumulating?")

    if "possession_pct" in df.columns:
        pp = df["possession_pct"].dropna()
        if pp.sum() > 0:
            r.ok("possession_pct", f"sum={pp.sum():.2f} (should be ~1.0 or 2.0 across both teams)")
        else:
            r.warn("possession_pct", "all zero")

    print()


# ── Section: features.csv ─────────────────────────────────────────────────────

def validate_features(r: Report):
    path = os.path.join(DATA_DIR, "features.csv")
    print("── features.csv ──────────────────────────────────────────────")
    df = _check_file(r, path, "features")
    if df is None:
        return

    if not _check_nonempty(r, df, "features"):
        return

    # Column count
    n_cols = len(df.columns)
    if n_cols >= MIN_FEATURE_COLS:
        r.ok("feature column count", f"{n_cols} columns")
    else:
        r.fail("feature column count", f"only {n_cols} cols (expected ≥{MIN_FEATURE_COLS})")

    # NaN audit
    nan_fracs = df.isna().mean()
    all_nan_cols = nan_fracs[nan_fracs == 1.0].index.tolist()
    high_nan_cols = nan_fracs[(nan_fracs > 0.5) & (nan_fracs < 1.0)].index.tolist()
    mostly_ok = (nan_fracs < 0.5).mean()

    if all_nan_cols:
        r.fail("all-NaN columns", f"{len(all_nan_cols)} cols: {all_nan_cols[:5]}")
    else:
        r.ok("all-NaN columns", "none")

    if high_nan_cols:
        r.warn(">50% NaN columns", f"{len(high_nan_cols)}: {high_nan_cols[:5]}")
    else:
        r.ok(">50% NaN columns", "none")

    if mostly_ok >= MIN_NAN_FREE_PCT:
        r.ok("data completeness", f"{mostly_ok*100:.0f}% of columns mostly populated")
    else:
        r.warn("data completeness", f"only {mostly_ok*100:.0f}% of columns mostly populated")

    # Rolling feature presence
    rolling_cols = [c for c in df.columns if "roll" in c.lower() or "window" in c.lower()]
    if rolling_cols:
        r.ok("rolling features", f"{len(rolling_cols)} rolling/window columns found")
    else:
        r.warn("rolling features", "no rolling features found — feature_engineering may not be running")

    print()


# ── Section: cross-file consistency ──────────────────────────────────────────

def validate_cross_file(r: Report):
    print("── cross-file consistency ────────────────────────────────────")
    td_path = os.path.join(DATA_DIR, "tracking_data.csv")
    fe_path = os.path.join(DATA_DIR, "features.csv")
    bl_path = os.path.join(DATA_DIR, "ball_tracking.csv")

    if os.path.exists(td_path) and os.path.exists(fe_path):
        td = pd.read_csv(td_path)
        fe = pd.read_csv(fe_path)
        td_frames = td["frame"].nunique() if "frame" in td.columns else 0
        fe_frames = fe["frame"].nunique() if "frame" in fe.columns else 0
        if abs(td_frames - fe_frames) <= 5:
            r.ok("tracking/features frame count", f"tracking={td_frames}  features={fe_frames}")
        else:
            r.warn("tracking/features frame count",
                   f"mismatch: tracking={td_frames}  features={fe_frames}")

    if os.path.exists(td_path) and os.path.exists(bl_path):
        td = pd.read_csv(td_path)
        bl = pd.read_csv(bl_path)
        td_max = td["frame"].max() if "frame" in td.columns else 0
        bl_max = bl["frame"].max() if "frame" in bl.columns else 0
        if abs(td_max - bl_max) <= 5:
            r.ok("tracking/ball frame sync", f"tracking max={td_max}  ball max={bl_max}")
        else:
            r.warn("tracking/ball frame sync", f"tracking ends at {td_max}, ball at {bl_max}")

    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def run_pipeline(video: str, frames: int | None):
    """Launch run_clip.py as a subprocess."""
    cmd = [sys.executable, os.path.join(PROJECT_DIR, "run_clip.py"),
           "--video", video, "--no-show"]
    if frames:
        cmd += ["--frames", str(frames)]
    print(f"\nRunning pipeline: {' '.join(cmd)}\n{'─'*60}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("\nPipeline exited with errors — validating whatever was written anyway.")
    print()


def main():
    ap = argparse.ArgumentParser(description="NBA AI pipeline validator")
    ap.add_argument("--run",    action="store_true",
                    help="Run the pipeline before validating (requires a video)")
    ap.add_argument("--video",  default=DEFAULT_VID,
                    help="Video path (used with --run)")
    ap.add_argument("--frames", type=int, default=None,
                    help="Frame limit for pipeline run (default: full video)")
    args = ap.parse_args()

    if args.run:
        if not os.path.exists(args.video):
            print(f"ERROR: video not found at {args.video}")
            sys.exit(1)
        run_pipeline(args.video, args.frames)

    print(f"\n{'='*60}")
    print("  NBA AI Pipeline Validator")
    print(f"  Data dir: {DATA_DIR}")
    print(f"{'='*60}\n")

    r_tracking = Report()
    r_ball     = Report()
    r_poss     = Report()
    r_shots    = Report()
    r_stats    = Report()
    r_features = Report()
    r_cross    = Report()

    validate_tracking(r_tracking);   r_tracking.print()
    validate_ball(r_ball);           r_ball.print()
    validate_possessions(r_poss);    r_poss.print()
    validate_shot_log(r_shots);      r_shots.print()
    validate_player_stats(r_stats);  r_stats.print()
    validate_features(r_features);   r_features.print()
    validate_cross_file(r_cross);    r_cross.print()

    all_reports = [r_tracking, r_ball, r_poss, r_shots, r_stats, r_features, r_cross]

    total_pass = sum(r.counts.get(PASS, 0) for r in all_reports)
    total_fail = sum(r.counts.get(FAIL, 0) for r in all_reports)
    total_warn = sum(r.counts.get(WARN, 0) for r in all_reports)

    print("=" * 60)
    print(f"  RESULT:  {total_pass} passed  {total_fail} failed  {total_warn} warnings")
    print("=" * 60)

    if total_fail == 0 and total_warn == 0:
        print("\n  All checks passed. Pipeline is complete and healthy.\n")
    elif total_fail == 0:
        print("\n  No failures. Review warnings above — most are expected on short test clips.\n")
    else:
        print(f"\n  {total_fail} failures need fixing before moving to Phase 1.\n")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
