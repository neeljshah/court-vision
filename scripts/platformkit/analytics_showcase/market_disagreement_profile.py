"""Market disagreement profile: bucket rows by |model_prob - market_prob| and
report per-bucket n, model Brier, market Brier, outcome-agreement rate.

Honest question: when the model disagrees with the market a lot, who is usually
right? Reads the same row-level joined grade corpora as murphy_decomposition.py
(data/cache/ingame_grade_joined/{mlb,soccer_intl}/*.jsonl). edge_claimed=False.

Usage:
    python -m scripts.platformkit.analytics_showcase.market_disagreement_profile
    python -m scripts.platformkit.analytics_showcase.market_disagreement_profile --check
"""
import argparse
import glob
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
IN_DIR = os.path.join(REPO_ROOT, "data", "cache", "ingame_grade_joined")
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "market_disagreement_profile.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "market_disagreement_profile.png")
SPORTS = ["mlb", "soccer_intl"]
BUCKETS = [(0.0, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 1.0001)]
BUCKET_LABELS = ["<.02", ".02-.05", ".05-.10", ">=.10"]


def load_rows(sport):
    rows = []
    for path in glob.glob(os.path.join(IN_DIR, sport, "*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d.get("outcome") is None or d.get("model_prob") is None or d.get("market_prob") is None:
                    continue
                rows.append(d)
    return rows


def _model_right(p, m, y):
    """1 if model was closer to the outcome than market (agreement side), else 0.
    Ties (equal abs error) count as neither -- excluded from agreement rate denom."""
    de = abs(p - y) - abs(m - y)
    if de < 0:
        return 1
    if de > 0:
        return 0
    return None


def profile_sport(rows):
    buckets = []
    for (lo, hi), label in zip(BUCKETS, BUCKET_LABELS):
        in_bucket = [r for r in rows if lo <= abs(r["model_prob"] - r["market_prob"]) < hi]
        n = len(in_bucket)
        if n == 0:
            buckets.append({"bucket": label, "n": 0})
            continue
        model_brier = sum((r["model_prob"] - r["outcome"]) ** 2 for r in in_bucket) / n
        market_brier = sum((r["market_prob"] - r["outcome"]) ** 2 for r in in_bucket) / n
        agree_flags = [_model_right(r["model_prob"], r["market_prob"], r["outcome"]) for r in in_bucket]
        agree_flags = [f for f in agree_flags if f is not None]
        agreement_rate = sum(agree_flags) / len(agree_flags) if agree_flags else None
        buckets.append({
            "bucket": label,
            "n": n,
            "model_brier": round(model_brier, 6),
            "market_brier": round(market_brier, 6),
            "model_closer_rate": round(agreement_rate, 4) if agreement_rate is not None else None,
        })
    return buckets


def build_verdict(result):
    lines = []
    for sport, buckets in result["sports"].items():
        scored = [b for b in buckets if b.get("n", 0) > 0]
        if not scored:
            lines.append(f"{sport}: no scored rows.")
            continue
        biggest = scored[-1] if scored[-1]["n"] > 0 else None
        if biggest and biggest["model_closer_rate"] is not None:
            verdict = ("model usually closer" if biggest["model_closer_rate"] > 0.5
                        else "market usually right")
            lines.append(
                f"{sport}: at largest disagreement ({biggest['bucket']}, n={biggest['n']}), "
                f"{verdict} (model_closer_rate={biggest['model_closer_rate']:.3f}, "
                f"model_brier={biggest['model_brier']:.4f} vs market_brier={biggest['market_brier']:.4f})."
            )
    return " ".join(lines) if lines else "No sport had scorable rows."


def make_plot(result):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    sports_with_data = [s for s in SPORTS if any(b.get("n", 0) > 0 for b in result["sports"].get(s, []))]
    if not sports_with_data:
        return False

    fig, axes = plt.subplots(1, len(sports_with_data), figsize=(6 * len(sports_with_data), 4.5), sharey=False)
    if len(sports_with_data) == 1:
        axes = [axes]
    for ax, sport in zip(axes, sports_with_data):
        buckets = result["sports"][sport]
        labels = [b["bucket"] for b in buckets]
        model_b = [b.get("model_brier") for b in buckets]
        market_b = [b.get("market_brier") for b in buckets]
        x = range(len(labels))
        w = 0.35
        ax.bar([i - w / 2 for i in x], [v if v is not None else 0 for v in model_b], w, label="model Brier")
        ax.bar([i + w / 2 for i in x], [v if v is not None else 0 for v in market_b], w, label="market Brier")
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels)
        ax.set_xlabel("|model_prob - market_prob| bucket")
        ax.set_title(f"{sport} (n per bucket: {[b.get('n', 0) for b in buckets]})")
        ax.legend(fontsize=8)
    axes[0].set_ylabel("Brier score (lower = better)")
    fig.suptitle("Market disagreement profile: model vs market Brier by disagreement size")
    fig.text(0.5, 0.01,
              "Source: data/cache/ingame_grade_joined/{mlb,soccer_intl} row-level joined grade corpora. "
              "edge_claimed=False.", ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=140)
    plt.close(fig)
    return True


def run():
    result = {"edge_claimed": False,
              "method": "bucket rows by |model_prob - market_prob|; per-bucket model/market Brier + model_closer_rate",
              "sports": {}}
    for sport in SPORTS:
        rows = load_rows(sport)
        result["sports"][sport] = profile_sport(rows) if rows else []
    result["verdict"] = build_verdict(result)
    result["plot_written"] = make_plot(result)

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def check():
    """Synthetic: model always exactly right, market always wrong at large gap ->
    model_closer_rate should be 1.0 in the >=.10 bucket."""
    rows = [{"model_prob": 1.0, "market_prob": 0.5, "outcome": 1.0} for _ in range(10)]
    buckets = profile_sport(rows)
    top = buckets[-1]
    assert top["n"] == 10, top
    assert top["model_closer_rate"] == 1.0, top
    assert top["model_brier"] == 0.0, top
    print("market_disagreement_profile self-check OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        check()
        res = run()
        print(json.dumps({"verdict": res["verdict"], "plot_written": res["plot_written"],
                           "sports_n_buckets": {s: [b.get("n", 0) for b in v] for s, v in res["sports"].items()}},
                          indent=2))
