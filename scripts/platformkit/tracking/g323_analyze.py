"""G323 -- gate reproduction on the 60 crops, two-rater agreement, and the two sealed verdicts.

Prereg: docs/evidence/tracking/g323_prereg_2026-09-07.md sections 6, 8, 9 and 10.
SURVIVORSHIP, declared: every sampled row was WRITTEN to tracking_data.csv, so it already passed
every gate in the write route. The gate PASS count is 0-rejection a priori; this is a REPRODUCTION
check of the standalone gate, not a discovery of rejections.

The team-colour gate re-run mirrors src/tracking/advanced_tracker.py:1341-1356 exactly: adaptive HSV
ranges from the POST-TOPCUT frame, cv2.inRange over the upper 70 pct of the UNPADDED crop, argmax of
the nonzero counts, and an all-zero result treated as the `if not team: continue` reject.

Usage:
  python scripts/platformkit/tracking/g323_analyze.py --sample <csv> --rater-a <csv> --rater-b <csv> \
      --frames <dir> --maps <dir> --gate-out <csv> --agreement-out <csv>
"""
from __future__ import annotations

import argparse
import collections
import csv
import glob
import math
import os
import sys

import cv2
import numpy as np

TOPCUT = 60
PAD = 15          # src/tracking/player_detection.py:20 -- asserted against the real import below
JERSEY_FRAC = 0.70
NON_PLAYER = {"crowd", "referee_or_staff", "broadcast_graphic",
              "off_frame_or_empty", "player_bench_or_courtside"}
PREMISE_BAR = 10
GATE_BAR = 0.50


def gate_imports():
    """Import the production colour gate (import only, never edited). Lazy: only the gate path
    needs it, so the sample and agreement arithmetic stay testable without the src dependency."""
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))))
    from src.tracking.player_detection import _adaptive_colors, PAD as SRC_PAD
    assert SRC_PAD == PAD, "PAD drifted from src/tracking/player_detection.py: %r" % (SRC_PAD,)
    return _adaptive_colors


def unpad(row, w, h):
    """CSV bbox back to the raw detector box the gate saw, clamped to the post-TOPCUT frame."""
    x1 = int(float(row["bbox_x1"])) + PAD
    y1 = int(float(row["bbox_y1"])) + PAD
    x2 = int(float(row["bbox_x2"])) - PAD
    y2 = int(float(row["bbox_y2"])) - PAD
    return max(0, x1), max(0, y1), min(w, x2), min(h, y2)


def gate_team_colour(frame_post, box, adaptive_colors):
    """Re-run advanced_tracker.py:1341-1356 standalone. Returns (team, best_n, per-range counts)."""
    x1, y1, x2, y2 = box
    crop = frame_post[y1:y2, x1:x2]
    if crop.size == 0:
        return "", 0, {}
    jersey_h = max(1, int(crop.shape[0] * JERSEY_FRAC))
    hsv = cv2.cvtColor(crop[:jersey_h], cv2.COLOR_BGR2HSV)
    counts = {}
    team, best_n = "", 0
    for key, rng in adaptive_colors(frame_post).items():
        n = int(cv2.countNonZero(cv2.inRange(hsv, np.array(rng[0]), np.array(rng[1]))))
        counts[key] = n
        if n > best_n:
            best_n, team = n, key
    return team, best_n, counts


def cohens_kappa(pairs):
    """Unweighted Cohen's kappa with the asymptotic SE of prereg section 8."""
    n = len(pairs)
    po = sum(1 for a, b in pairs if a == b) / float(n)
    ca = collections.Counter(a for a, _ in pairs)
    cb = collections.Counter(b for _, b in pairs)
    pe = sum((ca[c] / float(n)) * (cb[c] / float(n)) for c in set(ca) | set(cb))
    if abs(1.0 - pe) < 1e-12:
        return po, pe, None, None
    kappa = (po - pe) / (1.0 - pe)
    se = math.sqrt(po * (1.0 - po) / (n * (1.0 - pe) ** 2))
    return po, pe, kappa, se


def frame_index(maps_dir):
    idx = {}
    for path in glob.glob(os.path.join(maps_dir, "map_*.txt")):
        game = os.path.basename(path)[4:-4]
        for line in open(path):
            name, frame = line.split()
            idx[(game, int(frame))] = name
    return idx


def _read(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def main(argv=None):
    ap = argparse.ArgumentParser()
    for flag in ("--sample", "--rater-a", "--rater-b", "--frames", "--maps",
                 "--gate-out", "--agreement-out"):
        ap.add_argument(flag, required=True)
    a = ap.parse_args(argv)

    sample = _read(a.sample)
    lab_a = {r["panel_id"]: r["category"] for r in _read(a.rater_a)}
    lab_b = {r["panel_id"]: r["category"] for r in _read(a.rater_b)}
    idx = frame_index(a.maps)
    adaptive_colors = gate_imports()

    gate_rows = []
    for row in sample:
        name = idx[(row["game_id"], int(row["frame"]))]
        img = cv2.imread(os.path.join(a.frames, name))
        post = img[TOPCUT:]
        h, w = post.shape[:2]
        box = unpad(row, w, h)
        team, best_n, counts = gate_team_colour(post, box, adaptive_colors)
        gate_rows.append({
            "panel_id": row["panel_id"], "game_id": row["game_id"], "cell": row["cell"],
            "cat_a": lab_a[row["panel_id"]], "cat_b": lab_b[row["panel_id"]],
            "gate_verdict": "PASS" if team else "REJECT", "matched_range": team,
            "matched_pixels": best_n,
            "n_green": counts.get("green", 0), "n_white": counts.get("white", 0),
            "n_referee": counts.get("referee", 0),
            "crop_w": box[2] - box[0], "crop_h": box[3] - box[1],
        })
    with open(a.gate_out, "w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=list(gate_rows[0].keys()))
        w_.writeheader()
        w_.writerows(gate_rows)

    pairs = [(lab_a[r["panel_id"]], lab_b[r["panel_id"]]) for r in sample]
    po, pe, kappa, se = cohens_kappa(pairs)
    n = len(pairs)
    ca = collections.Counter(x for x, _ in pairs)
    cb = collections.Counter(x for _, x in pairs)
    np_a = sum(v for k, v in ca.items() if k in NON_PLAYER)
    np_b = sum(v for k, v in cb.items() if k in NON_PLAYER)
    # Acceptance denominator, corrected at landing (codex-sol verifier): a panel counts as
    # both-rater non-player when BOTH labels fall in the sealed NON_PLAYER set. Requiring the
    # detailed categories to be identical collapsed the denominator and inflated the share.
    agreed = [r["panel_id"] for r in sample
              if lab_a[r["panel_id"]] in NON_PLAYER
              and lab_b[r["panel_id"]] in NON_PLAYER]
    rejected = sum(1 for g in gate_rows
                   if g["panel_id"] in agreed and g["gate_verdict"] == "REJECT")

    print("RATER COUNTS (n = %d)" % n)
    for cat in sorted(set(ca) | set(cb)):
        print("  %-26s A=%-3d B=%-3d" % (cat, ca.get(cat, 0), cb.get(cat, 0)))
    print("NON_PLAYER: A=%d/%d  B=%d/%d" % (np_a, n, np_b, n))
    print("AGREEMENT: po=%.4f pe=%.4f kappa=%s SE=%s"
          % (po, pe, "UNDEFINED" if kappa is None else "%.4f" % kappa,
             "UNDEFINED" if se is None else "%.4f" % se))
    if kappa is not None:
        print("  kappa 95 pct asymptotic interval: %.4f to %.4f"
              % (kappa - 1.96 * se, kappa + 1.96 * se))
    print("CONFUSION (A row, B column), nonzero cells only:")
    conf = collections.Counter(pairs)
    for (x, y), c in sorted(conf.items()):
        print("  %-26s %-26s %d" % (x, y, c))
    gv = collections.Counter((g["cat_a"], g["gate_verdict"]) for g in gate_rows)
    print("GATE REPRODUCTION by rater-A category (denominator = 60):")
    for cat in sorted(ca):
        print("  %-26s PASS=%-3d REJECT=%d" % (cat, gv.get((cat, "PASS"), 0),
                                               gv.get((cat, "REJECT"), 0)))
    matched = collections.Counter(g["matched_range"] for g in gate_rows)
    print("MATCHED RANGE over all 60: %s" % dict(matched))
    print("NON_PLAYER by game and by cell (counts; denominator is the rated panels in that group):")
    for field in ("game_id", "cell"):
        groups = collections.defaultdict(lambda: [0, 0, 0, 0])
        for r in sample:
            g = groups[r[field]]
            g[0] += 1
            g[1] += 1 if lab_a[r["panel_id"]] in NON_PLAYER else 0
            g[2] += 1 if lab_b[r["panel_id"]] in NON_PLAYER else 0
            g[3] += 1 if r["panel_id"] in agreed else 0
        for k in sorted(groups):
            n_, a_, b_, ag_ = groups[k]
            print("  %-9s %-18s n=%-3d A=%-3d B=%-3d both=%d" % (field, k, n_, a_, b_, ag_))

    premise = "PREMISE HOLDS" if max(np_a, np_b) >= PREMISE_BAR else "PREMISE FALSE"
    if not agreed:
        gate = "GATE VERDICT UNDEFINED (both-rater-agreed NON_PLAYER set is empty)"
    else:
        frac = rejected / float(len(agreed))
        gate = ("GATE MISSING" if frac < GATE_BAR else "GATES SUFFICIENT")
        gate += " (gate rejects %d of %d both-agreed NON_PLAYER = %.6f, bar %.2f)" % (
            rejected, len(agreed), frac, GATE_BAR)
    print("VERDICT: %s (bar %d/60); %s" % (premise, PREMISE_BAR, gate))

    with open(a.agreement_out, "w", newline="") as fh:
        w_ = csv.writer(fh)
        w_.writerow(["statistic", "value"])
        for k, v in (("n", n), ("po", "%.6f" % po), ("pe", "%.6f" % pe),
                     ("kappa", "UNDEFINED" if kappa is None else "%.6f" % kappa),
                     ("kappa_se_asymptotic", "UNDEFINED" if se is None else "%.6f" % se),
                     ("non_player_a", np_a), ("non_player_b", np_b),
                     ("both_agreed_non_player", len(agreed)),
                     ("gate_rejects_of_agreed", rejected),
                     ("premise_verdict", premise), ("gate_verdict", gate)):
            w_.writerow([k, v])
        w_.writerow(["confusion_a__b", "count"])
        for (x, y), c in sorted(conf.items()):
            w_.writerow(["%s__%s" % (x, y), c])
    return 0


if __name__ == "__main__":
    sys.exit(main())
