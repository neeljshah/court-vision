"""Possession-level defensive statistics from broadcast tracking + public PBP.

Ten defensive measures that have no box-score counterpart, computed per
possession from geometry only (no player identity required), then joined to
the possession outcome (points allowed) from play-by-play.

Usage:
    python -m scripts.platformkit.defensive_stats --games 20
    python -m scripts.platformkit.defensive_stats --all --out data/cache/def_stats.csv
"""
import argparse
import csv
import glob
import os
import sys
from collections import defaultdict

# ponytail: stdlib csv streaming, not pandas -- 4.5GB of CSV, row-at-a-time
# keeps memory flat and we only ever need per-possession aggregates.

PAINT_FT = 8.0        # distance_to_basket threshold treated as "at the rim"
DRIVE_VEL = 5.0       # vel_toward_basket that counts as attacking
ROTATION_FT = 6.0     # off_ball_distance jump that counts as leaving your man
LATE_CLOCK_SEC = 17.0 # possession duration past which offense is in trouble


def _f(v, default=0.0):
    try:
        x = float(v)
        return x if x == x else default  # NaN guard
    except (TypeError, ValueError):
        return default


def load_possessions(path):
    """possession_id -> dict(points, result, offense) for PBP-matched rows."""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, newline="", encoding="utf-8", errors="ignore") as fh:
        for r in csv.DictReader(fh):
            if str(r.get("pbp_matched", "")).lower() != "true":
                continue
            pid = (r.get("possession_id") or "").strip()
            pts = (r.get("outcome_score") or "").strip()
            if not pid or pts == "":
                continue
            out[pid] = {
                "points": _f(pts),
                "result": (r.get("result") or "").strip(),
                "offense": (r.get("team_abbrev") or "").strip(),
                "duration": _f(r.get("duration_sec")),
            }
    return out


def scan_game(track_path, poss):
    """Stream one game's frames, accumulate per-possession defensive features."""
    acc = defaultdict(lambda: {
        "frames": 0, "handler_frames": 0,
        "drive_frames": 0, "rim_frames": 0,
        "pressure_sum": 0.0, "pressure_n": 0,
        "paint_opp_sum": 0.0, "spacing_sum": 0.0, "spacing_n": 0,
        "contest_sum": 0.0, "contest_n": 0, "jumps": 0,
        "closeout_sum": 0.0, "closeout_n": 0,
        "rotations": 0, "offball_prev": {},
        "min_rim_dist": 99.0, "iso_sum": 0.0, "iso_n": 0,
    })
    with open(track_path, newline="", encoding="utf-8", errors="ignore") as fh:
        for row in csv.DictReader(fh):
            pid = (row.get("possession_id") or "").strip()
            if pid not in poss:
                continue
            if str(row.get("homography_valid", "")).strip() not in ("1", "True", "true"):
                continue
            a = acc[pid]
            a["frames"] += 1

            has_ball = str(row.get("ball_possession", "")).strip() == "1"
            rim = _f(row.get("distance_to_basket"), 99.0)
            vtb = _f(row.get("vel_toward_basket"))
            slot = (row.get("player_id") or "").strip()

            # --- ball-handler-side measures (defense is what resists them) ---
            if has_ball:
                a["handler_frames"] += 1
                if vtb >= DRIVE_VEL or str(row.get("drive_flag", "")).strip() == "1":
                    a["drive_frames"] += 1
                if rim <= PAINT_FT:
                    a["rim_frames"] += 1
                if rim < a["min_rim_dist"]:
                    a["min_rim_dist"] = rim
                nearest = _f(row.get("nearest_opponent"), 0.0)
                if nearest > 0:
                    a["pressure_sum"] += 1.0 / nearest
                    a["pressure_n"] += 1
                iso = _f(row.get("handler_isolation"), -1.0)
                if iso >= 0:
                    a["iso_sum"] += iso
                    a["iso_n"] += 1

            # --- defensive posture measures ---
            a["paint_opp_sum"] += _f(row.get("paint_count_opp"))
            sp = _f(row.get("team_spacing"), -1.0)
            if sp > 0:
                a["spacing_sum"] += sp
                a["spacing_n"] += 1

            arm = _f(row.get("contest_arm_angle"), -1.0)
            if arm > 0:
                a["contest_sum"] += arm
                a["contest_n"] += 1
            if str(row.get("jump_detected", "")).strip() == "1":
                a["jumps"] += 1

            # closeout: defender moving toward the basket-side ball fast
            if not has_ball and vtb > 0:
                a["closeout_sum"] += vtb
                a["closeout_n"] += 1

            # rotation: a defender's distance from their man jumps sharply
            obd = _f(row.get("off_ball_distance"), -1.0)
            if obd >= 0 and slot:
                prev = a["offball_prev"].get(slot)
                if prev is not None and (obd - prev) >= ROTATION_FT:
                    a["rotations"] += 1
                a["offball_prev"][slot] = obd
    return acc


def finalize(acc, poss, game_id):
    """Turn raw accumulators into the ten published measures."""
    rows = []
    for pid, a in acc.items():
        if a["frames"] < 10:
            continue
        p = poss[pid]
        hf = max(a["handler_frames"], 1)
        rows.append({
            "game_id": game_id,
            "possession_id": pid,
            "offense": p["offense"],
            "points_allowed": p["points"],
            "result": p["result"],
            "duration_sec": p["duration"],
            "frames": a["frames"],
            # 1. did the offense ever attack downhill
            "drive_share": a["drive_frames"] / hf,
            # 2. did the offense reach the rim
            "rim_share": a["rim_frames"] / hf,
            "min_rim_dist": a["min_rim_dist"],
            # 3. how tightly the ball was guarded
            "ball_pressure": (a["pressure_sum"] / a["pressure_n"]) if a["pressure_n"] else 0.0,
            # 4. bodies stationed in the paint
            "paint_wall": a["paint_opp_sum"] / a["frames"],
            # 5. how much room the offense achieved
            "spacing_conceded": (a["spacing_sum"] / a["spacing_n"]) if a["spacing_n"] else 0.0,
            # 6. contest quality at the point of attack
            "contest_index": (a["contest_sum"] / a["contest_n"]) if a["contest_n"] else 0.0,
            "vertical_rate": a["jumps"] / a["frames"],
            # 7. urgency of help arriving
            "closeout_speed": (a["closeout_sum"] / a["closeout_n"]) if a["closeout_n"] else 0.0,
            # 8. how often defenders abandoned their assignment
            "rotation_count": a["rotations"],
            "rotation_rate": a["rotations"] / a["frames"],
            # 9. did the defense force the offense into isolation
            "iso_forced": (a["iso_sum"] / a["iso_n"]) if a["iso_n"] else 0.0,
            # 10. did the defense drain the clock
            "late_clock": 1 if p["duration"] >= LATE_CLOCK_SEC else 0,
        })
    return rows


def deterrence(rows):
    """Share of possessions where the offense attacked and still scored nothing."""
    attacked = [r for r in rows if r["drive_share"] > 0 or r["rim_share"] > 0]
    if not attacked:
        return 0.0, 0
    stopped = sum(1 for r in attacked if r["points_allowed"] == 0)
    return stopped / len(attacked), len(attacked)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="data/cache/defensive_stats.csv")
    args = ap.parse_args()

    paths = sorted(glob.glob("data/tracking/*/tracking_data.csv"))
    if not args.all:
        paths = paths[: args.games]

    all_rows = []
    done = 0
    for tp in paths:
        gdir = os.path.dirname(tp)
        gid = os.path.basename(gdir)
        poss = load_possessions(os.path.join(gdir, "possessions.csv"))
        if not poss:
            continue
        try:
            acc = scan_game(tp, poss)
        except Exception as exc:  # keep the corpus scan alive
            print("SKIP %s: %s" % (gid, exc))
            continue
        all_rows.extend(finalize(acc, poss, gid))
        done += 1
        if done % 25 == 0:
            print("  ... %d games, %d possessions" % (done, len(all_rows)))
            sys.stdout.flush()

    if not all_rows:
        print("no possessions produced")
        return

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="ascii", errors="replace") as fh:
        w = csv.DictWriter(fh, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)

    n = len(all_rows)
    ppp = sum(r["points_allowed"] for r in all_rows) / n
    det, natk = deterrence(all_rows)
    print("\n=== DEFENSIVE STATS CORPUS ===")
    print("games              : %d" % done)
    print("possessions        : %d" % n)
    print("points per poss    : %.3f" % ppp)
    print("attacked poss      : %d" % natk)
    print("DETERRENCE RATE    : %.3f" % det)
    for k in ("drive_share", "rim_share", "ball_pressure", "paint_wall",
              "spacing_conceded", "contest_index", "vertical_rate",
              "closeout_speed", "rotation_rate", "iso_forced"):
        vals = [r[k] for r in all_rows]
        vals.sort()
        print("%-18s : mean %8.3f  med %8.3f  p90 %8.3f" % (
            k, sum(vals) / len(vals), vals[len(vals) // 2], vals[int(len(vals) * 0.9)]))
    print("wrote %s" % args.out)


if __name__ == "__main__":
    main()
