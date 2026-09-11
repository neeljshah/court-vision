"""Retrospective rescore of the two older trace generations under the G388 band rule.

Run only AFTER the new G388 labels are sealed. Diagnosis only; never independent
confirmation, and no missing old annotation is regenerated.
"""
import csv, json, math, pathlib, sys

ROOT = pathlib.Path("docs/evidence/tracking")
G382 = ROOT / "g382_court_stroke_specificity_2026-09-10"
G387 = ROOT / "g387_paint_localization_controls_2026-09-11"
OUT = ROOT / "g388_paint_band_protocol_2026-09-11"
TOL = 6.0


def read(path):
    with path.open(encoding="utf-8", newline="") as h:
        return list(csv.DictReader(h))


def long_axis(points):
    """Return the two polygon vertices furthest apart: the band's long axis."""
    best, pair = -1.0, None
    for i, a in enumerate(points):
        for b in points[i + 1:]:
            d = math.dist(a, b)
            if d > best:
                best, pair = d, (a, b)
    return pair


def dist_to_line(point, line):
    (x1, y1), (x2, y2) = line
    dx, dy = x2 - x1, y2 - y1
    n = math.hypot(dx, dy)
    if n == 0:
        return float("inf")
    return abs((point[0] - x1) * dy - (point[1] - y1) * dx) / n


def symmetric(a, b):
    return (sum(dist_to_line(p, b) for p in a) + sum(dist_to_line(p, a) for p in b)) / 4.0


def gen1():
    """G382 polygon traces: same-band membership of each rater's long axis."""
    rows = [r for r in read(G382 / "ratings.csv") if r["kind"] == "PAINTED"]
    by = {}
    for r in rows:
        by.setdefault((r["frame_key"], r["identifier"]), {})[r["rater"]] = json.loads(r["polygon"])
    out, same = [], 0
    for (frame, ident), raters in sorted(by.items()):
        if len(raters) != 2:
            continue
        axes = {k: long_axis([tuple(map(float, p)) for p in v]) for k, v in raters.items()}
        d = symmetric(axes["terra"], axes["sol"])
        hit = d <= TOL
        same += hit
        out.append({"generation": "G382", "unit": "%s|%s" % (frame, ident),
                    "symmetric_line_px": "%.2f" % d, "same_band_under_g388_rule": "YES" if hit else "NO"})
    return out, same


def gen2():
    """G387 endpoint/midpoint traces: reuse its own recorded collinear deviation."""
    out, same = [], 0
    for r in read(G387 / "adjudication.csv"):
        if not r["collinear_dev_px"]:
            continue
        d = float(r["collinear_dev_px"])
        hit = d <= TOL
        same += hit
        out.append({"generation": "G387", "unit": "%s|%s" % (r["opaque_id"], r["pair_id"]),
                    "symmetric_line_px": "%.2f" % d, "same_band_under_g388_rule": "YES" if hit else "NO"})
    return out, same


def main():
    rows1, same1 = gen1()
    rows2, same2 = gen2()
    rows = rows1 + rows2
    path = OUT / "retrospective_rescore.csv"
    with path.open("w", encoding="utf-8", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader(); w.writerows(rows)
    summary = {"label": "RETROSPECTIVE DIAGNOSIS ONLY -- not independent confirmation",
               "rule": "symmetric infinite-line distance <= %.0f px" % TOL,
               "G382_shared_units": len(rows1), "G382_same_band": same1,
               "G387_shared_units": len(rows2), "G387_same_band": same2,
               "G387_under_its_own_endpoint_rule": 1}
    (OUT / "retrospective_rescore.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
