"""
cv_fix_anchor_intel.py <gid> — PBP-anchored CV contest intelligence.

Fuses three sources to attribute REAL CV contest geometry to KNOWN shots, bypassing
both jersey OCR and CV shot detection:
  1. scoreboard_ocr.csv  — frame -> (period, game-clock) from the broadcast score bug
  2. shotchart.json/pbp  — every FGA: shooter, period, clock, made/missed, zone, distance
  3. tracking_data.csv   — per-frame player + ball court positions

For each ground-truth shot: anchor its (period, clock) to a video frame via the scoreboard
map; at that frame find the tracked player nearest the ball (= the shooter) and measure the
nearest opponent (= the contesting defender) in feet. Aggregate per player & per zone, joined
to the real made/missed outcome.

Outputs: data/cache/cv_fix/anchored_<gid>.csv  +  intel_<gid>.json
"""
from __future__ import annotations
import csv, json, math, os, sys
from collections import defaultdict

GID = sys.argv[1]
TRACK_DIR = f"data/tracking/{GID}"
NBA_DIR = f"data/cache/cv_fix/nba_{GID}" if os.path.isdir(f"data/cache/cv_fix/nba_{GID}") else "data/cache/cv_fix/nba"
OUT_DIR = "data/cache/cv_fix"
PX_PER_FT = 3404.0 / 94.0   # court map width 3404px / 94ft
TOL_SEC = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0


def load_scoreboard():
    path = f"{TRACK_DIR}/scoreboard_ocr.csv"
    rows = []
    for r in csv.DictReader(open(path)):
        try:
            per = int(r["period"]) if r["period"] not in ("", "None") else None
            clk = float(r["clock_sec"]) if r["clock_sec"] not in ("", "None") else None
        except ValueError:
            per, clk = None, None
        # Clock OCR emits garbage 4-5 digit reads (shot-clock bleed); a real game clock is
        # 0..720s. Reject out-of-range so we never anchor on a parse error.
        if clk is not None and not (1 <= clk <= 720):
            clk = None
        if per and clk is not None and float(r.get("period_conf", 0) or 0) >= 0.5:
            rows.append((int(r["frame"]), per, clk))
    return rows  # list[(frame, period, clock_sec)]


def load_shots():
    sc = json.load(open(f"{NBA_DIR}/shotchart.json"))
    shots = []
    for s in sc:
        shots.append({
            "pid": s["PLAYER_ID"], "name": s["PLAYER_NAME"], "team": s.get("TEAM_NAME", ""),
            "period": s["PERIOD"], "clock_sec": s["MINUTES_REMAINING"] * 60 + s["SECONDS_REMAINING"],
            "loc_x": s["LOC_X"], "loc_y": s["LOC_Y"], "dist": s["SHOT_DISTANCE"],
            "made": s["SHOT_MADE_FLAG"], "zone": s["SHOT_ZONE_BASIC"], "area": s.get("SHOT_ZONE_AREA", ""),
            "action": s.get("ACTION_TYPE", ""),
        })
    return shots


def load_tracking_by_frame():
    path = f"{TRACK_DIR}/tracking_data.csv"
    byf = defaultdict(list)
    for r in csv.DictReader(open(path)):
        try:
            f = int(float(r["frame"]))
            x = float(r["x_position"]); y = float(r["y_position"])
        except (ValueError, KeyError):
            continue
        bx = r.get("ball_x2d", ""); by = r.get("ball_y2d", "")
        byf[f].append({
            "slot": r.get("player_id"), "team": r.get("team", ""), "x": x, "y": y,
            "ball_x": float(bx) if bx not in ("", "None") else None,
            "ball_y": float(by) if by not in ("", "None") else None,
            "spacing": r.get("team_spacing", ""),
        })
    return byf


def anchor(shots, sb):
    """For each shot find the scoreboard frame with same period and closest clock."""
    by_per = defaultdict(list)
    for fr, per, clk in sb:
        by_per[per].append((clk, fr))
    for p in by_per:
        by_per[p].sort()
    out = []
    for s in shots:
        cands = by_per.get(s["period"], [])
        best = None
        for clk, fr in cands:
            d = abs(clk - s["clock_sec"])
            if best is None or d < best[0]:
                best = (d, fr, clk)
        if best and best[0] <= TOL_SEC:
            s = dict(s); s["anchor_frame"] = best[1]; s["clock_resid"] = round(best[0], 1)
            out.append(s)
        else:
            s = dict(s); s["anchor_frame"] = None; s["clock_resid"] = None
            out.append(s)
    return out


def nearest_frame_with_tracks(frame, byf, window=120):
    if frame in byf:
        return frame
    for d in range(1, window + 1):
        if frame + d in byf:
            return frame + d
        if frame - d in byf:
            return frame - d
    return None


def contest_at(frame, byf):
    """Return (shooter_slot, contest_ft, spacing, n_players) at the frame: shooter = player
    nearest the ball; defender = nearest opponent to that shooter."""
    tf = nearest_frame_with_tracks(frame, byf)
    if tf is None:
        return None
    players = byf[tf]
    balled = [p for p in players if p["ball_x"] is not None]
    if not balled:
        return None
    bx, by = balled[0]["ball_x"], balled[0]["ball_y"]
    shooter = min(players, key=lambda p: (p["x"] - bx) ** 2 + (p["y"] - by) ** 2)
    opps = [p for p in players if p["team"] != shooter["team"] and p["team"] in ("green", "white")]
    if not opps:
        return None
    dpx = min(math.hypot(shooter["x"] - o["x"], shooter["y"] - o["y"]) for o in opps)
    sp = shooter.get("spacing", "")
    return {"shooter_team": shooter["team"], "contest_ft": round(dpx / PX_PER_FT, 1),
            "spacing": float(sp) if sp not in ("", "None") else None,
            "n_players": len(players), "track_frame": tf, "ball_dist_to_shooter_ft":
            round(math.hypot(shooter["x"] - bx, shooter["y"] - by) / PX_PER_FT, 1)}


def main():
    sb = load_scoreboard()
    shots = load_shots()
    byf = load_tracking_by_frame()
    print(f"[intel] {GID}: scoreboard anchors={len(sb)} shots={len(shots)} tracked_frames={len(byf)}")

    anchored = anchor(shots, sb)
    n_anch = sum(1 for s in anchored if s["anchor_frame"] is not None)
    print(f"[intel] anchored {n_anch}/{len(shots)} shots within {TOL_SEC}s")

    rows = []
    for s in anchored:
        rec = dict(s)
        if s["anchor_frame"] is not None:
            c = contest_at(s["anchor_frame"], byf)
            if c:
                rec.update(c)
        rows.append(rec)

    # write per-shot csv
    cols = ["pid", "name", "team", "period", "clock_sec", "made", "zone", "dist",
            "anchor_frame", "clock_resid", "track_frame", "shooter_team", "contest_ft",
            "ball_dist_to_shooter_ft", "spacing", "n_players"]
    with open(f"{OUT_DIR}/anchored_{GID}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # intelligence aggregates
    valid = [r for r in rows if r.get("contest_ft") is not None
             and r.get("ball_dist_to_shooter_ft", 99) <= 12]  # shooter must be near ball
    per_player = defaultdict(lambda: {"n": 0, "made": 0, "contest": [], "by_zone": defaultdict(int)})
    for r in valid:
        pp = per_player[r["name"]]
        pp["n"] += 1; pp["made"] += int(r["made"]); pp["contest"].append(r["contest_ft"])
        pp["by_zone"][r["zone"]] += 1
    intel = {"game_id": GID, "scoreboard_anchor_rows": len(sb), "total_shots": len(shots),
             "anchored_shots": n_anch, "contest_resolved_shots": len(valid),
             "players": {}}
    for name, pp in sorted(per_player.items(), key=lambda kv: -kv[1]["n"]):
        if pp["n"] < 2:
            continue
        cs = sorted(pp["contest"])
        intel["players"][name] = {
            "shots_resolved": pp["n"], "made": pp["made"],
            "avg_contest_ft": round(sum(cs) / len(cs), 1),
            "median_contest_ft": cs[len(cs) // 2],
            "tight_contests_under_4ft": sum(1 for c in cs if c < 4),
            "zones": dict(pp["by_zone"]),
        }
    json.dump(intel, open(f"{OUT_DIR}/intel_{GID}.json", "w"), indent=2)
    print(f"[intel] wrote anchored_{GID}.csv + intel_{GID}.json | contest-resolved {len(valid)} shots, "
          f"{len(intel['players'])} players with >=2")
    # quick headline
    for name, d in list(intel["players"].items())[:8]:
        print(f"   {name:26s} shots={d['shots_resolved']:2d} made={d['made']} "
              f"avgD={d['avg_contest_ft']}ft tight<4ft={d['tight_contests_under_4ft']}")


if __name__ == "__main__":
    main()
