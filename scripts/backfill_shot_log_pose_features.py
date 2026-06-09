"""P6 (2026-05-29): backfill contest_arm_angle + dribble_count in shot_log.csv from per-frame data.

Bug 35 family: the shot-time write in `unified_pipeline.py:~2566` reads pose data
from frame_tracks at the EXACT shot frame. Per-frame measurement shows:
  contest_arm_angle  per-frame: 34.5% nonzero  /  shot_log: 3.7%  (10x miss)
  dribble_hand       per-frame: 100% populated /  shot_log dribble_count: 2.3%

The signal IS in tracking_data.csv. The shot-time point-lookup is the bug.

Fix: scan a [shot_frame - 45, shot_frame + 5] window (1.5s before through release)
for each shot:
  - contest_arm_angle: max across defender rows within 8ft of shooter in the window
  - dribble_count: distinct frames where shooter has dribble_hand populated in
    [shot_frame - 60, shot_frame] (2s before — typical pre-shot dribble burst)

Usage:
  python scripts/backfill_shot_log_pose_features.py
  python scripts/backfill_shot_log_pose_features.py --game-id 0022400909
  python scripts/backfill_shot_log_pose_features.py --dry-run
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
TRACKING_DIR = ROOT / "data" / "tracking"
GAMES_DIR = ROOT / "data" / "games"

# P6 fix v2 (2026-05-29): tracking_data.csv's `x_position`/`y_position` are
# IMAGE-pixel coords (max ~2500), while shot_log.csv `x_position`/`y_position`
# are court-map coords (940 px wide, 18.8 px/ft per tracking_feature_extractor).
# Use `ft_x`/`ft_y` from tracking_data (0-94 ft / 0-50 ft) for the distance
# check; convert shot_log px to ft via /18.8.
_PX_PER_FT = 18.8           # shot_log px -> ft conversion (940 px = 50 ft)
# P21 (2026-05-30): widened 8.0 -> 10.0 ft. contest_arm_angle was stuck at 8.6%
# nonzero in cv_features despite per-frame arm-angle data being 34.5% available.
# Homography/position noise puts a true ~6-8 ft contest at a MEASURED ~9-11 ft, so
# the 8 ft gate dropped genuine contests. 10 ft recovers them while staying inside
# the contest band (the max-arm-angle aggregation already biases toward the
# closest/most-contesting defender, limiting open-shot false positives). Validated
# by dry-run differential before committing to a full backfill.
_CONTEST_FT = 10.0
_CONTEST_FT_SQ = _CONTEST_FT * _CONTEST_FT  # ft² comparison

_CONTEST_WINDOW_BEFORE = 45  # 1.5s @ 30fps before shot
_CONTEST_WINDOW_AFTER = 5    # 0.17s @ 30fps after (late closeout)
_DRIBBLE_WINDOW_BEFORE = 60  # 2.0s @ 30fps before shot
# P8 historical (2026-05-29): closeout speed from defender position history
_CLOSEOUT_LOOKBACK = 45      # 1.5s window for closeout
_CLOSEOUT_MIN_DELTA_FT = 2.0 # defender must close at least 2 ft
_CLOSEOUT_MAX_END_FT = 7.0   # defender must end within 7 ft of shooter
_FPS = 30.0
_MPH_PER_FTPS = 3600.0 / 5280.0  # ft/s -> mph


def _build_frame_index(tracking_path: str) -> Dict[int, List[dict]]:
    """Return {frame: [row, row, ...]}.

    Rows preserve the minimal fields we need: player_id (slot), team, x2d, y2d,
    contest_arm_angle, dribble_hand.
    """
    by_frame: Dict[int, List[dict]] = defaultdict(list)
    if not os.path.exists(tracking_path):
        return by_frame
    try:
        with open(tracking_path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    fr = int(float(row.get("frame", "") or 0))
                except (ValueError, TypeError):
                    continue
                if fr <= 0:
                    continue
                try:
                    pid = int(float(row.get("player_id", "") or 0))
                except (ValueError, TypeError):
                    pid = 0
                if pid <= 0:
                    continue
                # Use ft_x / ft_y (court feet) — x_position/y_position are image-pixel.
                try:
                    x = float(row.get("ft_x", "") or 0)
                    y = float(row.get("ft_y", "") or 0)
                except (ValueError, TypeError):
                    continue
                if x <= 0 and y <= 0:
                    continue
                cam = row.get("contest_arm_angle", "")
                try:
                    cam_v = float(cam) if cam not in ("", None, "nan") else None
                except (ValueError, TypeError):
                    cam_v = None
                dh = row.get("dribble_hand", "")
                team = str(row.get("team", "")).strip()
                by_frame[fr].append({
                    "pid": pid,
                    "team": team,
                    "x": x,
                    "y": y,
                    "cam": cam_v,
                    "dh": dh if dh not in ("", None, "nan") else None,
                })
    except Exception:
        pass
    return by_frame


def _compute_features_for_shot(
    shot_frame: int,
    shooter_slot: int,
    shooter_team: str,
    by_frame: Dict[int, List[dict]],
) -> Tuple[float, int, int]:
    """Return (best_contest_arm_angle, dribble_count, nearest_defender_slot) for one shot.

    P5-historical extension: emits defender_slot_id even for shots that pre-date
    the P5 write-time fix. nearest_defender_slot is the slot of the closest
    opposing-team track within 8 ft at the shot frame; "" if no defender visible.
    """
    # Find shooter position (in court feet) around shot frame.
    # Use closest frame within ±5 with valid shooter row.
    shooter_pos = None
    for off in range(0, 6):
        for fr in (shot_frame - off, shot_frame + off):
            for row in by_frame.get(fr, ()):
                if row["pid"] == shooter_slot:
                    shooter_pos = (row["x"], row["y"])  # ft_x, ft_y
                    break
            if shooter_pos:
                break
        if shooter_pos:
            break

    best_cam = 0.0
    have_cam = False
    # Nearest defender at shot frame (P5 historical fill)
    nearest_def_slot = ""
    nearest_def_dist_sq = float("inf")
    if shooter_pos is not None:
        sx, sy = shooter_pos  # in feet
        for fr in range(
            shot_frame - _CONTEST_WINDOW_BEFORE,
            shot_frame + _CONTEST_WINDOW_AFTER + 1,
        ):
            for row in by_frame.get(fr, ()):
                if row["pid"] == shooter_slot:
                    continue
                # Opposing team check (same colour label is teammate)
                if row["team"] and shooter_team and row["team"] == shooter_team:
                    continue
                if row["team"] in (None, "referee", ""):
                    continue
                dx = row["x"] - sx  # ft difference
                dy = row["y"] - sy
                dsq = dx * dx + dy * dy
                if dsq > _CONTEST_FT_SQ:
                    continue
                # Track nearest defender (within window) for defender_slot_id fill
                if dsq < nearest_def_dist_sq:
                    nearest_def_dist_sq = dsq
                    nearest_def_slot = row["pid"]
                if row["cam"] is None:
                    continue
                if row["cam"] > best_cam:
                    best_cam = row["cam"]
                    have_cam = True

    # Dribble count: distinct frames where shooter has dribble_hand populated
    dribble_frames = set()
    for fr in range(shot_frame - _DRIBBLE_WINDOW_BEFORE, shot_frame + 1):
        for row in by_frame.get(fr, ()):
            if row["pid"] == shooter_slot and row["dh"] is not None:
                dribble_frames.add(fr)
                break

    cam_out = round(best_cam, 3) if have_cam else 0.0

    # P8 historical: compute closeout speed for the nearest defender (if any).
    # Walk back from shot frame, find the same defender slot earlier in the
    # window, and compute how much they closed and at what speed.
    closeout_speed = 0.0
    if shooter_pos is not None and nearest_def_slot != "" and nearest_def_slot != 0:
        sx, sy = shooter_pos  # in feet
        # End position: defender position at shot frame
        def_end_pos = None
        for off in range(0, 6):
            for fr in (shot_frame - off, shot_frame + off):
                for row in by_frame.get(fr, ()):
                    if row["pid"] == nearest_def_slot:
                        def_end_pos = (row["x"], row["y"], fr)
                        break
                if def_end_pos:
                    break
            if def_end_pos:
                break
        # Start position: defender earliest entry within lookback window
        def_start_pos = None
        for fr in range(shot_frame - _CLOSEOUT_LOOKBACK, shot_frame):
            for row in by_frame.get(fr, ()):
                if row["pid"] == nearest_def_slot:
                    def_start_pos = (row["x"], row["y"], fr)
                    break
            if def_start_pos:
                break
        if def_start_pos and def_end_pos and def_end_pos[2] > def_start_pos[2]:
            sx0, sy0, fr0 = def_start_pos
            sx1, sy1, fr1 = def_end_pos
            dist_then = math.hypot(sx0 - sx, sy0 - sy)
            dist_now = math.hypot(sx1 - sx, sy1 - sy)
            delta = dist_then - dist_now
            if delta >= _CLOSEOUT_MIN_DELTA_FT and dist_now <= _CLOSEOUT_MAX_END_FT:
                # Average speed of defender over the closing window
                travel = math.hypot(sx1 - sx0, sy1 - sy0)
                dt_s = max((fr1 - fr0) / _FPS, 0.1)
                ftps = travel / dt_s
                closeout_speed = round(ftps * _MPH_PER_FTPS, 2)

    return cam_out, len(dribble_frames), nearest_def_slot, closeout_speed


def backfill_game(game_dir: str, dry_run: bool) -> Tuple[int, int, int, int, int]:
    """Return (shots_total, contest_filled, contest_was_zero, dribble_filled, dribble_was_zero).

    P6-enriched extension 2026-05-29: also rewrites shot_log_enriched.csv (NBA-enricher
    output) so downstream consumers that join on the enriched file pick up the new
    pose-features. Tracking_data scan is shared between both files.
    """
    shot_path = os.path.join(game_dir, "shot_log.csv")
    tracking_path = os.path.join(game_dir, "tracking_data.csv")
    if not os.path.exists(shot_path) or not os.path.exists(tracking_path):
        return 0, 0, 0, 0, 0

    with open(shot_path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if not rows:
        return 0, 0, 0, 0, 0

    needed = {"frame", "player_id", "team"}
    if not needed.issubset(set(fieldnames)):
        return 0, 0, 0, 0, 0

    by_frame = _build_frame_index(tracking_path)
    if not by_frame:
        return len(rows), 0, 0, 0, 0

    if "contest_arm_angle" not in fieldnames:
        return 0, 0, 0, 0, 0  # column should already exist; if not, this is a no-op

    # P5 historical extension: add defender_slot_id column if missing
    if "defender_slot_id" not in fieldnames:
        try:
            idx = fieldnames.index("defender_dist_norm") + 1
        except ValueError:
            idx = len(fieldnames)
        fieldnames.insert(idx, "defender_slot_id")

    contest_filled = 0
    contest_was_zero = 0
    dribble_filled = 0
    dribble_was_zero = 0

    for row in rows:
        try:
            fr = int(float(row.get("frame", "") or 0))
            slot = int(float(row.get("player_id", "") or 0))
        except (ValueError, TypeError):
            continue
        if fr <= 0 or slot <= 0:
            continue
        team = str(row.get("team", "")).strip()

        # Current values to detect whether we improve
        try:
            cur_cam = float(row.get("contest_arm_angle", "") or 0)
        except (ValueError, TypeError):
            cur_cam = 0.0
        try:
            cur_dc = int(float(row.get("dribble_count", "") or 0))
        except (ValueError, TypeError):
            cur_dc = 0
        cur_def_slot = str(row.get("defender_slot_id", "") or "").strip()

        new_cam, new_dc, new_def_slot, new_closeout = _compute_features_for_shot(
            fr, slot, team, by_frame
        )

        # Only overwrite when we have a stronger signal — keep OCR/EventDetector
        # values when they're already populated.
        if cur_cam <= 0 and new_cam > 0:
            row["contest_arm_angle"] = str(new_cam)
            contest_filled += 1
        elif cur_cam <= 0:
            contest_was_zero += 1

        if cur_dc <= 0 and new_dc > 0:
            row["dribble_count"] = str(new_dc)
            dribble_filled += 1
        elif cur_dc <= 0:
            dribble_was_zero += 1

        # P5 historical: fill defender_slot_id when missing
        if cur_def_slot in ("", "0") and new_def_slot:
            row["defender_slot_id"] = str(new_def_slot)
            row["_def_was_filled"] = "1"  # transient marker stripped before write

        # P8 historical: fill closeout_speed when 0/empty and a real closeout was detected.
        # closeout_speed is in MPH; preserve any value the in-pipeline detector wrote.
        try:
            cur_closeout = float(row.get("closeout_speed", "") or 0)
        except (ValueError, TypeError):
            cur_closeout = 0.0
        if cur_closeout <= 0 and new_closeout > 0:
            row["closeout_speed"] = str(new_closeout)
            row["_def_was_filled"] = "1"  # reuse the write trigger marker

    # Also write when ANY row got a defender_slot_id fill (P5 historical)
    any_def_filled = any(r.pop("_def_was_filled", "") for r in rows)
    if not dry_run and (contest_filled > 0 or dribble_filled > 0 or any_def_filled):
        with open(shot_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    # P6-enriched extension 2026-05-29: ALWAYS sync the pose-feature columns
    # from shot_log.csv (just read or just written) into shot_log_enriched.csv —
    # even when shot_log itself didn't need rewriting. Downstream consumers join
    # on the enriched file and were getting stale values where contest/dribble
    # had been added to shot_log by an earlier backfill pass but the enriched
    # file was still pre-P6 (1% nonzero).
    if not dry_run:
        _sync_enriched_from_rows(game_dir, rows)

    return len(rows), contest_filled, contest_was_zero, dribble_filled, dribble_was_zero


def _sync_enriched_from_rows(game_dir, source_rows):
    """Copy contest_arm_angle / dribble_count / defender_slot_id / closeout_speed
    from source_rows (just-written shot_log.csv) into shot_log_enriched.csv.

    Match by (frame, player_id, shot_id) when present — falls back to (frame, player_id).
    Idempotent: only overwrites the target row's cell when source has a stronger value.
    """
    enriched_path = os.path.join(game_dir, "shot_log_enriched.csv")
    if not os.path.exists(enriched_path):
        return
    try:
        with open(enriched_path, newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            e_fields = list(reader.fieldnames or [])
            e_rows = list(reader)
        if not e_rows:
            return
        # Add P5 column if missing in enriched too
        if "defender_slot_id" not in e_fields and "defender_slot_id" in (
            source_rows[0].keys() if source_rows else ()
        ):
            try:
                idx = e_fields.index("defender_dist_norm") + 1
            except ValueError:
                idx = len(e_fields)
            e_fields.insert(idx, "defender_slot_id")
        # Build index of source rows
        def _key(r):
            return (
                str(r.get("frame", "")).strip(),
                str(r.get("player_id", "")).strip(),
                str(r.get("shot_id", "")).strip(),
            )
        src_by_key = {_key(r): r for r in source_rows}
        updated = 0
        for e_row in e_rows:
            k = _key(e_row)
            src = src_by_key.get(k)
            if src is None:
                # Fallback to (frame, player_id) match
                k2 = (k[0], k[1], "")
                src = src_by_key.get(k2)
                if src is None:
                    # Search by (frame, player_id) only
                    for sk, sr in src_by_key.items():
                        if sk[0] == k[0] and sk[1] == k[1]:
                            src = sr
                            break
            if src is None:
                continue
            for col in (
                "contest_arm_angle", "dribble_count",
                "defender_slot_id", "closeout_speed",
            ):
                v = src.get(col, "")
                cur = (e_row.get(col, "") or "").strip()
                if v not in ("", None) and cur in ("", "0", "0.0"):
                    e_row[col] = v
                    updated += 1
        if updated > 0:
            _tmp = enriched_path + ".tmp"
            with open(_tmp, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=e_fields, extrasaction="ignore")
                w.writeheader()
                w.writerows(e_rows)
            os.replace(_tmp, enriched_path)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    targets = []
    if args.game_id:
        for base in (TRACKING_DIR, GAMES_DIR):
            d = base / args.game_id
            if d.is_dir():
                targets.append((args.game_id, str(d)))
    else:
        for base in (TRACKING_DIR, GAMES_DIR):
            if not base.is_dir():
                continue
            for d in sorted(base.iterdir()):
                if not d.is_dir() or d.name.startswith("_"):
                    continue
                targets.append((d.name, str(d)))
    if not targets:
        print("No tracking dirs found.")
        return 1

    print(f"Pose-features backfill: {len(targets)} game dirs (dry_run={args.dry_run})")

    total_shots = 0
    cam_filled = 0
    cam_zero = 0
    dc_filled = 0
    dc_zero = 0
    n_games = 0
    n_skip = 0

    for game_id, game_dir in targets:
        if args.limit and n_games >= args.limit:
            break
        try:
            s, cf, cz, df, dz = backfill_game(game_dir, args.dry_run)
        except Exception as exc:
            print(f"  {game_id}: ERROR {exc}")
            continue
        if s == 0:
            n_skip += 1
            continue
        n_games += 1
        total_shots += s
        cam_filled += cf
        cam_zero += cz
        dc_filled += df
        dc_zero += dz
        if n_games <= 20 or n_games % 50 == 0:
            print(
                f"  {game_id}: {s} shots; contest_arm_angle filled {cf} "
                f"(remained 0: {cz}); dribble_count filled {df} (remained 0: {dz})"
            )

    print()
    print("=" * 70)
    print(f"games processed   : {n_games}")
    print(f"games skipped     : {n_skip}")
    print(f"total shots       : {total_shots}")
    if total_shots:
        print(
            f"contest_arm_angle : filled {cam_filled} / total {total_shots} "
            f"({cam_filled/total_shots*100:.1f}%) — was 3.7% in shot_log baseline"
        )
        print(
            f"dribble_count     : filled {dc_filled} / total {total_shots} "
            f"({dc_filled/total_shots*100:.1f}%) — was 2.3% in shot_log baseline"
        )
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
