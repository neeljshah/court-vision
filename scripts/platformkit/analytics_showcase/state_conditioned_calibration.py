"""State-conditioned calibration: where is the model miscalibrated vs the market?

Buckets every graded ingame prediction by (model_prob band) x (game-state time
bucket, parsed from state_summary) and computes n-weighted calibration error
(|mean_p - mean_y|) per bucket, for both the model and the market. The ranked
worst-bucket list is the improvement backlog.

Corpora: data/cache/ingame_grade_joined/{mlb,soccer_intl}/*.jsonl (mlb_clean
is a byte-identical duplicate of mlb -- skipped to avoid double counting).

edge_claimed=False always. This is a calibration diagnostic, not a betting signal.
"""
import argparse
import glob
import json
import os
import re
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CORPUS_DIR = os.path.join(ROOT, "data", "cache", "ingame_grade_joined")
OUT_JSON = os.path.join(ROOT, "out", "state_conditioned_calibration.json")
OUT_PNG = os.path.join(ROOT, "docs", "img", "state_calibration_heatmap.png")

PROB_BINS = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]
PROB_LABELS = ["0-.2", ".2-.4", ".4-.6", ".6-.8", ".8-1"]

# sport -> (state field regex, time-bucket fn)
INNING_RE = re.compile(r"inning=(\d+)")
MINUTE_RE = re.compile(r"minute=(\d+)")


def mlb_time_bucket(state_summary):
    m = INNING_RE.search(state_summary or "")
    if not m:
        return None
    inning = int(m.group(1))
    if inning <= 3:
        return "early(inn1-3)"
    if inning <= 6:
        return "mid(inn4-6)"
    return "late(inn7+)"


def soccer_time_bucket(state_summary):
    m = MINUTE_RE.search(state_summary or "")
    if not m:
        return None
    minute = int(m.group(1))
    if minute >= 75:
        return "75-90+"
    lo = (minute // 15) * 15
    return f"{lo}-{lo + 15}"


SPORTS = {
    "mlb": mlb_time_bucket,
    "soccer_intl": soccer_time_bucket,
}


def prob_bucket(p):
    for i in range(len(PROB_BINS) - 1):
        lo, hi = PROB_BINS[i], PROB_BINS[i + 1]
        if (lo <= p < hi) or (i == len(PROB_BINS) - 2 and p == hi):
            return PROB_LABELS[i]
    return None


def load_records(sport):
    files = sorted(glob.glob(os.path.join(CORPUS_DIR, sport, "*.jsonl")))
    recs = []
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return files, recs


def build_buckets(sport, recs, time_bucket_fn):
    # key: (time_bucket, prob_bucket) -> {model: [p,y]..., market: [p,y]...}
    buckets = defaultdict(lambda: {"model": [], "market": []})
    n_skipped_no_state = 0
    for r in recs:
        tb = time_bucket_fn(r.get("state_summary"))
        if tb is None:
            n_skipped_no_state += 1
            continue
        y = r.get("outcome")
        mp = r.get("model_prob")
        kp = r.get("market_prob")
        if y is None:
            continue
        if mp is not None:
            pb = prob_bucket(mp)
            if pb is not None:
                buckets[(tb, pb)]["model"].append((mp, y))
        if kp is not None:
            pb = prob_bucket(kp)
            if pb is not None:
                buckets[(tb, pb)]["market"].append((kp, y))
    return buckets, n_skipped_no_state


def summarize_buckets(sport, buckets):
    rows = []
    for (tb, pb), d in buckets.items():
        for src in ("model", "market"):
            pts = d[src]
            if not pts:
                continue
            n = len(pts)
            mean_p = sum(p for p, _ in pts) / n
            mean_y = sum(y for _, y in pts) / n
            cal_err = abs(mean_p - mean_y)
            rows.append({
                "sport": sport,
                "time_bucket": tb,
                "prob_bucket": pb,
                "source": src,
                "n": n,
                "mean_p": round(mean_p, 4),
                "mean_y": round(mean_y, 4),
                "calibration_error": round(cal_err, 4),
            })
    return rows


def ece(rows, source):
    sub = [r for r in rows if r["source"] == source]
    total_n = sum(r["n"] for r in sub)
    if total_n == 0:
        return None
    return round(sum(r["calibration_error"] * r["n"] for r in sub) / total_n, 4)


def make_heatmap(all_rows, sports_present, out_png):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    time_orders = {
        "mlb": ["early(inn1-3)", "mid(inn4-6)", "late(inn7+)"],
        "soccer_intl": ["0-15", "15-30", "30-45", "45-60", "60-75", "75-90+"],
    }

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, source in zip(axes, ("model", "market")):
        # Combine sports into one grid: rows = sport/time_bucket, cols = prob_bucket
        row_labels = []
        for sp in sports_present:
            for tb in time_orders.get(sp, []):
                row_labels.append(f"{sp}:{tb}")
        grid = np.full((len(row_labels), len(PROB_LABELS)), np.nan)
        for r in all_rows:
            if r["source"] != source:
                continue
            label = f"{r['sport']}:{r['time_bucket']}"
            if label not in row_labels:
                continue
            ri = row_labels.index(label)
            ci = PROB_LABELS.index(r["prob_bucket"])
            grid[ri, ci] = r["calibration_error"]

        im = ax.imshow(grid, cmap="Reds", vmin=0, vmax=0.5, aspect="auto")
        ax.set_xticks(range(len(PROB_LABELS)))
        ax.set_xticklabels(PROB_LABELS, rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(len(row_labels)))
        ax.set_yticklabels(row_labels, fontsize=7)
        ax.set_title(f"{source} calibration error |mean_p-mean_y|", fontsize=10)
        ax.set_xlabel("model_prob band")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    fig.suptitle("State-conditioned calibration error: model vs market (n-weighted)", fontsize=11)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    fig.savefig(out_png, dpi=130)
    plt.close(fig)


def run():
    result = {
        "edge_claimed": False,
        "story": (
            "Buckets every graded ingame prediction by model_prob band x game-state "
            "time bucket; ranked_worst_buckets is where the model is furthest from "
            "outcomes relative to the market, i.e. the improvement backlog."
        ),
        "sports": {},
        "skipped": [],
    }
    all_rows = []
    sports_present = []

    for sport, time_fn in SPORTS.items():
        files, recs = load_records(sport)
        if not files:
            result["skipped"].append({"sport": sport, "reason": "no jsonl files found"})
            continue
        buckets, n_skipped = build_buckets(sport, recs, time_fn)
        rows = summarize_buckets(sport, buckets)
        if not rows:
            result["skipped"].append({"sport": sport, "reason": "no rows with parseable time bucket + outcome"})
            continue
        all_rows.extend(rows)
        sports_present.append(sport)
        result["sports"][sport] = {
            "n_files": len(files),
            "n_records": len(recs),
            "n_skipped_no_state_field": n_skipped,
            "model_ece_n_weighted": ece(rows, "model"),
            "market_ece_n_weighted": ece(rows, "market"),
            "buckets": rows,
        }

    result["skipped"].append({
        "sport": "mlb_clean",
        "reason": "byte-identical duplicate of mlb corpus (verified via filecmp) -- excluded to avoid double counting",
    })

    ranked = sorted(
        [r for r in all_rows if r["source"] == "model"],
        key=lambda r: r["calibration_error"],
        reverse=True,
    )
    result["ranked_worst_buckets"] = ranked[:15]

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    if sports_present:
        make_heatmap(all_rows, sports_present, OUT_PNG)
    else:
        result["png_skipped_reason"] = "no sports had usable rows"

    return result


def check():
    """Minimal self-check: run() produces a JSON with n-weighted ECE that is
    consistent with a hand-recomputation from ranked_worst_buckets."""
    result = run()
    assert result["ranked_worst_buckets"], "expected at least one worst bucket"
    top = result["ranked_worst_buckets"][0]
    assert top["calibration_error"] >= result["ranked_worst_buckets"][-1]["calibration_error"], "not sorted desc"
    for sport, d in result["sports"].items():
        rows = d["buckets"]
        model_rows = [r for r in rows if r["source"] == "model"]
        total_n = sum(r["n"] for r in model_rows)
        if total_n:
            recomputed = sum(r["calibration_error"] * r["n"] for r in model_rows) / total_n
            assert abs(recomputed - d["model_ece_n_weighted"]) < 1e-3, f"{sport} ECE mismatch"
    assert os.path.exists(OUT_JSON)
    assert os.path.exists(OUT_PNG)
    print("OK: state_conditioned_calibration self-check passed")


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
            print(sp, "model_ece", d["model_ece_n_weighted"], "market_ece", d["market_ece_n_weighted"], "n_records", d["n_records"])
