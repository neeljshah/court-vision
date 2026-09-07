"""G309 -- multi-game tracking census over the pod's data/tracking tree.

READ-ONLY. Image space only (coordinate_space = image_px): no court, foot, metre or
registration claim is made or implied. Every metric is an internal-consistency proxy
computed from the CSVs themselves -- none is recall, precision, accuracy or registration.

Run on the pod:
  ~/bin/pod_run a12 --fetch docs/evidence/tracking/g309_multigame_census_2026-09-07.csv \
    -- python -m scripts.platformkit.tracking.g309_multigame_census
"""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
import sys
import time

DATE = "2026-09-07"
OUT_CSV = "docs/evidence/tracking/g309_multigame_census_%s.csv" % DATE
PREMISE_MIN = 6

COLUMNS = [
    "game_id", "sport", "rows", "frames_emitted", "frames_attempted",
    "coverage_attempted_frames_pct", "coverage_decoded_pct", "decoded_frames", "stride",
    "distinct_track_ids", "median_track_len_rows", "id_churn_per_detection",
    "ball_rows", "ball_detected", "ball_inferred", "ball_none", "ball_valid_share",
    "n_steps", "p95_disp_norm", "zero_step_share", "share_frames_ge6_boxes",
    "source_height", "coordinate_space", "ledger_row", "ledger_passed", "ledger_status",
    "ledger_rung", "ledger_rows", "ledger_coverage_pct", "rows_match_ledger",
    "coverage_match_ledger_4dp", "failure_head",
]


def _f(v):
    """Parse a CSV cell as a finite float, else None."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _p95(vals):
    """Nearest-rank 95th percentile: sorted[ceil(0.95*n)-1]. Stated convention, no interpolation."""
    if not vals:
        return None
    s = sorted(vals)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def _ascii(s, n=180):
    s = "" if s is None else str(s)
    s = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in s)
    return s.replace('"', "'")[:n]


def read_ledger(root):
    """LAST ledger line per game_id (a game is written thin first, then tracked)."""
    path = os.path.join(root, "track_daemon_ledger.jsonl")
    rows, n_lines, n_passed = {}, 0, 0
    if not os.path.exists(path):
        return rows, 0, 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            n_lines += 1
            if d.get("passed") is not None:
                n_passed += 1
            if d.get("game_id"):
                rows[d["game_id"]] = d
    return rows, n_lines, n_passed


def player_metrics(path):
    """One streaming pass over tracking_data.csv. Footpoint = bbox bottom-centre."""
    per_frame, tracks, rows, height, cspace = {}, {}, 0, None, None
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            rows += 1
            fr = r.get("frame")
            per_frame[fr] = per_frame.get(fr, 0) + 1
            if height is None:
                height = _f(r.get("source_height"))
            if not cspace:
                cspace = (r.get("coordinate_space") or "").strip() or None
            x1, x2, y2 = _f(r.get("bbox_x1")), _f(r.get("bbox_x2")), _f(r.get("bbox_y2"))
            fi = _f(fr)
            pid = r.get("player_id")
            tr = tracks.setdefault(pid, [])
            tr.append((fi, None if None in (x1, x2, y2) else ((x1 + x2) / 2.0, y2)))

    steps, zero = [], 0
    for obs in tracks.values():
        pts = sorted((f, p) for f, p in obs if f is not None and p is not None)
        for (_, a), (_, b) in zip(pts, pts[1:]):
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            steps.append(d)
            if d == 0.0:
                zero += 1

    frames_emitted = len(per_frame)
    p95 = _p95(steps)
    return {
        "rows": rows,
        "frames_emitted": frames_emitted,
        "distinct_track_ids": len(tracks),
        "median_track_len_rows": (statistics.median(len(v) for v in tracks.values())
                                  if tracks else None),
        "id_churn_per_detection": (len(tracks) / rows) if rows else None,
        "n_steps": len(steps),
        "p95_disp_norm": (p95 / height) if (p95 is not None and height) else None,
        "zero_step_share": (zero / len(steps)) if steps else None,
        "share_frames_ge6_boxes": (sum(1 for c in per_frame.values() if c >= 6) / frames_emitted
                                   if frames_emitted else None),
        "source_height": height,
        "coordinate_space": cspace,
    }


def ball_metrics(path):
    out = {"ball_rows": 0, "ball_detected": 0, "ball_inferred": 0, "ball_none": 0,
           "ball_valid_share": None}
    if not os.path.exists(path):
        return out
    valid = 0
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            out["ball_rows"] += 1
            det = (r.get("detected") or "").strip() in ("1", "1.0", "True", "true")
            inf = (r.get("ball_inferred") or "").strip() in ("1", "1.0", "True", "true")
            out["ball_detected"] += int(det)
            out["ball_inferred"] += int(inf)
            out["ball_none"] += int(not det and not inf)
            if _f(r.get("ball_x2d")) is not None and _f(r.get("ball_y2d")) is not None:
                valid += 1
    if out["ball_rows"]:
        out["ball_valid_share"] = valid / out["ball_rows"]
    return out


def _attempted(led, verdict, decoded, stride):
    for src in (verdict, led):
        v = (src or {}).get("evaluated_frames")
        if v:
            return int(v)
    if decoded and stride:
        return math.ceil(decoded / stride)
    return None


def census(root):
    """One row per game directory holding a tracking_data.csv."""
    ledger, n_lines, n_passed = read_ledger(root)
    out = []
    for game in sorted(os.listdir(root)):
        gdir = os.path.join(root, game)
        tdc = os.path.join(gdir, "tracking_data.csv")
        if not (os.path.isdir(gdir) and os.path.exists(tdc)):
            continue
        led = ledger.get(game)
        verdict = {}
        vp = os.path.join(gdir, "harness_verdict.json")
        if os.path.exists(vp):
            try:
                verdict = json.load(open(vp, "r", encoding="utf-8", errors="replace"))
            except ValueError:
                verdict = {}
        row = {c: None for c in COLUMNS}
        row["game_id"] = game
        row.update(player_metrics(tdc))
        row.update(ball_metrics(os.path.join(gdir, "ball_tracking.csv")))

        decoded = (led or {}).get("decoded_frames") or verdict.get("decoded_frames")
        stride = (led or {}).get("stride") or verdict.get("stride")
        att = _attempted(led, verdict, decoded, stride)
        fe = row["frames_emitted"]
        row["decoded_frames"], row["stride"], row["frames_attempted"] = decoded, stride, att
        row["coverage_attempted_frames_pct"] = (fe / att) if (att and fe is not None) else None
        row["coverage_decoded_pct"] = (fe / decoded) if (decoded and fe is not None) else None
        row["sport"] = (led or {}).get("sport")
        row["ledger_row"] = "present" if led else "absent"
        if led:
            row["ledger_passed"] = led.get("passed")
            row["ledger_status"] = led.get("status")
            row["ledger_rung"] = led.get("rung")
            row["ledger_rows"] = led.get("rows")
            row["ledger_coverage_pct"] = led.get("coverage_pct")
            heads = led.get("failure_heads") or []
            row["failure_head"] = _ascii(heads[0]) if heads else ""
            row["rows_match_ledger"] = (row["rows"] == led.get("rows"))
            lc = led.get("coverage_pct")
            cd = row["coverage_decoded_pct"]
            row["coverage_match_ledger_4dp"] = (
                None if (lc is None or cd is None) else (round(cd, 4) == round(float(lc), 4)))
        out.append(row)
    return out, ledger, n_lines, n_passed


def _dist(rows, key):
    vals = [(r[key], r["game_id"]) for r in rows if isinstance(r.get(key), (int, float))]
    if not vals:
        return None
    vals.sort()
    return {"median": statistics.median(v for v, _ in vals),
            "min": vals[0][0], "argmin": vals[0][1],
            "max": vals[-1][0], "argmax": vals[-1][1], "n": len(vals)}


def main():
    root = os.path.join("data", "tracking")
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print("G309 census_at=%s root=%s" % (stamp, os.path.abspath(root)))
    if not os.path.isdir(root):
        print("PREMISE FALSE: no %s" % root)
        return 2
    rows, ledger, n_lines, n_passed = census(root)
    print("PREMISE: ledger lines=%d ; rows with passed != null = %d (bar >= %d)"
          % (n_lines, n_passed, PREMISE_MIN))
    if n_passed < PREMISE_MIN:
        print("PREMISE FALSE -- fewer than %d adjudicated games; STOP." % PREMISE_MIN)
        return 3

    seen = [r["game_id"] for r in rows]
    missing = [g for g in ledger
               if os.path.exists(os.path.join(root, g, "tracking_data.csv")) and g not in seen]
    print("ACCEPTANCE: census_rows=%d duplicates=%d ledger_games_with_csv_missing=%s"
          % (len(rows), len(seen) - len(set(seen)), missing or "none"))

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", encoding="ascii", errors="replace", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("WROTE %s (%d rows)" % (OUT_CSV, len(rows)))

    for k in ("rows", "frames_emitted", "coverage_attempted_frames_pct", "coverage_decoded_pct",
              "distinct_track_ids", "median_track_len_rows", "id_churn_per_detection",
              "ball_detected", "ball_valid_share", "p95_disp_norm", "zero_step_share",
              "share_frames_ge6_boxes"):
        print("DIST %s %s" % (k, json.dumps(_dist(rows, k))))

    med = {k: (_dist(rows, k) or {}).get("median") for k in
           ("id_churn_per_detection", "zero_step_share")}
    for r in rows:
        g = r["game_id"]
        if r["ball_detected"] == 0:
            print("NEW GAP: %s emitted %d ball rows with ZERO detected -- ball head produced nothing"
                  % (g, r["ball_rows"]))
        for k in ("id_churn_per_detection", "zero_step_share"):
            v, m = r[k], med[k]
            if isinstance(v, float) and m and v > 2 * m:
                print("NEW GAP: %s %s = %.6f is above 2x the cross-game median %.6f"
                      % (g, k, v, m))
        if r["rows_match_ledger"] is False:
            print("NEW GAP: %s recomputed rows=%s disagrees with ledger rows=%s"
                  % (g, r["rows"], r["ledger_rows"]))
        if r["coverage_match_ledger_4dp"] is False:
            print("NEW GAP: %s coverage_decoded_pct=%s disagrees with ledger coverage_pct=%s at 4dp"
                  % (g, r["coverage_decoded_pct"], r["ledger_coverage_pct"]))
        if r["ledger_row"] == "absent":
            print("NEW GAP: %s has a tracking_data.csv but NO ledger row (in flight at census time)"
                  % g)
    return 0


if __name__ == "__main__":
    sys.exit(main())
