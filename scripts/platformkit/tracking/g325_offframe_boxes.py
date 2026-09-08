"""G325 -- census of player boxes lying WHOLLY OUTSIDE the decoded frame, over every pod game.

Prereg: docs/evidence/tracking/g325_prereg_2026-09-07.md.
Read-only arithmetic over tracking_data.csv copies fetched from the pod into a scratch tree.
Nothing here writes the pod, src/, data/registry/ or any threshold.

Machinery reused from scripts/platformkit/tracking/g322_oversized_boxes.py (worktree a21).

Usage:
  python scripts/platformkit/tracking/g325_offframe_boxes.py --root <scratch> --out <dir>
where <scratch> holds track_daemon_ledger_snapshot.jsonl and tables/<game>/tracking_data.csv.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g325_share_format import checked_share, share_approx, zfill_counts  # noqa: E402

TOPCUT = 60          # src/tracking/video_handler.py:11; frame = frame[TOPCUT:]
PAD = 15             # src/tracking/player_detection.py:20; added to each box side
MATCHED_CONF = 0.999  # confidence == 1.0 <=> lost_age == 0 (unified_pipeline.py:2025)

CENSUS_COLS = [
    "game_id", "sport", "source_resolution", "frame_w",
    "ledger_source_height", "table_source_height", "height_disagrees",
    "frame_h_primary", "frame_h_secondary",
    "rows_total", "rows_valid", "rows_bad",
    "n_wholly", "share_wholly", "share_wholly_frac",
    "n_wholly_secondary", "share_wholly_secondary", "share_wholly_secondary_frac",
    "n_partial", "share_partial", "share_partial_frac",
    "n_wholly_padremoved", "share_wholly_padremoved", "share_wholly_padremoved_frac",
    "n_side_left", "n_side_right", "n_side_top", "n_side_bottom",
    "n_matched", "n_coasting", "n_wholly_matched", "n_wholly_coasting",
    "min_bbox_x2", "max_bbox_x1", "min_bbox_y2", "max_bbox_y1",
    "table_bytes", "table_sha256",
]


def _f(v):
    """Float or None. Empty strings and junk are None (counted as rows_bad)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None  # NaN -> None


def tracked_games(ledger_path):
    """Every ledger row with status 'tracked' and rows > 0, keyed by game_id (last wins)."""
    out = {}
    with open(ledger_path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("status") == "tracked" and (r.get("rows") or 0) > 0:
                out[r["game_id"]] = r
    return out


def frame_w_of(led):
    """Width from the ledger's source_resolution ('WxH'). The table has NO width column."""
    res = led.get("source_resolution") or ""
    if "x" not in res:
        return None
    try:
        return float(res.split("x")[0])
    except ValueError:
        return None


def census_game(path, frame_w):
    """Stream one tracking_data.csv and return the sealed counts. No row is dropped silently."""
    acc = {k: 0 for k in (
        "rows_total", "rows_bad", "n_wholly", "n_wholly_secondary", "n_partial",
        "n_wholly_padremoved", "n_side_left", "n_side_right", "n_side_top",
        "n_side_bottom", "n_matched", "n_coasting", "n_wholly_matched", "n_wholly_coasting")}
    acc.update(min_bbox_x2=None, max_bbox_x1=None, min_bbox_y2=None, max_bbox_y1=None)
    heights = set()
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            acc["rows_total"] += 1
            x1, y1 = _f(row.get("bbox_x1")), _f(row.get("bbox_y1"))
            x2, y2 = _f(row.get("bbox_x2")), _f(row.get("bbox_y2"))
            sh = _f(row.get("source_height"))
            if None in (x1, y1, x2, y2, sh) or sh <= 0 or frame_w is None:
                acc["rows_bad"] += 1
                continue
            heights.add(sh)
            fh_pri = sh - TOPCUT          # the space the boxes are written in
            fh_sec = sh                   # the naive ledger-height reading
            left, right = x2 <= 0, x1 >= frame_w
            top, bottom = y2 <= 0, y1 >= fh_pri
            wholly = left or right or top or bottom
            if wholly:
                acc["n_wholly"] += 1
                acc["n_side_left"] += int(left)
                acc["n_side_right"] += int(right)
                acc["n_side_top"] += int(top)
                acc["n_side_bottom"] += int(bottom)
            if left or right or top or y1 >= fh_sec:
                acc["n_wholly_secondary"] += 1
            if not wholly and (x1 < 0 or y1 < 0 or x2 > frame_w or y2 > fh_pri):
                acc["n_partial"] += 1
            if ((x2 - PAD) <= 0 or (x1 + PAD) >= frame_w
                    or (y2 - PAD) <= 0 or (y1 + PAD) >= fh_pri):
                acc["n_wholly_padremoved"] += 1
            conf = _f(row.get("confidence"))
            key = "matched" if conf is not None and conf >= MATCHED_CONF else "coasting"
            acc["n_" + key] += 1
            if wholly:
                acc["n_wholly_" + key] += 1
            for name, val, better in (("min_bbox_x2", x2, min), ("max_bbox_x1", x1, max),
                                      ("min_bbox_y2", y2, min), ("max_bbox_y1", y1, max)):
                acc[name] = val if acc[name] is None else better(acc[name], val)
    acc["rows_valid"] = acc["rows_total"] - acc["rows_bad"]
    acc["table_source_height"] = sorted(heights)[0] if len(heights) == 1 else (
        "|".join(str(h) for h in sorted(heights)) if heights else None)
    acc["height_disagrees"] = 1 if len(heights) > 1 else 0
    return acc


def census_row(game_id, led, acc, frame_w, table_bytes, table_sha):
    d = acc["rows_valid"]
    lh = led.get("source_height")
    th = acc["table_source_height"]
    dis = acc["height_disagrees"] or (
        th is not None and lh is not None and not isinstance(th, str) and float(th) != float(lh))
    sh = None if isinstance(th, str) or th is None else float(th)
    out = {
        "game_id": game_id, "sport": led.get("sport"),
        "source_resolution": led.get("source_resolution"), "frame_w": frame_w,
        "ledger_source_height": lh, "table_source_height": th,
        "height_disagrees": int(bool(dis)),
        "frame_h_primary": None if sh is None else sh - TOPCUT,
        "frame_h_secondary": sh,
        "table_bytes": table_bytes, "table_sha256": table_sha,
    }
    for k in ("rows_total", "rows_valid", "rows_bad", "n_wholly", "n_wholly_secondary",
              "n_partial", "n_wholly_padremoved", "n_side_left", "n_side_right",
              "n_side_top", "n_side_bottom", "n_matched", "n_coasting",
              "n_wholly_matched", "n_wholly_coasting", "min_bbox_x2", "max_bbox_x1",
              "min_bbox_y2", "max_bbox_y1"):
        out[k] = acc[k]
    out["share_wholly"], out["share_wholly_frac"] = checked_share(acc["n_wholly"], d)
    out["share_wholly_secondary"], out["share_wholly_secondary_frac"] = checked_share(
        acc["n_wholly_secondary"], d)
    out["share_partial"], out["share_partial_frac"] = checked_share(acc["n_partial"], d)
    out["share_wholly_padremoved"], out["share_wholly_padremoved_frac"] = checked_share(
        acc["n_wholly_padremoved"], d)
    return out


def verdict(rows):
    """The sealed rules, applied mechanically. Nothing here moves a bar."""
    tot = sum(r["rows_valid"] for r in rows)
    who = sum(r["n_wholly"] for r in rows)
    per_game = any(r["n_wholly"] * 100 >= r["rows_valid"] for r in rows if r["rows_valid"])
    holds = (who * 1000 >= tot) or per_game
    coast = sum(r["n_wholly_coasting"] for r in rows)
    pinned = who > 0 and coast * 10 >= who * 9
    return {"rows_valid": tot, "n_wholly": who, "n_wholly_coasting": coast,
            "premise_holds": holds, "any_game_ge_1_in_100": per_game, "site_pinned": pinned}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    led = tracked_games(os.path.join(a.root, "track_daemon_ledger_snapshot.jsonl"))
    os.makedirs(a.out, exist_ok=True)

    rows, excluded = [], []
    for gid in sorted(led):
        p = os.path.join(a.root, "tables", gid, "tracking_data.csv")
        if not os.path.exists(p) or os.path.getsize(p) == 0:
            excluded.append((gid, "table absent or empty"))
            continue
        fw = frame_w_of(led[gid])
        if fw is None:
            excluded.append((gid, "no source_resolution width in the ledger row"))
            continue
        blob = open(p, "rb").read()
        acc = census_game(p, fw)
        if acc["rows_valid"] == 0:
            excluded.append((gid, "0 usable rows of %d" % acc["rows_total"]))
            continue
        rows.append(census_row(gid, led[gid], acc, fw, len(blob),
                               hashlib.sha256(blob).hexdigest()))

    cpath = os.path.join(a.out, "g325_offframe_boxes_census_2026-09-07.csv")
    with open(cpath, "w", newline="", encoding="ascii") as fh:
        w = csv.DictWriter(fh, fieldnames=CENSUS_COLS)
        w.writeheader()
        for r in rows:
            w.writerow(zfill_counts(r))

    agg = {}
    for r in rows:
        v = agg.setdefault(r["source_resolution"], dict(
            games=0, rows_valid=0, wholly=0, partial=0, padrem=0, wcoast=0, wmatch=0))
        v["games"] += 1
        v["rows_valid"] += r["rows_valid"]
        v["wholly"] += r["n_wholly"]
        v["partial"] += r["n_partial"]
        v["padrem"] += r["n_wholly_padremoved"]
        v["wcoast"] += r["n_wholly_coasting"]
        v["wmatch"] += r["n_wholly_matched"]
    apath = os.path.join(a.out, "g325_offframe_boxes_by_resolution_2026-09-07.csv")
    with open(apath, "w", newline="", encoding="ascii") as fh:
        w = csv.writer(fh)
        w.writerow(["source_resolution", "games", "n_observations", "n_wholly",
                    "share_wholly", "share_wholly_frac", "n_partial", "share_partial",
                    "share_partial_frac", "n_wholly_padremoved", "n_wholly_coasting",
                    "n_wholly_matched"])
        for res in sorted(agg):
            v = agg[res]
            sw, swf = checked_share(v["wholly"], v["rows_valid"])
            sp, spf = checked_share(v["partial"], v["rows_valid"])
            w.writerow([res, "%06d" % v["games"], "%06d" % v["rows_valid"],
                        "%06d" % v["wholly"], sw, swf, "%06d" % v["partial"], sp, spf,
                        "%06d" % v["padrem"], "%06d" % v["wcoast"], "%06d" % v["wmatch"]])

    vd = verdict(rows)
    print("games censused: %d" % len(rows))
    print("games excluded: %d %s" % (len(excluded), excluded))
    print("pooled wholly: %d/%d (~%s)" % (vd["n_wholly"], vd["rows_valid"],
                                          share_approx(vd["n_wholly"], vd["rows_valid"])))
    print("wholly coasting: %d/%d (~%s)" % (
        vd["n_wholly_coasting"], vd["n_wholly"],
        share_approx(vd["n_wholly_coasting"], vd["n_wholly"])))
    print("PREMISE_HOLDS=%s any_game_ge_1_in_100=%s SITE_PINNED=%s"
          % (vd["premise_holds"], vd["any_game_ge_1_in_100"], vd["site_pinned"]))
    print("wrote %s" % cpath)
    print("wrote %s" % apath)
    return 0


if __name__ == "__main__":
    sys.exit(main())
