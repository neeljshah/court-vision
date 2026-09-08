"""G315 -- same-id step SCREEN. Counts id-swap CANDIDATES; adjudicates nothing.

A SCREEN, NOT A FIX. Read-only over fetched `tracking_data.csv` copies. Image space only
(`coordinate_space = image_px`): no court, foot, metre or registration claim is made or
implied, and no metric here is recall, precision, accuracy or a swap RATE.

Conventions are the G315 seal (`docs/evidence/tracking/g315_prereg_2026-09-07.md`):
footpoint = bbox bottom-centre; a step is two consecutive same-`player_id` observations
ordered by `frame` with NO interpolation across a gap; displacement is Euclidean image px
over `source_height`; percentiles are NEAREST-RANK; a CANDIDATE is a step strictly above
0.30; gap bins are B1 gap == stride, B2 stride < gap <= 5*stride, B3 gap > 5*stride.

  python -m scripts.platformkit.tracking.g315_same_id_step_screen \
      --tables <dir with <game>/tracking_data.csv> --out-prefix <path prefix>
"""

from __future__ import annotations

import argparse
import collections
import csv
import math
import os
import sys

CANDIDATE_THRESHOLD = 0.30  # sealed by the G315 prereg; MAY NOT be moved
GAP_BIN_B2_MULT = 5
N_EXAMPLES = 10

DIST_COLUMNS = [
    "game_id", "rows", "dropped_rows", "source_height", "stride", "distinct_track_ids",
    "n_steps", "p50_nr", "p75_nr", "p95_nr", "max_step", "share_gt_0p30",
    "n_candidates", "cand_share_of_steps", "cand_b1_one_stride", "cand_b2_le5x",
    "cand_b3_gt5x", "n_examples",
]
EXAMPLE_COLUMNS = [
    "panel_id", "game_id", "player_id", "frame_a", "frame_b", "gap", "gap_bin",
    "step_norm", "cand_rank", "n_candidates", "ax1", "ay1", "ax2", "ay2",
    "bx1", "by1", "bx2", "by2",
]


def _f(v):
    """Parse a CSV cell as a finite float, else None."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def nearest_rank(vals, q):
    """sorted[ceil(q*n)-1]; no interpolation. Sealed convention."""
    if not vals:
        return None
    s = sorted(vals)
    return s[max(0, math.ceil(q * len(s)) - 1)]


def modal_stride(frames):
    """Modal positive difference between consecutive DISTINCT frame values."""
    s = sorted(set(frames))
    diffs = [b - a for a, b in zip(s, s[1:]) if b > a]
    if not diffs:
        return None
    return collections.Counter(diffs).most_common(1)[0][0]


def read_steps(path):
    """One pass over tracking_data.csv -> (steps, rows, dropped, height, stride, n_ids).

    A step dict carries player_id, frame_a/frame_b, gap, step_norm and both bboxes.
    """
    tracks, rows, dropped, height, frames = {}, 0, 0, None, []
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        for r in csv.DictReader(fh):
            rows += 1
            if height is None:
                height = _f(r.get("source_height"))
            fi = _f(r.get("frame"))
            x1, y1 = _f(r.get("bbox_x1")), _f(r.get("bbox_y1"))
            x2, y2 = _f(r.get("bbox_x2")), _f(r.get("bbox_y2"))
            if None in (fi, x1, x2, y2):
                dropped += 1
                continue
            frames.append(fi)
            tracks.setdefault(r.get("player_id"), []).append((fi, x1, y1, x2, y2))

    stride = modal_stride(frames)
    steps = []
    for pid, obs in tracks.items():
        pts = sorted(obs)
        for a, b in zip(pts, pts[1:]):
            fa, ax1, ay1, ax2, ay2 = a
            fb, bx1, by1, bx2, by2 = b
            d = math.hypot(((bx1 + bx2) / 2.0) - ((ax1 + ax2) / 2.0), by2 - ay2)
            steps.append({
                "player_id": pid, "frame_a": int(fa), "frame_b": int(fb),
                "gap": int(fb - fa), "step_norm": (d / height) if height else None,
                "ax1": ax1, "ay1": ay1, "ax2": ax2, "ay2": ay2,
                "bx1": bx1, "by1": by1, "bx2": bx2, "by2": by2,
            })
    return steps, rows, dropped, height, stride, len(tracks)


def gap_bin(gap, stride):
    """B1 == one stride, B2 <= 5x stride, B3 beyond. Never pooled into one number."""
    if stride is None:
        return "B_unknown_stride"
    if gap == stride:
        return "B1_one_stride"
    if gap <= GAP_BIN_B2_MULT * stride:
        return "B2_le5x"
    return "B3_gt5x"


def pick_examples(cands, k=N_EXAMPLES):
    """Decile MIDPOINTS of the candidate distribution, ascending: an even sweep, not a
    top-k tail slice (contract A3/B7). Returns [(rank_1indexed, step), ...]."""
    n = len(cands)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: (cands[i]["step_norm"], i))
    if n <= k:
        return [(r + 1, cands[i]) for r, i in enumerate(order)]
    ranks, out = [], []
    for i in range(k):
        # ceil((2i+1)/(2k) * n) in EXACT integer arithmetic: the float form returns
        # 55.00000000000001 -> 56 at n=100, i=5, which is a rounding artifact, not the rule.
        rank = max(1, min(n, -((-(2 * i + 1) * n) // (2 * k))))
        if rank not in ranks:
            ranks.append(rank)
    for rank in ranks:
        out.append((rank, cands[order[rank - 1]]))
    return out


def screen_game(game_id, path):
    """Full per-game screen. Returns (dist_row, example_rows)."""
    steps, rows, dropped, height, stride, n_ids = read_steps(path)
    vals = [s["step_norm"] for s in steps if s["step_norm"] is not None]
    cands = [s for s in steps if s["step_norm"] is not None
             and s["step_norm"] > CANDIDATE_THRESHOLD]
    bins = collections.Counter(gap_bin(c["gap"], stride) for c in cands)
    picked = pick_examples(cands)

    dist = {
        "game_id": game_id, "rows": rows, "dropped_rows": dropped,
        "source_height": height, "stride": stride, "distinct_track_ids": n_ids,
        "n_steps": len(steps),
        "p50_nr": nearest_rank(vals, 0.50), "p75_nr": nearest_rank(vals, 0.75),
        "p95_nr": nearest_rank(vals, 0.95), "max_step": max(vals) if vals else None,
        "share_gt_0p30": (len(cands) / len(vals)) if vals else None,
        "n_candidates": len(cands),
        "cand_share_of_steps": (len(cands) / len(steps)) if steps else None,
        "cand_b1_one_stride": bins.get("B1_one_stride", 0),
        "cand_b2_le5x": bins.get("B2_le5x", 0),
        "cand_b3_gt5x": bins.get("B3_gt5x", 0),
        "n_examples": len(picked),
    }
    examples = []
    for i, (rank, c) in enumerate(picked, start=1):
        row = {"panel_id": "%s_%02d" % (game_id, i), "game_id": game_id,
               "gap_bin": gap_bin(c["gap"], stride), "cand_rank": rank,
               "n_candidates": len(cands)}
        row.update({k: c[k] for k in ("player_id", "frame_a", "frame_b", "gap",
                                      "step_norm", "ax1", "ay1", "ax2", "ay2",
                                      "bx1", "by1", "bx2", "by2")})
        examples.append(row)
    return dist, examples


def main(argv=None):
    ap = argparse.ArgumentParser(description="G315 same-id step screen (measurement only)")
    ap.add_argument("--tables", required=True,
                    help="dir holding <game_id>/tracking_data.csv copies")
    ap.add_argument("--out-prefix", required=True, help="output path prefix")
    args = ap.parse_args(argv)

    games = sorted(g for g in os.listdir(args.tables)
                   if os.path.exists(os.path.join(args.tables, g, "tracking_data.csv")))
    if not games:
        print("NO GAMES under %s" % args.tables)
        return 2

    dists, examples = [], []
    for g in games:
        d, ex = screen_game(g, os.path.join(args.tables, g, "tracking_data.csv"))
        dists.append(d)
        examples.extend(ex)
        print("%-34s n_steps=%-6d p50=%.4f p75=%.4f p95=%.4f max=%.4f "
              "share>0.30=%.4f cand=%d (B1=%d B2=%d B3=%d) stride=%s h=%s"
              % (g, d["n_steps"], d["p50_nr"], d["p75_nr"], d["p95_nr"], d["max_step"],
                 d["share_gt_0p30"], d["n_candidates"], d["cand_b1_one_stride"],
                 d["cand_b2_le5x"], d["cand_b3_gt5x"], d["stride"], d["source_height"]))

    premise_false = [d["game_id"] for d in dists if (d["p95_nr"] or 0) < CANDIDATE_THRESHOLD]
    print("PREMISE: p95 >= 0.30 on all %d games -> %s%s"
          % (len(dists), "HOLDS" if not premise_false else "FALSE",
             "" if not premise_false else " (" + ",".join(premise_false) + ")"))

    for path, cols, rows_ in ((args.out_prefix + ".csv", DIST_COLUMNS, dists),
                              (args.out_prefix + "_examples.csv", EXAMPLE_COLUMNS,
                               examples)):
        with open(path, "w", encoding="ascii", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for r in rows_:
                w.writerow(r)
        print("WROTE %s (%d rows)" % (path, len(rows_)))
    return 0 if not premise_false else 1


if __name__ == "__main__":
    sys.exit(main())
