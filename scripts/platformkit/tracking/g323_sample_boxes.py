"""G323 -- sealed 60-box sample: median games, tercile x region cells, seeded round-robin.

Prereg: docs/evidence/tracking/g323_prereg_2026-09-07.md sections 2, 3 and 4 (seal
148d3861a2e293ea94982a6e0d36ad7722e937e2fb4e5e0ca6735bca2a6f021a). Nothing here filters a row:
every observation in every fetched table is a candidate.

Usage:
  python scripts/platformkit/tracking/g323_sample_boxes.py \
      --census <g322 census csv> --tables <dir of <game_id>.csv> \
      --out <sample csv> --cells <cell count csv>
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import math
import os
import sys

TOPCUT = 60
SEED = "G323"
GAME_ORDER_KEY = "share_gt50"
CELL_ORDER = [(t, r) for t in ("T1", "T2", "T3") for r in ("UPPER", "LOWER")]
PER_CELL = 10

SAMPLE_COLS = [
    "panel_id", "cell", "tercile", "region", "game_id", "source_resolution",
    "frame", "player_id", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2",
    "box_h", "source_height", "post_topcut_h", "ratio", "centre_y", "key",
]


def median_games(census_path):
    """Nearest-rank median share_gt50 game per source_resolution (prereg section 2)."""
    by_res = collections.defaultdict(list)
    with open(census_path, newline="") as fh:
        for row in csv.DictReader(fh):
            by_res[row["source_resolution"]].append(
                (float(row[GAME_ORDER_KEY]), row["game_id"]))
    picked = {}
    for res, rows in by_res.items():
        rows.sort()
        rank = int(math.ceil(0.5 * len(rows)))
        share, gid = rows[rank - 1]
        picked[res] = (gid, rank, len(rows), share)
    return picked


def load_rows(table_path, game_id):
    """Every observation in the table, with the prereg's derived fields. No filtering."""
    out = []
    with open(table_path, newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                y1, y2 = float(row["bbox_y1"]), float(row["bbox_y2"])
                x1, x2 = float(row["bbox_x1"]), float(row["bbox_x2"])
                sh = float(row["source_height"])
            except (KeyError, TypeError, ValueError):
                continue
            h = sh - TOPCUT
            key = hashlib.sha256(
                ("%s|%s|%s|%s" % (SEED, game_id, row["frame"], row["player_id"]))
                .encode("ascii")).hexdigest()
            out.append({
                "game_id": game_id, "frame": row["frame"], "player_id": row["player_id"],
                "bbox_x1": x1, "bbox_y1": y1, "bbox_x2": x2, "bbox_y2": y2,
                "box_h": y2 - y1, "source_height": sh, "post_topcut_h": h,
                "ratio": (y2 - y1) / h, "centre_y": (y1 + y2) / 2.0, "key": key,
            })
    return out


def _nearest_rank(sorted_vals, q):
    """Nearest-rank percentile, 1-based ceil(q*n) (prereg section 3)."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    return sorted_vals[max(0, min(n - 1, int(math.ceil(q * n)) - 1))]


def assign_cells(rows):
    """Tercile from the game's OWN 1/3 and 2/3 nearest-rank ratio percentiles; region by centre_y."""
    vals = sorted(r["ratio"] for r in rows)
    p33, p67 = _nearest_rank(vals, 1.0 / 3.0), _nearest_rank(vals, 2.0 / 3.0)
    for r in rows:
        r["tercile"] = "T1" if r["ratio"] < p33 else ("T2" if r["ratio"] < p67 else "T3")
        r["region"] = "UPPER" if r["centre_y"] < 0.5 * r["post_topcut_h"] else "LOWER"
    return p33, p67


def fill_cell(pools, game_order):
    """Round-robin over game_order, each game's lowest-key unused row, until PER_CELL or empty."""
    taken, shortfall = [], collections.Counter()
    idx = {g: 0 for g in game_order}
    gi = 0
    while len(taken) < PER_CELL:
        if all(idx[g] >= len(pools.get(g, ())) for g in game_order):
            break
        g = game_order[gi % len(game_order)]
        gi += 1
        pool = pools.get(g, ())
        if idx[g] >= len(pool):
            shortfall[g] += 1
            continue
        taken.append(pool[idx[g]])
        idx[g] += 1
    return taken, shortfall


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", required=True)
    ap.add_argument("--tables", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cells", required=True)
    a = ap.parse_args(argv)

    picked = median_games(a.census)
    print("MEDIAN GAME PICK (prereg section 2, recomputed):")
    for res in sorted(picked):
        gid, rank, n, share = picked[res]
        print("  %-9s -> %-18s rank %d of %d, share_gt50 %.4f" % (res, gid, rank, n, share))
    game_order = [picked[r][0] for r in ("1920x1080", "1280x720", "640x360")]
    print("GAME ORDER (prereg section 4): %s" % ", ".join(game_order))

    all_rows, cuts = {}, {}
    for gid in game_order:
        path = os.path.join(a.tables, gid + ".csv")
        rows = load_rows(path, gid)
        cuts[gid] = assign_cells(rows)
        all_rows[gid] = rows
        print("  %-18s rows=%d  tercile cuts ratio p33=%.4f p67=%.4f"
              % (gid, len(rows), cuts[gid][0], cuts[gid][1]))

    res_of = {picked[r][0]: r for r in picked}
    sample, cell_counts, shortfalls = [], [], collections.Counter()
    for tercile, region in CELL_ORDER:
        pools = {}
        for gid in game_order:
            pool = [r for r in all_rows[gid]
                    if r["tercile"] == tercile and r["region"] == region]
            pool.sort(key=lambda r: r["key"])
            pools[gid] = pool
        taken, sf = fill_cell(pools, game_order)
        shortfalls.update(sf)
        cell = "%s-%s" % (tercile, region)
        per_game = collections.Counter(r["game_id"] for r in taken)
        for gid in game_order:
            cell_counts.append({
                "cell": cell, "game_id": gid, "n_candidates": len(pools[gid]),
                "n_drawn": per_game.get(gid, 0), "shortfall_slots": sf.get(gid, 0),
            })
        for r in taken:
            r["cell"], r["source_resolution"] = cell, res_of[r["game_id"]]
            sample.append(r)

    for i, r in enumerate(sample, 1):
        r["panel_id"] = "P%02d" % i

    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SAMPLE_COLS, extrasaction="ignore")
        w.writeheader()
        for r in sample:
            w.writerow(r)
    with open(a.cells, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "cell", "game_id", "n_candidates", "n_drawn", "shortfall_slots"])
        w.writeheader()
        w.writerows(cell_counts)

    print("SAMPLE: %d panels over %d cells" % (len(sample), len(CELL_ORDER)))
    for row in cell_counts:
        print("  %-9s %-18s candidates=%-6d drawn=%-3d shortfall=%d"
              % (row["cell"], row["game_id"], row["n_candidates"],
                 row["n_drawn"], row["shortfall_slots"]))
    if shortfalls:
        print("SHORTFALL SLOTS PASSED ON (prereg section 4): %s" % dict(shortfalls))
    else:
        print("SHORTFALL SLOTS PASSED ON: none")
    return 0 if len(sample) == PER_CELL * len(CELL_ORDER) else 1


if __name__ == "__main__":
    sys.exit(main())
