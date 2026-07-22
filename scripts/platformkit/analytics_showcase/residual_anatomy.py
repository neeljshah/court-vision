"""Residual anatomy: where does the model's error concentrate?

Reuses the same joined ingame corpora as state_conditioned_calibration.py but
reports it as an error-concentration exhibit: for each segment (sport x
game-state time bucket x model_prob band) computes model residual
(|model_prob - outcome|) mean and total absolute residual mass (mean_abs_err
* n), then ranks segments by total mass -- i.e. where fixing the model would
remove the most cumulative error, not just where the rate is worst on a thin
segment. This is the public improvement-backlog exhibit.

Corpora: data/cache/ingame_grade_joined/{mlb,soccer_intl}/*.jsonl (mlb_clean
is a byte-identical duplicate of mlb -- skipped to avoid double counting).

edge_claimed=False always. This is a calibration/error diagnostic, not a
betting signal.
"""
import argparse
import json
import os

try:  # -m package invocation (check_all) vs bare-script invocation
    from scripts.platformkit.analytics_showcase.state_conditioned_calibration import (
        SPORTS, load_records, prob_bucket)
except ImportError:
    from state_conditioned_calibration import SPORTS, load_records, prob_bucket

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT_JSON = os.path.join(ROOT, "scripts", "platformkit", "analytics_showcase", "out", "residual_anatomy.json")
OUT_PNG = os.path.join(ROOT, "docs", "img", "residual_anatomy.png")


def build_segments(sport, recs, time_bucket_fn):
    # key: (time_bucket, prob_bucket) -> list of abs residuals
    segs = {}
    n_skipped = 0
    for r in recs:
        tb = time_bucket_fn(r.get("state_summary"))
        y = r.get("outcome")
        mp = r.get("model_prob")
        if tb is None or y is None or mp is None:
            n_skipped += 1
            continue
        pb = prob_bucket(mp)
        if pb is None:
            continue
        segs.setdefault((tb, pb), []).append(abs(mp - y))
    return segs, n_skipped


def summarize(sport, segs):
    rows = []
    for (tb, pb), errs in segs.items():
        n = len(errs)
        mean_abs_err = sum(errs) / n
        rows.append({
            "sport": sport,
            "time_bucket": tb,
            "prob_bucket": pb,
            "n": n,
            "mean_abs_residual": round(mean_abs_err, 4),
            "total_abs_residual_mass": round(mean_abs_err * n, 2),
        })
    return rows


def make_chart(ranked, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    top = ranked[:15][::-1]
    labels = [f"{r['sport']}:{r['time_bucket']}:{r['prob_bucket']} (n={r['n']})" for r in top]
    mass = [r["total_abs_residual_mass"] for r in top]

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.barh(labels, mass, color="#b3452c")
    ax.set_xlabel("total abs residual mass (mean_abs_residual x n)")
    ax.set_title("Residual anatomy: worst error-concentration segments (ranked)")
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    fig.savefig(out_png, dpi=130)
    plt.close(fig)


def run():
    result = {
        "edge_claimed": False,
        "story": (
            "Ranks (sport x game-state time bucket x model_prob band) segments by "
            "total absolute residual mass -- where fixing the model removes the "
            "most cumulative error, i.e. the improvement backlog."
        ),
        "sports": {},
        "skipped": [
            {"sport": "mlb_clean", "reason": "byte-identical duplicate of mlb corpus -- excluded to avoid double counting"},
        ],
    }
    all_rows = []

    for sport, time_fn in SPORTS.items():
        files, recs = load_records(sport)
        if not files:
            result["skipped"].append({"sport": sport, "reason": "no jsonl files found"})
            continue
        segs, n_skipped = build_segments(sport, recs, time_fn)
        rows = summarize(sport, segs)
        if not rows:
            result["skipped"].append({"sport": sport, "reason": "no rows with parseable segment"})
            continue
        all_rows.extend(rows)
        result["sports"][sport] = {
            "n_files": len(files),
            "n_records": len(recs),
            "n_skipped": n_skipped,
            "segments": rows,
        }

    ranked = sorted(all_rows, key=lambda r: r["total_abs_residual_mass"], reverse=True)
    result["ranked_worst_segments"] = ranked[:15]

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    if ranked:
        make_chart(ranked, OUT_PNG)
    else:
        result["png_skipped_reason"] = "no segments had usable rows"

    return result


def check():
    """Minimal self-check: ranked list is sorted desc and mass ties to n * mean."""
    result = run()
    assert result["ranked_worst_segments"], "expected at least one worst segment"
    ranked = result["ranked_worst_segments"]
    assert all(ranked[i]["total_abs_residual_mass"] >= ranked[i + 1]["total_abs_residual_mass"]
               for i in range(len(ranked) - 1)), "not sorted desc"
    top = ranked[0]
    tol = 0.00005 * top["n"] + 1e-2  # rounding of mean_abs_residual (4dp) accumulates over n
    assert abs(top["mean_abs_residual"] * top["n"] - top["total_abs_residual_mass"]) < tol
    assert os.path.exists(OUT_JSON)
    assert os.path.exists(OUT_PNG)
    print("OK: residual_anatomy self-check passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        check()
    else:
        res = run()
        print(json.dumps({k: v for k, v in res.items() if k != "sports"}, indent=2)[:2000])
        for sp, d in res["sports"].items():
            print(sp, "n_records", d["n_records"], "n_segments", len(d["segments"]))
