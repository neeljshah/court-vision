"""Merge G296's two independent locator passes and measure their agreement.

G296 runs the SAME spec on the SAME 24 deterministic clip-wide frames twice, pass A on
gpt-5.6-terra and pass B on gpt-6-astra, each forbidden to read the other. This module is
the verifier's side: it joins the two and reports how much they agree, then emits the
consensus set that later recall rows may use.

Why two passes at all: G291 measured Cohen's kappa 0.283 between two model raters on a much
easier four-category task, so a single-rater ground truth would put an unmeasured labeller
variance underneath everything built on it.

MEASUREMENT ONLY. Reads two committed CSVs, writes nothing unless asked for the consensus.
Two model locators agreeing measures REPRODUCIBILITY, never CORRECTNESS -- both can be wrong
the same way, and no human has checked these frames.

Run:  python -m scripts.platformkit.tracking.g296_merge_locators
"""
from __future__ import annotations

import csv
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

EVID = Path("docs/evidence/tracking")
PASS_A = EVID / "g296a_located_players_artifact" / "located_players.csv"
PASS_B = EVID / "g296b_located_players_artifact" / "located_players.csv"

# A point pairs with the other pass's point only within this radius. It is a CHOSEN
# tolerance, not a derived one: a foot in a 1080p broadcast is uncertain at tens of pixels
# for distant players, which is what the passes' own `confidence` field records.
MATCH_RADIUS_PX = 60.0
PLAYER_ROLE = "player_on_court"


def load_points(path: Path, role: str = PLAYER_ROLE):
    """Located points with a coordinate, keyed by source frame. Rows with feet_visible
    false carry no coordinate and are counted separately, never guessed into a position."""
    located, no_coord = defaultdict(list), 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("role") or "").strip() != role:
                continue
            x, y = (row.get("foot_x_px") or "").strip(), (row.get("foot_y_px") or "").strip()
            if not x or not y:
                no_coord += 1
                continue
            located[int(row["source_frame"])].append(
                (float(x), float(y), (row.get("confidence") or "").strip())
            )
    return located, no_coord


def match_frame(a_pts, b_pts, radius=MATCH_RADIUS_PX):
    """Greedy mutual-nearest matching within `radius`. Greedy is not globally optimal;
    it is used because the point counts per frame are small and the alternative (Hungarian)
    would add a dependency for a difference that cannot matter at these sizes."""
    pairs, used_b = [], set()
    order = sorted(
        ((math.dist(a[:2], b[:2]), i, j) for i, a in enumerate(a_pts) for j, b in enumerate(b_pts)),
        key=lambda t: t[0],
    )
    used_a = set()
    for dist, i, j in order:
        if dist > radius or i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append((i, j, dist))
    return pairs, used_a, used_b


def agreement(path_a: Path = PASS_A, path_b: Path = PASS_B, radius=MATCH_RADIUS_PX):
    """Per-frame and overall agreement between the two independent locator passes."""
    a_all, a_no_coord = load_points(path_a)
    b_all, b_no_coord = load_points(path_b)
    frames = sorted(set(a_all) | set(b_all))
    matched = a_only = b_only = 0
    offsets, per_frame = [], []
    for frame in frames:
        a_pts, b_pts = a_all.get(frame, []), b_all.get(frame, [])
        pairs, used_a, used_b = match_frame(a_pts, b_pts, radius)
        matched += len(pairs)
        a_only += len(a_pts) - len(used_a)
        b_only += len(b_pts) - len(used_b)
        offsets.extend(d for _, _, d in pairs)
        per_frame.append(
            {
                "source_frame": frame,
                "pass_a": len(a_pts),
                "pass_b": len(b_pts),
                "matched": len(pairs),
                "a_only": len(a_pts) - len(used_a),
                "b_only": len(b_pts) - len(used_b),
            }
        )
    union = matched + a_only + b_only
    return {
        "frames": len(frames),
        "pass_a_points": sum(len(v) for v in a_all.values()),
        "pass_b_points": sum(len(v) for v in b_all.values()),
        "pass_a_no_coordinate": a_no_coord,
        "pass_b_no_coordinate": b_no_coord,
        "matched_pairs": matched,
        "pass_a_only": a_only,
        "pass_b_only": b_only,
        # Jaccard over the union of located players: the headline agreement number.
        "jaccard": matched / union if union else None,
        "median_offset_px": st.median(offsets) if offsets else None,
        "p90_offset_px": sorted(offsets)[int(0.9 * len(offsets))] if offsets else None,
        "match_radius_px": radius,
        "per_frame": per_frame,
    }


def consensus(path_a: Path = PASS_A, path_b: Path = PASS_B, radius=MATCH_RADIUS_PX):
    """Points BOTH passes located, at their midpoint. This is the set a later recall row
    should use: it excludes every point only one locator saw, so it is deliberately
    CONSERVATIVE and under-counts real players rather than inventing them."""
    a_all, _ = load_points(path_a)
    b_all, _ = load_points(path_b)
    out = []
    for frame in sorted(set(a_all) & set(b_all)):
        a_pts, b_pts = a_all[frame], b_all[frame]
        pairs, _, _ = match_frame(a_pts, b_pts, radius)
        for i, j, dist in pairs:
            out.append(
                {
                    "source_frame": frame,
                    "foot_x_px": (a_pts[i][0] + b_pts[j][0]) / 2,
                    "foot_y_px": (a_pts[i][1] + b_pts[j][1]) / 2,
                    "pass_offset_px": dist,
                    "confidence_a": a_pts[i][2],
                    "confidence_b": b_pts[j][2],
                }
            )
    return out


def main() -> None:
    if not (PASS_A.exists() and PASS_B.exists()):
        missing = [str(p) for p in (PASS_A, PASS_B) if not p.exists()]
        print(f"WAITING: locator pass not landed yet: {', '.join(missing)}")
        return
    result = agreement()
    print(f"frames                 {result['frames']}")
    print(f"pass A / pass B points {result['pass_a_points']} / {result['pass_b_points']}")
    print(f"matched pairs          {result['matched_pairs']} (radius {result['match_radius_px']} px)")
    print(f"A only / B only        {result['pass_a_only']} / {result['pass_b_only']}")
    print(f"jaccard agreement      {result['jaccard']}")
    print(f"median / p90 offset px {result['median_offset_px']} / {result['p90_offset_px']}")
    print(f"consensus points       {len(consensus())}")


if __name__ == "__main__":
    main()
