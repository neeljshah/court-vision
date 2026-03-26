"""
validate_thresholds.py — Empirical threshold validation and auto-correction.

Loads all processed game directories under data/tracking/ and computes the
empirical distribution for each hard-coded spatial threshold in EventDetector
and PossessionClassifier.  Prints a formatted report and optionally applies
corrections to source files.

Usage:
    python scripts/validate_thresholds.py [--apply] [--data-dir data/tracking]

Flags:
    --apply     Write corrected threshold values back into source files
                (default: dry-run only, prints what would change)
    --data-dir  Directory to search for game subdirectories (default: data/tracking)

Auto-correction rules:
    - Only applies when |suggested - current| / current > 15% AND n_samples >= 30
    - Never auto-updates _CUT_MIN_ANGLE_COS (semantic, manual review needed)
    - Adds calibration comment with date, game count, and old value
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False

# ── Force UTF-8 stdout on Windows so box-drawing chars render correctly ───────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── Project root ──────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
sys.path.insert(0, str(_ROOT))

_DATA_DIR   = _ROOT / "data" / "tracking"
_ED_PATH    = _ROOT / "src" / "tracking" / "event_detector.py"
_PC_PATH    = _ROOT / "src" / "tracking" / "possession_classifier.py"


# ── Current threshold values (mirrors source constants) ──────────────────────
# EventDetector — fps-independent spatial constants
CURRENT = {
    "DRIVE_MIN_SPEED_MPH":  8.0,          # mph (converted from px/abs-frame in configure())
    "SCREEN_MAX_DIST_FT":   3.0,          # ft  (_SCREEN_DIST = 3.0 * ft)
    "CLOSEOUT_FAR_FT":      6.0,          # ft  (_CLOSEOUT_FAR = 6.0 * ft)
    "CLOSEOUT_NEAR_FT":     3.0,          # ft  (_CLOSEOUT_NEAR = 3.0 * ft)
    "DRIBBLE_MAX_DIST_PX":  70.0,         # px  (_DRIBBLE_MAX_DIST)
    # PossessionClassifier
    "DRIVE_VEL_PX":         3.5,          # px/frame (_DRIVE_VEL_PX)
    "DBL_TEAM_RAD_N":       0.044,        # normalised radius (_DBL_TEAM_RAD_N)
    "FAST_BRK_ADV":         1,            # integer advantage surplus (_FAST_BRK_ADV)
}


# ── Data loading ──────────────────────────────────────────────────────────────

# Columns we actually need — loading all 50+ cols is wasteful on 250MB files
_TD_COLS  = ["frame", "event", "ball_possession", "vel_toward_basket",
             "distance_to_ball", "direction_deg", "velocity",
             "shot_clock_est", "scoreboard_shot_clock",
             "possession_type", "play_type", "handler_isolation"]
_POS_COLS = ["possession_id", "team", "fast_break", "play_type",
             "shot_attempted", "result", "duration_sec"]
_SL_COLS  = ["frame", "player_id", "made", "possession_id", "possession_duration"]

# Sample at most this many rows per game to keep load time <2s per game
_MAX_ROWS_PER_GAME = 50_000


def _find_game_dirs(data_dir: Path) -> List[Path]:
    """Return all subdirectories of data_dir that have all three required CSVs."""
    required = {"tracking_data.csv", "possessions.csv", "shot_log.csv"}
    dirs = []
    for p in sorted(data_dir.iterdir()):
        if p.is_dir():
            files = {f.name for f in p.iterdir() if f.is_file()}
            if required.issubset(files):
                dirs.append(p)
    return dirs


def _load_csv(path: Path, usecols: Optional[List[str]] = None) -> List[dict]:
    """Load a CSV, selecting only needed columns and capping rows.  Uses pandas when available."""
    if _HAS_PANDAS:
        try:
            # Read header first to know which cols actually exist in this file
            header_row = pd.read_csv(path, nrows=0)
            cols = [c for c in (usecols or []) if c in header_row.columns] or None
            # nrows cap keeps large game files (250MB, 800K rows) to <1s per load
            df = pd.read_csv(path, usecols=cols, nrows=_MAX_ROWS_PER_GAME,
                             low_memory=False)
            return df.where(df.notna(), other=None).to_dict("records")
        except Exception:
            pass
    # Fallback: plain csv with row cap
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f)):
            rows.append(row)
            if i >= _MAX_ROWS_PER_GAME:
                break
    return rows


def _load_game(gdir: Path) -> Tuple[List[dict], List[dict], List[dict]]:
    td  = _load_csv(gdir / "tracking_data.csv", usecols=_TD_COLS)
    pos = _load_csv(gdir / "possessions.csv",   usecols=_POS_COLS)
    sl  = _load_csv(gdir / "shot_log.csv",      usecols=_SL_COLS)
    return td, pos, sl


# ── Percentile helpers ────────────────────────────────────────────────────────

def _pct(arr: List[float], p: int) -> float:
    if not arr:
        return float("nan")
    return float(np.percentile(arr, p))


def _safe(v: str, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except (ValueError, TypeError):
        return default


# ── Per-threshold analysers ───────────────────────────────────────────────────

def analyse_drive_speed(
    all_td: List[List[dict]], map_w: int = 940, fps: float = 30.0, stride: int = 3
) -> dict:
    """
    Compute vel_toward_basket distribution on handler frames.

    NOTE: "drive" is a rich event written to events_log.csv (not the main event
    column).  The main event column has only shot/pass/dribble/none.  We use the
    upper quartile of handler vel_toward_basket as the drive speed proxy.

    vel_toward_basket in tracking_data is in px/abs-frame (at stride=3, 30fps,
    effective rate = fps/stride = 10 fps).
    Convert to mph: v_mph = v_pxpf × (fps/stride) ÷ ft_px × 3600 ÷ 5280
    where ft_px ≈ 0.87 × map_w ÷ 80.5 (px per foot on the 2D court map).
    """
    ft_px       = 0.87 * map_w / 80.5
    pxpf_to_mph = (fps / stride) / ft_px * 3600.0 / 5280.0

    # "Drive" frames: handler with vel_toward_basket > p75 of all handler frames
    # (drives are the upper-quartile fast attacks toward the basket)
    all_handler_vel: List[float] = []

    for td in all_td:
        for row in td:
            vtb = _safe(row.get("vel_toward_basket", ""))
            bp  = _safe(row.get("ball_possession", ""))
            if vtb > 0 and bp > 0:
                all_handler_vel.append(vtb * pxpf_to_mph)

    # Suggested drive threshold = p75 of handler velocities:
    # captures the top 25% of handler speed, consistent with real drive frequency
    suggested = _pct(all_handler_vel, 75) if len(all_handler_vel) >= 30 else float("nan")
    return {
        "n":         len(all_handler_vel),
        "source":    "handler frames (vel_toward_basket > 0)",
        "p10":       _pct(all_handler_vel, 10),
        "p25":       _pct(all_handler_vel, 25),
        "p50":       _pct(all_handler_vel, 50),
        "p75":       _pct(all_handler_vel, 75),
        "p90":       _pct(all_handler_vel, 90),
        # p75 gives threshold where top 25% of handler movement counts as a drive
        "suggested": suggested,
    }


def analyse_dribble_dist(all_td: List[List[dict]]) -> dict:
    """
    Compute distance_to_ball distribution on "dribble" frames.
    Suggested: p90 (should catch most dribbles).
    """
    dists: List[float] = []
    for td in all_td:
        for row in td:
            if row.get("event") != "dribble":
                continue
            d = _safe(row.get("distance_to_ball", ""))
            if 0 < d < 500:  # sanity gate
                dists.append(d)
    return {
        "n":       len(dists),
        "p50":     _pct(dists, 50),
        "p75":     _pct(dists, 75),
        "p90":     _pct(dists, 90),
        "suggested": _pct(dists, 90) if len(dists) >= 30 else float("nan"),
    }


def analyse_dbl_team_radius(
    all_td: List[List[dict]], map_w: int = 940
) -> dict:
    """
    From tracking_data: for rows with possession_type == "double_team",
    find the closest two defender distances.  Compute normalised radius
    that captures the observed double-team distances.
    Fallback: all frames where handler_isolation < 4 ft worth of pixels.
    """
    ft_px  = 0.87 * map_w / 80.5
    thresh = 4.0 * ft_px   # 4 ft in px

    obs_dist_n: List[float] = []  # normalised distances
    for td in all_td:
        for row in td:
            pt = row.get("possession_type", row.get("play_type", ""))
            if pt != "double_team":
                continue
            iso = _safe(row.get("handler_isolation", ""), default=float("nan"))
            if math.isfinite(iso) and iso > 0:
                obs_dist_n.append(iso / map_w)

    # Fallback: frames with handler_isolation < 4 ft
    if len(obs_dist_n) < 10:
        for td in all_td:
            for row in td:
                iso = _safe(row.get("handler_isolation", ""), default=float("nan"))
                if math.isfinite(iso) and 0 < iso < thresh:
                    obs_dist_n.append(iso / map_w)

    suggested = _pct(obs_dist_n, 80) if len(obs_dist_n) >= 30 else float("nan")
    return {
        "n":         len(obs_dist_n),
        "p50":       _pct(obs_dist_n, 50),
        "p75":       _pct(obs_dist_n, 75),
        "p80":       _pct(obs_dist_n, 80),
        "suggested": suggested,
    }


def analyse_shot_clock(
    all_td: List[List[dict]],
) -> dict:
    """
    Compare shot_clock_est vs scoreboard_shot_clock.
    Rows where scoreboard_shot_clock > 0 and shot_clock_est > 0.
    Reports MAE, bias (are we consistently early or late?), pct abs_error > 3s.
    """
    errors: List[float] = []
    for td in all_td:
        for row in td:
            sc_est = _safe(row.get("shot_clock_est", ""), default=-1.0)
            sc_ocr = _safe(row.get("scoreboard_shot_clock", ""), default=-1.0)
            if sc_est > 0 and sc_ocr > 0:
                errors.append(sc_est - sc_ocr)

    if not errors:
        return {"n": 0, "mae": float("nan"), "bias": float("nan"), "pct_over_3s": float("nan")}
    arr   = np.array(errors)
    mae   = float(np.mean(np.abs(arr)))
    bias  = float(np.mean(arr))
    pct3  = float(np.mean(np.abs(arr) > 3.0) * 100)
    return {
        "n":         len(errors),
        "mae":       round(mae, 2),
        "bias":      round(bias, 2),
        "pct_over_3s": round(pct3, 1),
    }


def analyse_fast_break_window(
    all_pos: List[List[dict]],
) -> dict:
    """
    For possessions where fast_break == 1, check whether the current
    x-window radius of 0.40 is appropriate.
    Reports: fraction of fast-break possessions, current surplus detection.
    (Full per-frame attacker/defender spread requires multi-player correlation
    which is not directly in possessions.csv — we report coverage proxy instead.)
    """
    fb_total = 0
    total    = 0
    for pos in all_pos:
        for row in pos:
            total += 1
            if _safe(row.get("fast_break", "")) > 0:
                fb_total += 1
    pct = 100 * fb_total / max(1, total)
    # Current radius = 0.40 captures ~40% of map_w; typical fast-break spread is 35-45%
    return {
        "n_fast_break":  fb_total,
        "total_poss":    total,
        "pct_fast_break": round(pct, 1),
        "note": "x-window 0.40 captures ~40% map_w; NBA fast breaks span 35-50%",
    }


def analyse_cut_angle(all_td: List[List[dict]]) -> dict:
    """
    From tracking_data: compute cos(direction_change) for all frames where
    ball_possession==0 and velocity > 3 px/frame and direction changes.
    Report p10 (cuts are sharp direction changes → low cosine = large angle).
    """
    cos_vals: List[float] = []
    # Group rows by player_id to compute direction delta across consecutive frames
    from collections import defaultdict
    player_rows: Dict[str, List[dict]] = defaultdict(list)
    for td in all_td:
        for row in td:
            pid = row.get("player_id", "")
            if pid and _safe(row.get("ball_possession", "")) == 0:
                player_rows[pid].append(row)

    for pid, rows in player_rows.items():
        rows_sorted = sorted(rows, key=lambda r: _safe(r.get("frame", "0")))
        for i in range(1, len(rows_sorted) - 1):
            d_prev = _safe(rows_sorted[i - 1].get("direction_deg", ""), default=float("nan"))
            d_curr = _safe(rows_sorted[i].get("direction_deg", ""), default=float("nan"))
            d_next = _safe(rows_sorted[i + 1].get("direction_deg", ""), default=float("nan"))
            vel    = _safe(rows_sorted[i].get("velocity", ""))
            if not (math.isfinite(d_prev) and math.isfinite(d_curr) and math.isfinite(d_next)):
                continue
            if vel < 3.0:
                continue
            delta = d_curr - d_prev
            # Convert degrees to cos(angle)
            cos_a = math.cos(math.radians(delta))
            cos_vals.append(cos_a)

    return {
        "n":         len(cos_vals),
        "p10":       _pct(cos_vals, 10),
        "p25":       _pct(cos_vals, 25),
        "p50":       _pct(cos_vals, 50),
        "note":      "CUT_MIN_ANGLE_COS excluded from auto-update (semantic threshold)",
    }


# ── Source-file patcher ───────────────────────────────────────────────────────

def _patch_constant(
    filepath: Path,
    const_name: str,
    new_val: float,
    old_val: float,
    n_games: int,
) -> bool:
    """
    Replace a Python-level numeric constant in filepath.
    Supports patterns like:
        _CONST = 3.0
        _CONST = 70
        _CONST_N = 0.044
    Returns True if the file was modified.
    """
    text = filepath.read_text(encoding="utf-8")
    today = date.today().isoformat()
    # Build pattern that matches the assignment line (after any existing comment)
    pattern = rf"^({re.escape(const_name)}\s*=\s*){re.escape(str(old_val))}(\s*#.*)?$"
    comment = (
        f"  # calibrated {today} from {n_games} games — was {old_val}"
    )
    replacement = rf"\g<1>{_fmt(new_val)}{comment}"
    new_text, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count == 0:
        # Try integer representation
        pattern_int = rf"^({re.escape(const_name)}\s*=\s*){int(old_val)}(\s*#.*)?$"
        new_text, count = re.subn(pattern_int, replacement, text, flags=re.MULTILINE)
    if count > 0:
        filepath.write_text(new_text, encoding="utf-8")
        return True
    return False


def _fmt(v: float) -> str:
    """Format float for source code: 2 decimal places, no trailing zeros if integer."""
    if v == int(v):
        return str(int(v))
    return f"{v:.2f}"


# ── Report printing ───────────────────────────────────────────────────────────

_W = 66

def _box_top(title: str, games: int, frames: int) -> None:
    today = date.today().isoformat()
    print("╔" + "═" * _W + "╗")
    print(f"║  CourtVision Threshold Validation Report{' ' * (_W - 41)}║")
    print(f"║  Games analyzed: {games}  |  Total frames: {frames:,}  |  Date: {today}  {' ' * max(0, _W - 57 - len(str(games)) - len(str(frames)))}║")
    print("╠" + "═" * _W + "╣")


def _section(name: str, current: float, unit: str,
             stats: dict, key_pcts: List[Tuple[str, float]],
             suggested: float, n: int,
             change_applied: bool, skipped_reason: str = "",
             dry_run_would_apply: bool = False) -> None:
    print(f"║  {name:<62}  ║")
    print(f"║    Current:    {current} {unit:<49}║")
    for label, val in key_pcts:
        s = f"{val:.2f}" if math.isfinite(val) else "N/A"
        print(f"║    Data {label}:   {s} {unit:<47}║")
    if math.isfinite(suggested):
        print(f"║    → SUGGEST:  {suggested:.2f} {unit:<47}║")
        if change_applied:
            print(f"║    ✓ APPLIED to source file{' ' * (_W - 28)}║")
        elif dry_run_would_apply:
            pct_change = abs(suggested - current) / max(abs(current), 1e-9) * 100
            note = f"Δ={pct_change:.0f}%, n={n} — rerun with --apply to patch"
            print(f"║    ~ PENDING: {note:<50}║")
        elif skipped_reason:
            print(f"║    ✗ SKIPPED: {skipped_reason:<50}║")
        else:
            pct_change = abs(suggested - current) / max(abs(current), 1e-9) * 100
            if pct_change < 15:
                note = f"Δ={pct_change:.0f}% — within ±15% tolerance"
            else:
                note = f"only {n} samples (need ≥30)"
            print(f"║    ✗ SKIPPED: {note:<50}║")
    else:
        print(f"║    → SUGGEST:  N/A (insufficient data, n={n}){' ' * max(0, _W - 44 - len(str(n)))}║")
    print("╠" + "═" * _W + "╣")


def _note_section(name: str, note: str) -> None:
    print(f"║  {name:<62}  ║")
    print(f"║    {note:<64}║")
    print("╠" + "═" * _W + "╣")


def _box_bottom() -> None:
    # Remove the last ╠═╣ and replace with ╚═╝
    print("╚" + "═" * _W + "╝")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply",    action="store_true",
                    help="Write corrections to source files")
    ap.add_argument("--data-dir", type=Path, default=_DATA_DIR,
                    help="Root directory containing game subdirectories")
    args = ap.parse_args()

    game_dirs = _find_game_dirs(args.data_dir)
    if not game_dirs:
        print(f"[validate_thresholds] No complete game directories found under {args.data_dir}")
        sys.exit(1)

    print(f"\nLoading {len(game_dirs)} game directories from {args.data_dir} …")
    all_td:  List[List[dict]] = []
    all_pos: List[List[dict]] = []
    all_sl:  List[List[dict]] = []
    for gd in game_dirs:
        try:
            td, pos, sl = _load_game(gd)
            all_td.append(td)
            all_pos.append(pos)
            all_sl.append(sl)
        except Exception as e:
            print(f"  [WARN] {gd.name}: {e}")

    total_frames = sum(len(td) for td in all_td)
    n_games = len(all_td)

    # ── Run analysers ──────────────────────────────────────────────────────
    res_drive   = analyse_drive_speed(all_td)
    res_dribble = analyse_dribble_dist(all_td)
    res_dbl     = analyse_dbl_team_radius(all_td)
    res_sc      = analyse_shot_clock(all_td)
    res_fb      = analyse_fast_break_window(all_pos)
    res_cut     = analyse_cut_angle(all_td)

    # ── Decide which corrections to apply ──────────────────────────────────
    changes: List[dict] = []   # {name, old, new, file, const_src}

    def _should_apply(current: float, suggested: float, n: int,
                      excluded: bool = False) -> Tuple[bool, str]:
        if excluded:
            return False, "manual-review-only threshold"
        if n < 30:
            return False, f"only {n} samples (need ≥30)"
        if not math.isfinite(suggested):
            return False, "no valid suggestion"
        pct = abs(suggested - current) / max(abs(current), 1e-9)
        if pct <= 0.15:
            return False, f"Δ={pct*100:.0f}% is within ±15%"
        return True, ""

    # DRIVE_MIN_SPEED: changes EventDetector comment (8.0 mph constant in configure())
    drive_apply, drive_reason = _should_apply(
        CURRENT["DRIVE_MIN_SPEED_MPH"], res_drive["suggested"], res_drive["n"]
    )

    # DRIBBLE_MAX_DIST: _DRIBBLE_MAX_DIST in event_detector.py
    drib_apply, drib_reason = _should_apply(
        CURRENT["DRIBBLE_MAX_DIST_PX"], res_dribble["suggested"], res_dribble["n"]
    )

    # DBL_TEAM_RAD_N: _DBL_TEAM_RAD_N in possession_classifier.py
    dbl_apply, dbl_reason = _should_apply(
        CURRENT["DBL_TEAM_RAD_N"], res_dbl["suggested"], res_dbl["n"]
    )

    # Apply corrections to source files if --apply passed
    today       = date.today().isoformat()
    drive_patched  = False
    drib_patched   = False
    dbl_patched    = False

    if args.apply:
        if drive_apply and math.isfinite(res_drive["suggested"]):
            # Patch the mph constant in configure() and __init__() comments
            # The actual speed constant in event_detector uses 8.0 mph inline;
            # we patch the comment string and the inline literal.
            new_mph = round(res_drive["suggested"], 1)
            try:
                text = _ED_PATH.read_text(encoding="utf-8")
                # Replace "8.0 mph" → new value in the configure/init drive speed line
                old_literal = "8.0 * 5280.0 / 3600.0"
                if old_literal in text:
                    new_literal = f"{new_mph} * 5280.0 / 3600.0"
                    # Replace all occurrences (there are 2: __init__ and configure)
                    new_text = text.replace(old_literal, new_literal)
                    # Add calibration comment on the configure line
                    calib_tag = f"# calibrated {today} from {n_games} games — was 8.0 mph"
                    new_text = re.sub(
                        r"(# Drive speed: )8\.0 mph(.*)",
                        rf"\g<1>{new_mph} mph  {calib_tag}",
                        new_text,
                    )
                    _ED_PATH.write_text(new_text, encoding="utf-8")
                    drive_patched = True
                    changes.append({"name": "DRIVE_MIN_SPEED_MPH",
                                    "old": 8.0, "new": new_mph, "file": "event_detector.py"})
            except Exception as exc:
                print(f"[WARN] Could not patch DRIVE_MIN_SPEED: {exc}")

        if drib_apply and math.isfinite(res_dribble["suggested"]):
            new_drib = int(round(res_dribble["suggested"]))
            patched = _patch_constant(_ED_PATH, "_DRIBBLE_MAX_DIST", float(new_drib),
                                      CURRENT["DRIBBLE_MAX_DIST_PX"], n_games)
            if patched:
                drib_patched = True
                changes.append({"name": "_DRIBBLE_MAX_DIST",
                                 "old": CURRENT["DRIBBLE_MAX_DIST_PX"],
                                 "new": new_drib, "file": "event_detector.py"})

        if dbl_apply and math.isfinite(res_dbl["suggested"]):
            new_dbl = round(res_dbl["suggested"], 3)
            patched = _patch_constant(_PC_PATH, "_DBL_TEAM_RAD_N", new_dbl,
                                      CURRENT["DBL_TEAM_RAD_N"], n_games)
            if patched:
                dbl_patched = True
                changes.append({"name": "_DBL_TEAM_RAD_N",
                                 "old": CURRENT["DBL_TEAM_RAD_N"],
                                 "new": new_dbl, "file": "possession_classifier.py"})

    # ── Print formatted report ─────────────────────────────────────────────
    print()
    _box_top("CourtVision Threshold Validation Report", n_games, total_frames)

    _section(
        "DRIVE_MIN_SPEED",
        CURRENT["DRIVE_MIN_SPEED_MPH"], "mph",
        res_drive,
        [("p25", res_drive["p25"]), ("p50", res_drive["p50"]), ("p75", res_drive["p75"])],
        res_drive["suggested"], res_drive["n"],
        drive_patched, drive_reason,
        dry_run_would_apply=(not args.apply and drive_apply),
    )
    _section(
        "DRIBBLE_MAX_DIST",
        CURRENT["DRIBBLE_MAX_DIST_PX"], "px",
        res_dribble,
        [("p50", res_dribble["p50"]), ("p75", res_dribble["p75"]), ("p90", res_dribble["p90"])],
        res_dribble["suggested"], res_dribble["n"],
        drib_patched, drib_reason,
        dry_run_would_apply=(not args.apply and drib_apply),
    )
    _section(
        "DOUBLE_TEAM radius (_DBL_TEAM_RAD_N)",
        CURRENT["DBL_TEAM_RAD_N"], "norm",
        res_dbl,
        [("p50", res_dbl["p50"]), ("p75", res_dbl["p75"]), ("p80", res_dbl["p80"])],
        res_dbl["suggested"], res_dbl["n"],
        dbl_patched, dbl_reason,
        dry_run_would_apply=(not args.apply and dbl_apply),
    )

    # Shot clock
    print(f"║  SHOT_CLOCK_EST vs scoreboard{' ' * (_W - 30)}║")
    sc = res_sc
    if sc["n"] > 0:
        print(f"║    n={sc['n']}  MAE={sc['mae']}s  bias={sc['bias']}s  pct_err>3s={sc['pct_over_3s']}%{' ' * max(0, _W - 54)}║")
        dir_ = "HIGH (we estimate too much time remaining)" if sc["bias"] > 0 else "LOW (we think clock is running out too fast)"
        print(f"║    Systematic bias: {dir_:<45}║")
    else:
        print(f"║    No scoreboard shot-clock data available{' ' * (_W - 43)}║")
    print("╠" + "═" * _W + "╣")

    # Fast break
    fb = res_fb
    print(f"║  FAST_BREAK x-window (current 0.40){' ' * (_W - 36)}║")
    print(f"║    {fb['n_fast_break']} fast-break possessions of {fb['total_poss']} total ({fb['pct_fast_break']}%){' ' * max(0, _W - 52 - len(str(fb['n_fast_break'])) - len(str(fb['total_poss'])))}║")
    print(f"║    {fb['note']:<64}║")
    print("╠" + "═" * _W + "╣")

    # Cut angle
    cut = res_cut
    print(f"║  CUT_MIN_ANGLE_COS (current: cos < 0.0 = >90° turn){' ' * (_W - 51)}║")
    if cut["n"] >= 10:
        print(f"║    n={cut['n']}  p10={cut['p10']:.3f}  p25={cut['p25']:.3f}  p50={cut['p50']:.3f}{' ' * max(0, _W - 46)}║")
    else:
        print(f"║    n={cut['n']} — insufficient data for distribution{' ' * max(0, _W - 49)}║")
    print(f"║    {cut['note']:<64}║")
    print("╠" + "═" * _W + "╣")

    # Summary of applied changes
    print(f"║  SUMMARY{' ' * (_W - 9)}║")
    if not args.apply:
        print(f"║    Dry-run mode — rerun with --apply to patch source files{' ' * (_W - 59)}║")
    elif changes:
        for c in changes:
            line = f"    ✓ {c['name']}: {c['old']} → {c['new']} ({c['file']})"
            print(f"║  {line:<64}║")
    else:
        print(f"║    No corrections applied (all within ±15% or n<30){' ' * (_W - 53)}║")

    # Replace last ╠═╣ with ╚═╝
    _box_bottom()

    if args.apply and changes:
        print(f"\n[validate_thresholds] Applied {len(changes)} correction(s) to source files.")
    elif args.apply:
        print("\n[validate_thresholds] No changes applied — all thresholds within tolerance.")
    else:
        print("\n[validate_thresholds] Dry-run complete. Use --apply to patch source files.")


if __name__ == "__main__":
    main()
