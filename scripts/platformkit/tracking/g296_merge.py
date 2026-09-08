"""G296 merge: frame identity, one-to-one matching and adjudication bookkeeping.

Rules are sealed in docs/evidence/tracking/g296_merge_prereg_2026-09-07.md
(sha256 dcfa4d4be8f735dd1832bbe499991d88e3c34ef25654ae7819d96439c321b5d5).
Headless only: images are written to disk and read back, never displayed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys

FRAMES = [round(i * 174429 / 23) for i in range(24)]
RADIUS = 50.0
ADJUDICATE_ABOVE = 4.0
ART = "docs/evidence/tracking/g296_merge_artifact"
A_DIR = "docs/evidence/tracking/g296a_located_players_artifact"
B_DIR = "docs/evidence/tracking/g296b_located_players_artifact"
HEADER = ["source_frame", "person_index", "role", "feet_visible",
          "foot_x_px", "foot_y_px", "confidence", "note"]
GT_HEADER = ["frame_id", "player_ordinal", "x", "y", "source", "distance_px", "note"]


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def load_labels(path: str) -> list[dict]:
    """Read a pass CSV, assert the sealed header, return rows with parsed coords."""
    with open(path, newline="", encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        if rdr.fieldnames != HEADER:
            raise SystemExit("schema mismatch in %s: %s" % (path, rdr.fieldnames))
        rows = []
        for r in rdr:
            r["source_frame"] = int(r["source_frame"])
            r["person_index"] = int(r["person_index"])
            vis = r["feet_visible"].strip().lower() == "true"
            try:
                xy = (float(r["foot_x_px"]), float(r["foot_y_px"]))
            except ValueError:
                xy = None
            # R2: matchable iff feet_visible true AND both coordinates parse
            r["xy"] = xy if vis else None
            r["visible"] = vis
            rows.append(r)
    return rows


def eligible(rows: list[dict], frame: int, role: str) -> list[dict]:
    out = [r for r in rows if r["source_frame"] == frame and r["role"] == role
           and r["xy"] is not None]
    return sorted(out, key=lambda r: r["person_index"])


def match(a: list[dict], b: list[dict], radius: float):
    """R4: Hungarian on Euclidean distance, then break pairs beyond the radius."""
    import numpy as np
    from scipy.optimize import linear_sum_assignment
    if not a or not b:
        return [], list(range(len(a))), list(range(len(b)))
    pa = np.array([r["xy"] for r in a], dtype=float)
    pb = np.array([r["xy"] for r in b], dtype=float)
    cost = np.linalg.norm(pa[:, None, :] - pb[None, :, :], axis=2)
    ri, ci = linear_sum_assignment(cost)
    pairs, ma, mb = [], set(), set()
    for i, j in zip(ri, ci):
        d = float(cost[i, j])
        if d <= radius:
            pairs.append((int(i), int(j), d))
            ma.add(int(i))
            mb.add(int(j))
    return (pairs,
            [i for i in range(len(a)) if i not in ma],
            [j for j in range(len(b)) if j not in mb])


def percentile(vals: list[float], q: float) -> float:
    if not vals:
        return float("nan")
    s = sorted(vals)
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def run_match(radius: float = RADIUS, write: bool = True) -> dict:
    arows = load_labels(A_DIR + "/located_players.csv")
    brows = load_labels(B_DIR + "/located_players.csv")
    out = {"radius": radius, "roles": {}}
    pair_rows = []
    for role in ("player_on_court", "official"):
        per_frame = []
        tot = {"matched": 0, "a_elig": 0, "b_elig": 0, "a_only": 0, "b_only": 0}
        dists = []
        for f in FRAMES:
            a = eligible(arows, f, role)
            b = eligible(brows, f, role)
            pairs, ao, bo = match(a, b, radius)
            per_frame.append({"frame": f, "a_elig": len(a), "b_elig": len(b),
                              "matched": len(pairs), "a_only": len(ao), "b_only": len(bo),
                              "median_px": round(percentile([d for _, _, d in pairs], 0.5), 3)
                              if pairs else None})
            tot["matched"] += len(pairs)
            tot["a_elig"] += len(a)
            tot["b_elig"] += len(b)
            tot["a_only"] += len(ao)
            tot["b_only"] += len(bo)
            dists += [d for _, _, d in pairs]
            for i, j, d in pairs:
                pair_rows.append([f, role, "pair", a[i]["person_index"], b[j]["person_index"],
                                  a[i]["xy"][0], a[i]["xy"][1], b[j]["xy"][0], b[j]["xy"][1],
                                  round(d, 3), a[i]["note"], b[j]["note"]])
            for i in ao:
                pair_rows.append([f, role, "a_only", a[i]["person_index"], "",
                                  a[i]["xy"][0], a[i]["xy"][1], "", "", "", a[i]["note"], ""])
            for j in bo:
                pair_rows.append([f, role, "b_only", "", b[j]["person_index"], "", "",
                                  b[j]["xy"][0], b[j]["xy"][1], "", "", b[j]["note"]])
        tot["median_px"] = round(percentile(dists, 0.5), 3)
        tot["p90_px"] = round(percentile(dists, 0.9), 3)
        tot["over_adjudicate_threshold"] = sum(1 for d in dists if d > ADJUDICATE_ABOVE)
        tot["agree_share_of_A"] = round(tot["matched"] / tot["a_elig"], 4) if tot["a_elig"] else None
        tot["agree_share_of_B"] = round(tot["matched"] / tot["b_elig"], 4) if tot["b_elig"] else None
        out["roles"][role] = {"total": tot, "per_frame": per_frame}
    counts = {}
    for tag, rows in (("A", arows), ("B", brows)):
        counts[tag] = {"rows": len(rows),
                       "no_coordinate": sum(1 for r in rows if r["xy"] is None),
                       "by_role": {}}
        for r in rows:
            counts[tag]["by_role"][r["role"]] = counts[tag]["by_role"].get(r["role"], 0) + 1
    out["label_counts"] = counts
    if write:
        os.makedirs(ART, exist_ok=True)
        with open(ART + "/pairs.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["frame", "role", "kind", "a_index", "b_index", "ax", "ay", "bx", "by",
                        "distance_px", "a_note", "b_note"])
            w.writerows(pair_rows)
        with open(ART + "/match_stats.json", "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=1)
    return out


def identity() -> list[dict]:
    """Paired vs adjacent-index decoded-pixel MAD; the JPEGs are not byte-identical."""
    import cv2
    import numpy as np
    rows = []
    for i, n in enumerate(FRAMES):
        pa = "%s/frames/frame_%02d.jpg" % (A_DIR, i + 1)
        pb = "%s/frames/frame_%06d.jpg" % (B_DIR, n)
        ia = cv2.imread(pa)
        ib = cv2.imread(pb)
        mad = float(np.mean(np.abs(ia.astype(np.int16) - ib.astype(np.int16))))
        ctl = None
        if i + 1 < len(FRAMES):
            ic = cv2.imread("%s/frames/frame_%06d.jpg" % (B_DIR, FRAMES[i + 1]))
            ctl = float(np.mean(np.abs(ia.astype(np.int16) - ic.astype(np.int16))))
        rows.append({"frame": n, "shape_a": list(ia.shape), "shape_b": list(ib.shape),
                     "byte_identical": sha256_file(pa) == sha256_file(pb),
                     "paired_mad": round(mad, 4),
                     "adjacent_control_mad": round(ctl, 4) if ctl is not None else None})
    os.makedirs(ART, exist_ok=True)
    with open(ART + "/frame_identity.json", "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1)
    return rows


def sheets(role: str = "player_on_court", zoom: int = 3, half: int = 60) -> None:
    """R7: per-frame contact sheets of native crops, upscaled INTER_NEAREST for viewing."""
    import cv2
    import numpy as np
    with open(ART + "/pairs.csv", newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["role"] == role]
    todo = [r for r in rows
            if r["kind"] != "pair" or float(r["distance_px"]) > ADJUDICATE_ABOVE]
    os.makedirs(ART + "/sheets", exist_ok=True)
    cell = 2 * half * zoom
    for i, n in enumerate(FRAMES):
        items = [r for r in todo if int(r["frame"]) == n]
        if not items:
            continue
        img = cv2.imread("%s/frames/frame_%02d.jpg" % (A_DIR, i + 1))
        cols = min(4, len(items))
        rowsn = (len(items) + cols - 1) // cols
        sheet = np.zeros((rowsn * (cell + 22), cols * cell, 3), dtype=np.uint8)
        for k, r in enumerate(items):
            xs = [float(v) for v in (r["ax"], r["bx"]) if v]
            ys = [float(v) for v in (r["ay"], r["by"]) if v]
            cx = int(sum(xs) / len(xs))
            cy = int(sum(ys) / len(ys))
            x0 = max(0, min(1920 - 2 * half, cx - half))
            y0 = max(0, min(1080 - 2 * half, cy - half))
            crop = img[y0:y0 + 2 * half, x0:x0 + 2 * half]
            crop = cv2.resize(crop, (cell, cell), interpolation=cv2.INTER_NEAREST)
            if r["ax"]:
                p = (int((float(r["ax"]) - x0) * zoom), int((float(r["ay"]) - y0) * zoom))
                cv2.circle(crop, p, 9, (0, 0, 255), 1)
            if r["bx"]:
                p = (int((float(r["bx"]) - x0) * zoom), int((float(r["by"]) - y0) * zoom))
                cv2.line(crop, (p[0] - 12, p[1]), (p[0] - 4, p[1]), (0, 255, 0), 1)
                cv2.line(crop, (p[0] + 4, p[1]), (p[0] + 12, p[1]), (0, 255, 0), 1)
                cv2.line(crop, (p[0], p[1] - 12), (p[0], p[1] - 4), (0, 255, 0), 1)
                cv2.line(crop, (p[0], p[1] + 4), (p[0], p[1] + 12), (0, 255, 0), 1)
            gy = (k // cols) * (cell + 22)
            gx = (k % cols) * cell
            sheet[gy + 22:gy + 22 + cell, gx:gx + cell] = crop
            tag = "%s a%s b%s d%s" % (r["kind"], r["a_index"] or "-", r["b_index"] or "-",
                                      r["distance_px"] or "-")
            cv2.putText(sheet, tag, (gx + 3, gy + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                        (255, 255, 255), 1)
        cv2.imwrite("%s/sheets/f%06d.jpg" % (ART, n), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])


def finalize(role: str = "player_on_court") -> dict:
    """R6/R8/R10: apply the adjudications to the matched set and write the sealed CSV."""
    with open(ART + "/pairs.csv", newline="", encoding="utf-8") as fh:
        pairs = [r for r in csv.DictReader(fh) if r["role"] == role]
    with open(ART + "/decisions.csv", newline="", encoding="utf-8") as fh:
        dec = {(r["frame"], r["kind"], r["a_index"], r["b_index"]): r
               for r in csv.DictReader(fh)}
    rows, counts = [], {"agreed": 0, "adjudicated_A": 0, "adjudicated_B": 0, "dropped": 0}
    for r in pairs:
        key = (r["frame"], r["kind"], r["a_index"], r["b_index"])
        d = float(r["distance_px"]) if r["distance_px"] else None
        if r["kind"] == "pair" and d is not None and d <= ADJUDICATE_ABOVE:
            src = "agreed"
            xy = (round((float(r["ax"]) + float(r["bx"])) / 2),
                  round((float(r["ay"]) + float(r["by"])) / 2))
            note = "distance within the sealed 4.0 px agreement tolerance"
        else:
            if key not in dec:
                raise SystemExit("no adjudication for %s" % (key,))
            choice, note = dec[key]["decision"], dec[key]["note"]
            if choice == "A":
                src, xy = "adjudicated_A", (round(float(r["ax"])), round(float(r["ay"])))
            elif choice == "B":
                src, xy = "adjudicated_B", (round(float(r["bx"])), round(float(r["by"])))
            else:
                src = "dropped"
                xy = ((round(float(r["ax"])), round(float(r["ay"]))) if r["ax"]
                      else (round(float(r["bx"])), round(float(r["by"]))))
        counts[src] += 1
        rows.append({"frame_id": int(r["frame"]), "x": xy[0], "y": xy[1], "source": src,
                     "distance_px": ("%.3f" % d) if d is not None else "", "note": note})
    out = []
    for f in FRAMES:
        kept = sorted([r for r in rows if r["frame_id"] == f and r["source"] != "dropped"],
                      key=lambda r: (r["x"], r["y"]))
        for i, r in enumerate(kept, 1):
            r["player_ordinal"] = i
            out.append(r)
        for r in [r for r in rows if r["frame_id"] == f and r["source"] == "dropped"]:
            r["player_ordinal"] = 0
            out.append(r)
    path = "docs/evidence/tracking/g296_ground_truth_2026-09-07.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=GT_HEADER)
        w.writeheader()
        for r in out:
            w.writerow({k: r[k] for k in GT_HEADER})
    man = {"ground_truth_csv": path, "sha256": sha256_file(path), "rows": len(out),
           "source_counts": counts,
           "accepted": len(out) - counts["dropped"],
           "prereg": "docs/evidence/tracking/g296_merge_prereg_2026-09-07.md",
           "inputs": {p: sha256_file(p) for p in
                      (A_DIR + "/located_players.csv", B_DIR + "/located_players.csv")}}
    with open(ART + "/ground_truth_manifest.json", "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1)
    return man


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "match"
    if cmd == "finalize":
        print(json.dumps(finalize(), indent=1))
        sys.exit(0)
    if cmd == "identity":
        for r in identity():
            print(r["frame"], r["byte_identical"], r["paired_mad"], r["adjacent_control_mad"])
    elif cmd == "sheets":
        sheets()
        print("sheets written")
    else:
        rad = float(sys.argv[2]) if len(sys.argv) > 2 else RADIUS
        st = run_match(rad, write=(rad == RADIUS))
        print(json.dumps({k: v["total"] for k, v in st["roles"].items()}, indent=1))
