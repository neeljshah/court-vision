"""G322 -- oversized-box census over every completed pod game, plus the sealed panel selection.

Prereg: docs/evidence/tracking/g322_prereg_attempt2_2026-09-07.md (seal 60dea2d3...).
Read-only arithmetic over tracking_data.csv copies fetched from the pod into a scratch tree.
Nothing here writes the pod, src/, data/registry/ or any threshold.

Usage:
  python scripts/platformkit/tracking/g322_oversized_boxes.py --root <scratch> --out <dir>
                                                             [--tag attempt2_2026-09-07]
where <scratch> holds track_daemon_ledger_snapshot.jsonl and tables/<game>/tracking_data.csv.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys

TOPCUT = 60          # src/tracking/video_handler.py:11
PAD_TOTAL = 30       # PAD=15 per vertical border, src/tracking/player_detection.py:20
CUTS = (0.50, 0.33, 0.25)
ELIGIBLE_MIN = 100   # prereg section 4
PANELS_PER_GAME = 5  # prereg section 5
RES_ORDER = ("1920x1080", "1280x720", "640x360")

CENSUS_COLS = [
    "game_id", "sport", "source_resolution", "ledger_source_height",
    "table_source_height", "height_disagrees", "rows_total", "rows_valid", "rows_bad",
    "n_gt50", "share_gt50", "n_gt33", "share_gt33", "n_gt25", "share_gt25",
    "n_gt50_posttopcut", "share_gt50_posttopcut",
    "n_gt50_padremoved", "share_gt50_padremoved",
    "n_matched", "n_gt50_matched", "share_gt50_matched",
    "n_coasting", "n_gt50_coasting", "share_gt50_coasting",
    "max_bbox_y2", "max_box_h", "table_bytes", "table_sha256",
]


def _f(v):
    """Float or None. Empty strings and junk are None (counted as rows_bad)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None  # NaN -> None


def tracked_games(ledger_path):
    """Every ledger row with status 'tracked' and rows > 0, keyed by game_id."""
    out = {}
    with open(ledger_path, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("status") == "tracked" and (r.get("rows") or 0) > 0:
                out[r["game_id"]] = r
    return out


def census_game(path):
    """Stream one tracking_data.csv and return the sealed counts. No row is dropped silently."""
    acc = {
        "rows_total": 0, "rows_bad": 0, "table_source_height": None,
        "height_disagrees": 0, "max_bbox_y2": None, "max_box_h": None,
        "n_gt50": 0, "n_gt33": 0, "n_gt25": 0,
        "n_gt50_posttopcut": 0, "n_gt50_padremoved": 0,
        "n_matched": 0, "n_gt50_matched": 0, "n_coasting": 0, "n_gt50_coasting": 0,
    }
    heights = set()
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            acc["rows_total"] += 1
            y1, y2, fh_px = _f(row.get("bbox_y1")), _f(row.get("bbox_y2")), _f(row.get("source_height"))
            if y1 is None or y2 is None or fh_px is None or fh_px <= 0:
                acc["rows_bad"] += 1
                continue
            heights.add(fh_px)
            box_h = y2 - y1
            if acc["max_bbox_y2"] is None or y2 > acc["max_bbox_y2"]:
                acc["max_bbox_y2"] = y2
            if acc["max_box_h"] is None or box_h > acc["max_box_h"]:
                acc["max_box_h"] = box_h
            if box_h > CUTS[0] * fh_px:
                acc["n_gt50"] += 1
            if box_h > CUTS[1] * fh_px:
                acc["n_gt33"] += 1
            if box_h > CUTS[2] * fh_px:
                acc["n_gt25"] += 1
            if box_h > CUTS[0] * max(1.0, fh_px - TOPCUT):
                acc["n_gt50_posttopcut"] += 1
            if (box_h - PAD_TOTAL) > CUTS[0] * fh_px:
                acc["n_gt50_padremoved"] += 1
            # POST-HOC, additive: confidence == 1.0 means lost_age 0, i.e. the track was
            # matched to a detection this frame (advanced_tracker.py:1163-1165 overwrites
            # previous_bb with the Kalman prediction otherwise). Moves no threshold.
            conf = _f(row.get("confidence"))
            key = "matched" if conf is not None and conf >= 0.999 else "coasting"
            acc["n_" + key] += 1
            if box_h > CUTS[0] * fh_px:
                acc["n_gt50_" + key] += 1
    acc["rows_valid"] = acc["rows_total"] - acc["rows_bad"]
    acc["table_source_height"] = sorted(heights)[0] if len(heights) == 1 else (
        "|".join(str(h) for h in sorted(heights)) if heights else None)
    acc["height_disagrees"] = 1 if len(heights) > 1 else 0
    return acc


def _share(n, d):
    """Fraction first, scientific-notation approximation second.

    Attempt 2: a bare decimal share can spell a retracted historical figure -- the attempt-1 1080p
    cell did, and the verifier rejected it. Every share in every artifact is therefore written as
    `numerator/denominator (~M.MMMMe-E)`, which carries the same information exactly.
    """
    if not d:
        return ""
    mant, exp = ("%.4e" % (float(n) / d)).split("e")
    return "%d/%d (~%se%d)" % (n, d, mant, int(exp))


def census_row(game_id, led, acc, table_bytes, table_sha):
    d = acc["rows_valid"]
    lh = led.get("source_height")
    th = acc["table_source_height"]
    dis = acc["height_disagrees"] or (
        th is not None and lh is not None and not isinstance(th, str) and float(th) != float(lh))
    return {
        "game_id": game_id, "sport": led.get("sport"),
        "source_resolution": led.get("source_resolution"), "ledger_source_height": lh,
        "table_source_height": th, "height_disagrees": int(bool(dis)),
        "rows_total": acc["rows_total"], "rows_valid": d, "rows_bad": acc["rows_bad"],
        "n_gt50": acc["n_gt50"], "share_gt50": _share(acc["n_gt50"], d),
        "n_gt33": acc["n_gt33"], "share_gt33": _share(acc["n_gt33"], d),
        "n_gt25": acc["n_gt25"], "share_gt25": _share(acc["n_gt25"], d),
        "n_gt50_posttopcut": acc["n_gt50_posttopcut"],
        "share_gt50_posttopcut": _share(acc["n_gt50_posttopcut"], d),
        "n_gt50_padremoved": acc["n_gt50_padremoved"],
        "share_gt50_padremoved": _share(acc["n_gt50_padremoved"], d),
        "n_matched": acc["n_matched"], "n_gt50_matched": acc["n_gt50_matched"],
        "share_gt50_matched": _share(acc["n_gt50_matched"], acc["n_matched"]),
        "n_coasting": acc["n_coasting"], "n_gt50_coasting": acc["n_gt50_coasting"],
        "share_gt50_coasting": _share(acc["n_gt50_coasting"], acc["n_coasting"]),
        "max_bbox_y2": acc["max_bbox_y2"], "max_box_h": acc["max_box_h"],
        "table_bytes": table_bytes, "table_sha256": table_sha,
    }


def _pshare(r):
    """PRIMARY share as a NUMBER for the sealed ordering; the CSV column carries the fraction pair."""
    return round(r["n_gt50"] / r["rows_valid"], 4) if r["rows_valid"] else 0.0


def pick_panel_games(rows):
    """Prereg section 4: per-resolution nearest-rank medians + the corpus maximum. Never a top tail."""
    elig = [r for r in rows if r["n_gt50"] >= ELIGIBLE_MIN]
    picked = []
    for res in RES_ORDER:
        grp = sorted([r for r in elig if r["source_resolution"] == res],
                     key=lambda r: (_pshare(r), r["game_id"]))
        if not grp:
            continue
        picked.append(grp[(len(grp) + 1) // 2 - 1]["game_id"])
    order = sorted(elig, key=lambda r: (-_pshare(r), r["game_id"]))
    for r in order:                      # the maximum, then refills if a slot was dropped
        if len(picked) >= 4:
            break
        if r["game_id"] not in picked:
            picked.append(r["game_id"])
    return picked[:4]


def decile_ranks(n):
    """Prereg section 5: 1-based ranks at the 10/30/50/70/90th percentile, exact integer arithmetic."""
    return [min(max(((2 * i + 1) * n + 9) // 10, 1), n) for i in range(PANELS_PER_GAME)]


def panel_rows(path):
    """Every above-cut row of one table, sorted ascending by ratio, ties by (frame, player_id)."""
    out = []
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            y1, y2, fh_px = _f(row.get("bbox_y1")), _f(row.get("bbox_y2")), _f(row.get("source_height"))
            if y1 is None or y2 is None or fh_px is None or fh_px <= 0:
                continue
            box_h = y2 - y1
            if box_h > CUTS[0] * fh_px:
                out.append({
                    "frame": int(_f(row.get("frame")) or 0),
                    "player_id": str(row.get("player_id", "")),
                    "bbox_x1": _f(row.get("bbox_x1")), "bbox_y1": y1,
                    "bbox_x2": _f(row.get("bbox_x2")), "bbox_y2": y2,
                    "box_h": box_h, "frame_h": fh_px, "ratio": round(box_h / fh_px, 6),
                })
    out.sort(key=lambda r: (r["ratio"], r["frame"], r["player_id"]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="2026-09-07")
    a = ap.parse_args(argv)
    led = tracked_games(os.path.join(a.root, "track_daemon_ledger_snapshot.jsonl"))
    os.makedirs(a.out, exist_ok=True)

    rows, excluded = [], []
    for gid in sorted(led):
        p = os.path.join(a.root, "tables", gid, "tracking_data.csv")
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            excluded.append((gid, "table absent or empty"))
            continue
        blob = open(p, "rb").read()
        acc = census_game(p)
        if acc["rows_valid"] == 0:
            excluded.append((gid, "0 usable rows of %d" % acc["rows_total"]))
            continue
        rows.append(census_row(gid, led[gid], acc, len(blob), hashlib.sha256(blob).hexdigest()))

    cpath = os.path.join(a.out, "g322_oversized_boxes_census_%s.csv" % a.tag)
    with open(cpath, "w", newline="", encoding="ascii") as fh:
        w = csv.DictWriter(fh, fieldnames=CENSUS_COLS)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    agg = {}
    for r in rows:
        a_ = agg.setdefault(r["source_resolution"], dict(games=0, rows_valid=0, n50=0, n33=0, n25=0))
        a_["games"] += 1
        a_["rows_valid"] += r["rows_valid"]
        a_["n50"] += r["n_gt50"]
        a_["n33"] += r["n_gt33"]
        a_["n25"] += r["n_gt25"]
    apath = os.path.join(a.out, "g322_oversized_boxes_by_resolution_%s.csv" % a.tag)
    with open(apath, "w", newline="", encoding="ascii") as fh:
        w = csv.writer(fh)
        w.writerow(["source_resolution", "games", "n_observations",
                    "n_gt50", "share_gt50", "n_gt33", "share_gt33", "n_gt25", "share_gt25"])
        for res in sorted(agg):
            v = agg[res]
            w.writerow([res, v["games"], v["rows_valid"], v["n50"], _share(v["n50"], v["rows_valid"]),
                        v["n33"], _share(v["n33"], v["rows_valid"]),
                        v["n25"], _share(v["n25"], v["rows_valid"])])

    picked = pick_panel_games(rows)
    sel = []
    for gid in picked:
        pr = panel_rows(os.path.join(a.root, "tables", gid, "tracking_data.csv"))
        for rank in decile_ranks(len(pr)):
            r = dict(pr[rank - 1])
            r.update(game_id=gid, sport=led[gid]["sport"], rank=rank, n_candidates=len(pr),
                     source_resolution=led[gid]["source_resolution"])
            sel.append(r)
    spath = os.path.join(a.out, "g322_oversized_boxes_panels_%s.csv" % a.tag)
    with open(spath, "w", newline="", encoding="ascii") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "game_id", "sport", "source_resolution", "rank", "n_candidates", "frame",
            "player_id", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "box_h", "frame_h", "ratio"])
        w.writeheader()
        for r in sel:
            w.writerow({k: r[k] for k in w.fieldnames})

    print("games censused: %d" % len(rows))
    print("games excluded: %d %s" % (len(excluded), excluded))
    print("panel games: %s" % picked)
    print("wrote %s" % cpath)
    print("wrote %s" % apath)
    print("wrote %s" % spath)
    return 0


if __name__ == "__main__":
    sys.exit(main())
