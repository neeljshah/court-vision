"""G303 report writer -- combines the four independently-scored bases into one JSON report.

Split out of `g303_recall_vs_resolution.py` (fix pass 1c, A12 LOC rail) so the harness and
this writer both stay under 300 lines; the scoring math is unchanged, only the file boundary
moved -- `test_g303_recall.py` still imports `score_basis`/`bootstrap_ci` (now from here).

Also carries the B2 backward-compatibility layer the fix-1b REJECT required: the legacy
top-level paths (`primary_denominator`, `primary_denominator_name`, `primary_frame_ids`,
`arms`, `paired_R_vs_P`) are restored as ALIASES of the new `bases[PRIMARY]` sub-tree -- same
objects, same numbers, never recomputed.
"""
from __future__ import annotations

import json

from scripts.platformkit.tracking.g296_merge_locators import consensus
from scripts.platformkit.tracking.g298_compare import exact_mcnemar, read_csv, write_csv
from scripts.platformkit.tracking.g303_recall_vs_resolution import (
    ARMS, NOTE, PRIMARY, REGISTERED_CONF, TOLERANCES, eligible, score_arm)

BOOTSTRAP, SEED = 10000, 20260907


def bootstrap_ci(hits, ns, paired=None):
    """Paired percentile bootstrap over FRAMES; returns [lo, hi] for a rate or delta."""
    import numpy as np
    rng, draws, idx = np.random.default_rng(SEED), [], np.arange(len(ns))
    for _ in range(BOOTSTRAP):
        pick = rng.choice(idx, size=len(idx), replace=True)
        n = max(1, sum(ns[i] for i in pick))
        v = sum(hits[i] for i in pick) / n
        draws.append(sum(paired[i] for i in pick) / n - v if paired is not None else v)
    return [float(x) for x in np.percentile(draws, [2.5, 97.5])]


def bases(args):
    """The four scored point sets. Each carries its OWN points and its OWN denominator;
    no numerator is ever carried from one basis to another. `--ground-truth` is optional
    (the prior CLI contract): absent, PRIMARY falls back to the G296 consensus set."""
    consensus_pts = [(int(r["source_frame"]), float(r["foot_x_px"]), float(r["foot_y_px"]))
                     for r in consensus()]
    adj = args.ground_truth if args.ground_truth and args.ground_truth.is_file() else None
    primary_pts = ([(int(r["frame_id"]), float(r["x"]), float(r["y"]))
                    for r in read_csv(adj) if r["source"] != "dropped"] if adj else
                   consensus_pts)
    out = {PRIMARY: primary_pts, "consensus_86": consensus_pts}
    for name, path in (("pass_A_131", args.pass_a), ("pass_B_130", args.pass_b)):
        out[name] = [(int(r["source_frame"]), float(r["foot_x_px"]), float(r["foot_y_px"]))
                     for r in eligible(read_csv(path))]
    return out


def detections(output):
    """Per-arm, per-frame detection footpoints in native 1920x1080 coordinates."""
    out = {}
    for arm in ARMS:
        by = {}
        for d in read_csv(output / f"{arm}.csv"):
            by.setdefault(int(d["source_frame"]), []).append(
                (float(d["foot_x_px"]), float(d["foot_y_px"])))
        out[arm] = by
    return out


def score_basis(name, pts, dets, meta):
    """Score every arm against ONE basis, by real matching against that basis's points.

    Each arm entry also carries the e82b702fc legacy per-arm fields (fix 1d, B2 CORRECTION 2)
    as aliases of the SAME numbers already computed above -- total_detections_24_frames,
    detections_per_frame_24, ms_per_frame, peak_vram_mib, pose_served_frames,
    downstream_errors and precision. `meta` (=dm["arms"]) is basis-independent (one detection
    run feeds every basis), matching the legacy schema's single arm-cost tree.

    Fix 1e (B2 CORRECTION 1): the six meta[arm] reads backing those new aliases are
    compatibility-safe `.get(key, None)` reads, so the pre-31a three-key META call
    (imgsz/conf/conf_source only) still succeeds instead of raising KeyError. Absent means
    JSON null on the alias, never a fabricated 0 or []."""
    by_frame = {}
    for f, x, y in pts:
        by_frame.setdefault(f, []).append((x, y))
    keys, n = sorted(by_frame), len(pts)
    ns = [len(by_frame[f]) for f in keys]
    label = f"{n} {name} points over {len(keys)} frames"
    sc = {a: score_arm(by_frame, dets[a], keys) for a in ARMS}
    entry = {"denominator": n, "denominator_name": label, "frame_ids": keys,
             "arms": {}, "paired_R_vs_P": {}}
    for arm in ARMS:
        on_scored = sum(len(dets[arm].get(f, [])) for f in keys)
        recall, precision = {}, {}
        for t in TOLERANCES:
            matched = sum(sc[arm]["hits"][t][f] for f in keys)
            plb = matched / on_scored if on_scored else None
            recall[t] = {"rule": "one_to_one", "matched": matched, "denominator": n,
                         "denominator_name": label, "recall": matched / n,
                         "ci95": bootstrap_ci([sc[arm]["hits"][t][f] for f in keys], ns),
                         "nearest_rule_matched": sum(sc[arm]["nearest_rule"][t]),
                         "precision_lower_bound": plb,
                         "precision_note": NOTE}
            precision[t] = {"matched_detections": matched, "note": NOTE,
                            "detections_on_scored_frames": on_scored,
                            "precision_lower_bound": plb}
        entry["arms"][arm] = {"imgsz": meta[arm]["imgsz"], "conf": meta[arm]["conf"],
                              "conf_source": meta[arm]["conf_source"], "recall": recall,
                              "detections_on_scored_frames": on_scored,
                              "median_nearest_px": sc[arm]["median_nearest_px"],
                              "total_detections_24_frames": meta[arm].get("total_detections"),
                              "detections_per_frame_24": meta[arm].get("detections_per_frame"),
                              "ms_per_frame": meta[arm].get("ms_per_frame"),
                              "peak_vram_mib": meta[arm].get("peak_vram_mib"),
                              "pose_served_frames": meta[arm].get("pose_served_frames"),
                              "downstream_errors": meta[arm].get("errors"),
                              "precision": precision}
    for t in TOLERANCES:
        p_hits = [sc["P"]["hits"][t][f] for f in keys]
        r_hits = [sc["R"]["hits"][t][f] for f in keys]
        entry["paired_R_vs_P"][t] = {
            "delta_recall": (sum(r_hits) - sum(p_hits)) / n, "denominator": n,
            "denominator_name": label, "ci95": bootstrap_ci(p_hits, ns, paired=r_hits),
            "mcnemar_exact": exact_mcnemar(sc["P"]["one_to_one"][t], sc["R"]["one_to_one"][t]),
            "p_is_nominal": True, "multiplicity_correction": "none"}
    return entry, sc, by_frame


def score(args):
    """Local arithmetic; every denominator is named in the artifact it is written to.
    Legacy top-level `primary_denominator`/`primary_denominator_name`/`primary_frame_ids`/
    `arms`/`paired_R_vs_P` are aliases of `bases[PRIMARY]`'s own fields -- same objects,
    never recomputed (fix pass 1c, B2 compatibility). Fix 1d adds the remaining e82b702fc
    top-level aliases `basis` and `secondary_denominators`, plus the two per-tolerance
    `matched_over_pass_A_only`/`matched_over_pass_B_only` recall fields -- these are now the
    REAL matched count from that basis's own independent matching (never the primary's
    recycled numerator, which was the original REJECT finding)."""
    dm = json.loads((args.output / "g303_detect.json").read_text())
    dets = detections(args.output)
    cost_keys = ("imgsz", "conf", "conf_source", "total_detections", "detections_per_frame",
                 "ms_per_frame", "peak_vram_mib", "pose_served_frames", "errors")
    report = {"primary_basis": PRIMARY, "tolerances_px": list(TOLERANCES),
              "registered_conf": REGISTERED_CONF, "step0": dm["step0"],
              "sign_convention": "delta = ARM R minus ARM P; positive means R finds more",
              "arm_P_byte_identical_repeat": dm["arm_P_byte_identical_repeat"],
              "arm_cost": {a: {k: dm["arms"][a][k] for k in cost_keys} for a in ARMS},
              "bases": {}}
    for name, pts in bases(args).items():
        entry, sc, by_frame = score_basis(name, pts, dets, dm["arms"])
        report["bases"][name] = entry
        if name == PRIMARY:
            write_csv(args.output / "per_frame_recall.csv",
                      [{"source_frame": f, "n_truth": len(by_frame[f]),
                        **{f"{a}_m50": sc[a]["hits"][50][f] for a in ARMS}}
                       for f in entry["frame_ids"]])
    primary = report["bases"][PRIMARY]
    pass_a, pass_b = report["bases"]["pass_A_131"], report["bases"]["pass_B_130"]
    for arm in ARMS:
        for t in TOLERANCES:
            r = primary["arms"][arm]["recall"][t]
            r["matched_over_pass_A_only"] = [pass_a["arms"][arm]["recall"][t]["matched"],
                                             pass_a["denominator"]]
            r["matched_over_pass_A_only_note"] = ("corrected: real pass-A matching against "
                "its own points, not the primary numerator recycled (G303_VERIFY B2)")
            r["matched_over_pass_B_only"] = [pass_b["arms"][arm]["recall"][t]["matched"],
                                             pass_b["denominator"]]
            r["matched_over_pass_B_only_note"] = ("corrected: real pass-B matching against "
                "its own points, not the primary numerator recycled (G303_VERIFY B2)")
    report["primary_denominator"] = primary["denominator"]
    report["primary_denominator_name"] = primary["denominator_name"]
    report["primary_frame_ids"] = primary["frame_ids"]
    report["arms"] = primary["arms"]
    report["paired_R_vs_P"] = primary["paired_R_vs_P"]
    report["basis"] = PRIMARY if (args.ground_truth and args.ground_truth.is_file()) else "consensus"
    report["secondary_denominators"] = {"pass_A_only": pass_a["denominator"],
                                        "pass_B_only": pass_b["denominator"]}
    (args.output / "g303_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(json.dumps(report["bases"][PRIMARY]["paired_R_vs_P"], indent=2))
    return report
