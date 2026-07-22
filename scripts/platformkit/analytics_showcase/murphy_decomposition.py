"""Murphy decomposition (reliability/resolution/uncertainty) for model vs market,
computed from the row-level joined grade corpora in data/cache/ingame_grade_joined/.

Brier = reliability - resolution + uncertainty (10-bin decomposition, standard Murphy 1973).
Answers: is the model's Brier gap vs market a CALIBRATION problem (fixable, reliability)
or an INFORMATION problem (resolution -- market just knows more)?

edge_claimed=False. Calibration-only analytic, no $/ROI claims.

Usage:
    python -m scripts.platformkit.analytics_showcase.murphy_decomposition
    python -m scripts.platformkit.analytics_showcase.murphy_decomposition --check
"""
import argparse
import glob
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
IN_DIR = os.path.join(REPO_ROOT, "data", "cache", "ingame_grade_joined")
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "murphy_decomposition.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "reliability_model_vs_market.png")
N_BINS = 10
SPORTS = ["mlb", "soccer_intl"]
SIDES = ["model_prob", "market_prob"]


def load_rows(sport):
    rows = []
    for path in glob.glob(os.path.join(IN_DIR, sport, "*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if "outcome" not in d or d.get("outcome") is None:
                    continue
                rows.append(d)
    return rows


def murphy_decompose(rows, prob_field):
    """10-bin Murphy decomposition. Returns dict with brier, reliability, resolution,
    uncertainty, bins. Skips rows missing prob_field or outcome."""
    pairs = [(r[prob_field], r["outcome"]) for r in rows if r.get(prob_field) is not None]
    n = len(pairs)
    if n == 0:
        return None

    ybar = sum(y for _, y in pairs) / n
    uncertainty = ybar * (1.0 - ybar)
    brier = sum((p - y) ** 2 for p, y in pairs) / n

    bins = []
    reliability = 0.0
    resolution = 0.0
    for k in range(N_BINS):
        lo, hi = k / N_BINS, (k + 1) / N_BINS
        in_bin = [(p, y) for p, y in pairs if (lo <= p < hi) or (k == N_BINS - 1 and p == 1.0)]
        nk = len(in_bin)
        if nk == 0:
            bins.append({"bin_lo": lo, "bin_hi": hi, "n": 0, "mean_p": None, "mean_y": None})
            continue
        mean_p = sum(p for p, _ in in_bin) / nk
        mean_y = sum(y for _, y in in_bin) / nk
        reliability += (nk / n) * (mean_p - mean_y) ** 2
        resolution += (nk / n) * (mean_y - ybar) ** 2
        bins.append({"bin_lo": lo, "bin_hi": hi, "n": nk, "mean_p": round(mean_p, 4), "mean_y": round(mean_y, 4)})

    return {
        "n": n,
        "brier": round(brier, 6),
        "reliability": round(reliability, 6),
        "resolution": round(resolution, 6),
        "uncertainty": round(uncertainty, 6),
        "reconstructed_brier": round(reliability - resolution + uncertainty, 6),
        "bins": bins,
    }


def make_plot(result):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    fig, axes = plt.subplots(1, len(SPORTS), figsize=(11, 5), sharey=True)
    if len(SPORTS) == 1:
        axes = [axes]
    for ax, sport in zip(axes, SPORTS):
        sport_res = result["sports"].get(sport, {})
        for prob_field, label, marker in [("model_prob", "model", "o"), ("market_prob", "market", "s")]:
            dec = sport_res.get(prob_field)
            if not dec:
                continue
            xs = [b["mean_p"] for b in dec["bins"] if b["n"] > 0]
            ys = [b["mean_y"] for b in dec["bins"] if b["n"] > 0]
            ax.plot(xs, ys, marker=marker, label=f"{label} (Brier={dec['brier']:.4f})")
        ax.plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1, label="perfect")
        ax.set_title(sport)
        ax.set_xlabel("mean predicted prob (bin)")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("mean observed outcome (bin)")
    fig.suptitle("Reliability diagram: model vs market (10-bin Murphy decomposition)")
    fig.text(0.5, 0.01,
              "Source: data/cache/ingame_grade_joined/{mlb,soccer_intl} row-level joined grade corpora. "
              "Calibration-only, edge_claimed=False.",
              ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=140)
    plt.close(fig)
    return True


def build_verdict(result):
    lines = []
    for sport, sport_res in result["sports"].items():
        m = sport_res.get("model_prob")
        k = sport_res.get("market_prob")
        if not m or not k:
            continue
        gap = m["brier"] - k["brier"]
        rel_gap = m["reliability"] - k["reliability"]
        res_gap = m["resolution"] - k["resolution"]
        if abs(gap) < 1e-4:
            lines.append(f"{sport}: model and market Brier are effectively tied ({m['brier']:.4f} vs {k['brier']:.4f}).")
            continue
        driver = "reliability (calibration, fixable)" if abs(rel_gap) >= abs(res_gap) else "resolution (information, not fixable by recalibration)"
        worse_better = "worse" if gap > 0 else "better"
        lines.append(
            f"{sport}: model Brier {m['brier']:.4f} is {worse_better} than market {k['brier']:.4f} "
            f"(gap={gap:+.4f}); driven mainly by {driver} "
            f"(reliability_gap={rel_gap:+.4f}, resolution_gap={res_gap:+.4f})."
        )
    return " ".join(lines) if lines else "No sport had both model and market decomposable."


def run():
    result = {"edge_claimed": False, "method": "10-bin Murphy decomposition (Brier = reliability - resolution + uncertainty)", "sports": {}}
    for sport in SPORTS:
        rows = load_rows(sport)
        sport_out = {"n_rows": len(rows)}
        if not rows:
            sport_out["skipped_reason"] = "no rows found"
            result["sports"][sport] = sport_out
            continue
        for field in SIDES:
            dec = murphy_decompose(rows, field)
            if dec is None:
                sport_out[field] = None
                sport_out.setdefault("skipped_reason", f"{field} missing on all rows")
            else:
                sport_out[field] = dec
        result["sports"][sport] = sport_out

    result["verdict"] = build_verdict(result)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    plotted = make_plot(result)
    result["plot_written"] = plotted
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result


def check():
    """Tiny self-check: synthetic perfectly-calibrated predictor should have ~0 reliability."""
    rows = [{"model_prob": p, "outcome": 1.0 if i % 2 == 0 else 0.0} for i, p in enumerate([0.5] * 100)]
    # mean_p=0.5, mean_y=0.5 exactly -> reliability should be 0
    dec = murphy_decompose(rows, "model_prob")
    assert dec is not None
    assert abs(dec["reliability"]) < 1e-9, dec
    assert abs(dec["brier"] - dec["reconstructed_brier"]) < 1e-9, dec
    print("murphy_decomposition self-check OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        res = run()
        print(json.dumps({"verdict": res["verdict"], "plot_written": res["plot_written"],
                           "sports_n_rows": {s: v.get("n_rows") for s, v in res["sports"].items()}}, indent=2))
